# app.py  – Pelagica MVP v0.2
# ----------------------------------------------
# Dash app with:
#   • Genus → Species cascading dropdowns
#   • Searchable common-name dropdown
#   • Random-species button
#   • Image + blurb + full citation panel

from dash.exceptions import PreventUpdate
from dash import Dash, dcc, html, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc
from flask import send_from_directory, redirect, request, abort
from flask_compress import Compress


import pandas as pd, random, datetime
from urllib.parse import parse_qs
#import dash_cytoscape as cyto
#import networkx as nx
import numpy as np 
import json, base64   
import glob
import gc
import re
import time
import os
import requests
import secrets

from src.process_data import load_species_data, load_homo_sapiens, load_name_table, cm_to_in,load_species_with_taxonomy
from src.wiki import get_blurb, get_commons_thumb      
from src.utils import assign_random_depth
from src.taxonomic_tree import build_taxonomy_elements
from src.image_cache import url_to_stem
    
from src.fav_utils.routes_fav import register_fav_routes
from src.fav_utils.scoring import top_species, record_weekly_winner_if_missing
from src.fav_utils.utils_time import utcnow, next_monday_start


# --- media base switch (simple) ---
import os, mimetypes

#------------------- R2 Media path ---------------------
# Detect Fly; on Fly we always use R2
IS_FLY = any(k in os.environ for k in ("FLY_APP_NAME", "FLY_ALLOC_ID", "FLY_REGION"))

# You can flip this in local dev by setting USE_R2=true in your environment
USE_R2 = IS_FLY or os.getenv("USE_R2", "").strip().lower() in ("1", "true", "yes", "on")

R2_BASE = "https://pub-197edf068b764f1c992340f063f4f4f1.r2.dev"

def media_url(path: str) -> str:
    path = path.lstrip("/")
    return f"{R2_BASE}/{path}" if USE_R2 else f"/{path}"

def to_cdn(url: str) -> str:
    if not USE_R2 or not isinstance(url, str) or not url:
        return url
    if url.startswith("/cached-images/"):
        # /cached-images/<file>  ->  image_cache/<file> on R2
        fname = url.split("/cached-images/", 1)[1]
        return media_url(f"image_cache/{fname}")
    if url.startswith("/assets/"):
        return media_url(url.lstrip("/"))
    return url



mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")



print(f"BOOT: __name__={__name__} USE_DEV_SERVER={os.getenv('USE_DEV_SERVER')}")


def with_session_depth(df_use, depth_map):
    return df_use.assign(RandDepth=df_use["Genus_Species"].map(depth_map))
    
# --- Pre‑index scale images ------------------------------------
_scale_db = []
_pat = re.compile(r'(.+?)_(\d+(?:p\d+)?)(cm|m)\.webp$')

for p in glob.glob("assets/species/scale/*.webp"):
    name = os.path.basename(p)
    m = _pat.match(name)
    if not m:
        continue
    desc, num, unit = m.groups()
    num = float(num.replace('p', '.'))
    length_cm = num if unit == "cm" else num * 100
    _scale_db.append({
    "path": media_url(f"assets/species/scale/{name}"),  # ← was "/assets/species/scale/{name}"
    "desc": desc.replace('_', ' '),
    "length_cm": length_cm
    })

# NEW: human silhouettes (same filename convention)
_humanscale_db = []
for p in glob.glob("assets/species/humanscale/*.webp"):
    name = os.path.basename(p)
    m = _pat.match(name)
    if not m:
        continue
    desc, num, unit = m.groups()
    num = float(num.replace('p', '.'))
    length_cm = num if unit == "cm" else num * 100
    _humanscale_db.append({
        "path": media_url(f"assets/species/humanscale/{name}"),
        "desc": desc.replace('_', ' '),
        "length_cm": length_cm
    })

# ---------- Load & prep dataframe ---------------------------------------------------
df_full = load_species_with_taxonomy()  # heavy table + taxonomic data (cached in process_data)
df_light = load_name_table()     # 5‑col view on the cached frame   

# --- Popular-species whitelist -----------------------------------
popular_df   = pd.read_csv("data/processed/popular_species.csv")        # <-- path in /mnt/data
popular_set  = set(popular_df["Genus"] + " " + popular_df["Species"])

# --- Transparency‑removal blacklist -----------------------------
transp_df  = pd.read_csv("data/processed/transparency_blacklist.csv")
transp_set = set(transp_df["Genus"] + " " + transp_df["Species"])

gc.collect() 

# --- Common-name dictionary ------------------------------------------
common_taxa_df = (
    pd.read_csv("data/processed/common_names_taxa.csv",  
                names=["scientific", "common"],   
                header=None)
      .apply(lambda s: s.str.strip())          # trim whitespace
)

COMMON_NAMES = dict(zip(common_taxa_df.scientific, common_taxa_df.common))

def _label_with_common(taxon: str) -> str:
    """
    Return 'Taxon (common name)' if we have one, otherwise just 'Taxon'.
    Keeps dropdown .value equal to the scientific name.
    """
    cmn = COMMON_NAMES.get(taxon)
    return f"{taxon} ({cmn})" if cmn else taxon



# ---------- Build Dash app ----------------------------------------------------------
# external sheets (font + bootstrap)
external_stylesheets = [
    dbc.themes.LUX,
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap"
]
app = Dash(
    __name__,
    compress=True,serve_locally=False,
    external_stylesheets=external_stylesheets,
    title="Pelagica - The Aquatic Life Atlas",
    meta_tags=[
        {"name": "description", "content": "Explore 69,000+ marine species by depth, size, and taxonomy. Ambient soundscapes, smooth descent animation, and curated images."},
        {"name": "viewport", "content": "width=device-width, initial-scale=1"}
    ]
)

server = app.server

Compress(server)

server.config.update(
    COMPRESS_MIMETYPES=[
        "text/html", "text/css", "application/json",
        "application/javascript", "image/svg+xml"
    ],
    COMPRESS_LEVEL=3,        # safe default
    COMPRESS_MIN_SIZE=4096   # don’t waste CPU on tiny payloads
)


server.config["COMPRESS_ALGORITHM"] = ["gzip"]
server.config["COMPRESS_LEVEL"] = 4
server.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000  # 1 year

    
@app.server.route("/viewer/<path:filename>")
def serve_viewer_file(filename):
    resp = send_from_directory("depth_viewer", filename, conditional=True)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp

GOOGLE_VERIFY_FILE = "google50c42cdb868fa4f0.html"  

@server.get(f"/{GOOGLE_VERIFY_FILE}")
def google_site_verification():
    return send_from_directory(os.path.dirname(__file__), GOOGLE_VERIFY_FILE)
    
R2_PUBLIC = R2_BASE.rstrip("/")
CACHE_DIR = os.path.abspath("image_cache")

try:
    from src.wiki import WIKI_NAME_EQUIVALENTS
except Exception:
    WIKI_NAME_EQUIVALENTS = {}


def _canon_title(gs: str) -> str:
    title = (gs or "").replace("_", " ").strip()
    return WIKI_NAME_EQUIVALENTS.get(title, title)

def _stems(gs: str, w: int):
    title = _canon_title(gs)
    return (
        url_to_stem(f"{title}_{w}"),       # processed
        url_to_stem(f"{title}_{w}_raw"),   # raw
    )

def _r2_has(name: str) -> bool:
    try:
        r = requests.head(f"{R2_PUBLIC}/image_cache/{name}", timeout=2)
        return r.status_code == 200
    except Exception:
        return False

def _r2_has_path(rel_path: str) -> bool:
    try:
        r = requests.head(f"{R2_PUBLIC}/{rel_path.lstrip('/')}", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


@app.server.route("/cached-images/<path:fname>")
def cached_images(fname: str):
    gs = (
        request.args.get("gs")
        or request.args.get("sow")
        or request.args.get("species")
    )

    try:
        w = int(request.args.get("w", "640"))
    except Exception:
        w = 640

    # Dev: serve from disk with same preference order
    # Dev: serve from disk; respect ?variant=raw and transparency blacklist
    if not USE_R2:
        if gs:
            prefer = (request.args.get("variant") or "").lower()
            title = _canon_title(gs)                   # normalize (handles Wiki equivalents)
            prefer_raw = (prefer == "raw") or (title in transp_set)

            p, r = _stems(gs, w)                       # (processed, raw)
            order = (r, p) if prefer_raw else (p, r)   # flip when raw is preferred

            for stem in order:
                f = f"{stem}.webp"
                if os.path.exists(os.path.join(CACHE_DIR, f)):
                    return send_from_directory(CACHE_DIR, f)

        # exact filename fallback
        return send_from_directory(CACHE_DIR, fname)


    # Prod: redirect to whichever exists on R2 (processed → raw → requested)
    candidates = []
    if gs:
        prefer = (request.args.get("variant") or "").lower()
        p, r = _stems(gs, w)
        candidates.extend([f"{r}.webp", f"{p}.webp"]) if prefer == "raw" else candidates.extend([f"{p}.webp", f"{r}.webp"])
    if not fname.endswith(".webp"):
        fname = f"{fname}.webp"
    candidates.append(fname)

    seen = set()
    for name in [x for x in candidates if not (x in seen or seen.add(x))]:

        if _r2_has(name):
            resp = redirect(f"{R2_PUBLIC}/image_cache/{name}", code=302)
            resp.headers["Cache-Control"] = "public, max-age=86400"
            return resp

    return abort(404)

    


@app.server.route('/favicon.ico')
def serve_favicon():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'favicon.ico')
    
register_fav_routes(app) 

# _____ compute extremes _____________________________

def compute_extremes(df):
    shallow_col = df["DepthRangeComShallow"].where(df["DepthRangeComShallow"].notna(),
                                                   df["DepthRangeShallow"])
    deep_col    = df["DepthRangeComDeep"].where(df["DepthRangeComDeep"].notna(),
                                                df["DepthRangeDeep"])
    size_col    = df["Length_cm"]

    shallowest_idx = shallow_col.dropna().idxmin() if shallow_col.notna().any() else None
    deepest_idx    = deep_col.dropna().idxmax()    if deep_col.notna().any()    else None
    smallest_idx   = size_col.dropna().idxmin()    if size_col.notna().any()    else None
    largest_idx    = size_col.dropna().idxmax()    if size_col.notna().any()    else None

    def gs_at(idx):
        return None if idx is None else f"{df.iloc[idx].Genus} {df.iloc[idx].Species}"

    return {
        "shallowest": gs_at(shallowest_idx),
        "deepest":    gs_at(deepest_idx),
        "smallest":   gs_at(smallest_idx),
        "largest":    gs_at(largest_idx),
    }

EXTREMES = compute_extremes(df_full)


# ─── TOP BAR ───────────────────────────────────────────────

units_toggle = dbc.Switch(
    id="units-toggle",
    value=False,              # False → pill left  →  metric  (m)
    className="units-switch", # we skin it in CSS
)

units_block = html.Div(
    [
        html.Span("m",  style={"marginRight": ".35rem"}),
        units_toggle,
        html.Span("ft", style={"marginLeft":  "-0.5rem"}),
    ],
    style={"display": "flex",
           "alignItems": "center",
           "fontSize": ".8rem"}
)



top_bar = html.Div(
    [
        # 1. logo & tagline
        html.A(
            [
                html.Img(src="/assets/img/logo_pelagica_colour.webp", style={"height": "50px"}),
                html.Span(
                    "The Aquatic Life Atlas",
                    className="tagline",
                    style={"marginLeft": ".5rem", "fontSize": ".9rem", "fontWeight": 500, "color": "#f5f5f5"},
                ),
            ],
            href=app.get_relative_path("/"),
            id="logo-link",
            style={"display": "flex", "alignItems": "center", "textDecoration": "none", "color": "inherit"},
        ),

        # 2. spacer
        html.Div(style={"flex": "1"}),
        
        html.Div(
            ["🕪", html.Span("", className="sound-label")],
            id="depth-sound-btn",
            className="top-sound",
            style={"cursor": "pointer", "fontSize": ".9rem", "marginRight": "0.0rem", "opacity": 0.5},
        ),

        html.Div("|", style={"opacity": .4, "margin": "0 1rem"}),
        
        html.Div([
        html.Span("♡",  className="fav-icon"),
        html.Span(" Favourites", className="fav-label")   ],
            id="fav-menu-btn",
            className="top-heart",
            style={"cursor": "pointer", "fontSize": ".9rem"}
        ),

        html.Div("|", style={"opacity": .4, "margin": "0 1rem"}),

        units_block,
    ],
    id="top-bar",
    className="glass-panel",
    style={"display": "flex", "alignItems": "center",
           "padding": "0.5rem 1rem"}
)




# ─── SEARCH STACK ───────────────────────────────────────────────
search_stack = html.Div(id="search-stack", children=[
    html.Div(
        dcc.Dropdown(id="common-dd", options=[],
                     placeholder="Common name…", className="dash-dropdown",clearable=True, searchable=True)
    ),
    
    html.Div(                    # hidden unless the toggle is ON
        id="taxa-row",
        children=[
            dbc.Row([
                dbc.Col(
                    dcc.Dropdown(
                        id="order-dd", options=[],
                        placeholder="Order", className="dash-select"),
                    width=6),
                dbc.Col(
                    dcc.Dropdown(
                        id="family-dd", options=[],
                        placeholder="Family", className="dash-select"),
                    width=6),
            ])
        ],
        style={"display": "none"},),

    
    html.Div(
        dbc.Row([
            dbc.Col(
                dcc.Dropdown(id="genus-dd", options=[],
                             placeholder="Genus", className="dash-select"), width=6
            ),
            dbc.Col(
                dcc.Dropdown(id="species-dd",
                             placeholder="Species", className="dash-select"), width=6
            )
        ])
    ),
    
    html.Div(
        [
            html.Button("⚙ Settings", id="open-settings-btn",
                        className="btn btn-outline-light btn-sm"),
            html.Button("Random", id="random-btn",
                        className="btn btn-outline-light btn-sm")
        ],
        style={
            "display": "flex",
            "justifyContent": "space-between",   # Settings left, Random right
            "gap": "0.8rem",
            "marginTop": "0.4rem"
        }
    )

])


# --- Species of the Week/Hour card (UI) ---
species_of_week_card = html.Div(
    id="sow-card",
    className="glass-panel",
    style={"marginTop": "0.6rem", "cursor": "pointer"},  # ← always rendered
    children=[
        html.Div(
            id="sow-body",
            style={"display": "flex", "alignItems": "center", "gap": "0.6rem"},
            children=[
                html.Img(id="sow-thumb",
                         style={"width": "64px", "height": "64px", "objectFit": "cover", "borderRadius": "6px"}),
                html.Div([
                    html.Div(id="sow-common",     style={"fontSize": "0.95rem", "fontWeight": 600}),
                    html.Div(id="sow-scientific", style={"fontSize": "0.9rem", "opacity": 0.85}),
                    html.Small(id="sow-note",     style={"opacity": 0.7})
                ])
            ]
        )
    ]
)



CITATION_W  = 300   
PANEL_WIDTH  = CITATION_W
SEARCH_W, SEARCH_TOP = 450, 120    # width px, distance below top bar

advanced_filters = html.Div([           # collapsible area

    dbc.Checklist(
    id="instant-toggle",
    options=[{"label": "Enable descent animation", "value": "on"}],
    value=["on"],          # checked    → animation runs
    switch=True,
    className="settings-group"),
    
    dbc.Checklist(
        id="taxa-toggle",
        options=[{"label": "Allow selecting by order and family",
                  "value": "taxa"}],
        value=[],                # default = OFF
        switch=True,
        className="settings-group",
    ),
    
    # NEW: human silhouette switch (defaults OFF)
    dbc.Checklist(
        id="human-scale-toggle",
        options=[{"label": "Human silhouette for size comparison", "value": "human"}],
        value=[], switch=True, className="settings-group",
    ),


    # ── Filters ────────────────────────────────────────────────────
    html.H6("Filters", className="settings-header"),

    html.Div("Filters apply to dropdown options, random buttons, quick jumps, and navigation bridge", className="settings-note", style={"paddingLeft": "0.5rem"}),
    
    html.Br(),
    
    html.Div([
        dbc.Checklist(
            id="wiki-toggle",
            options=[{
                "label": "Only species with Wikipedia entry",
                "value": "wiki"
            }],
            value=[],
            switch=True
        )
    ], className="settings-group"),

    html.Div([
        dbc.Checklist(
            id="popular-toggle",
            options=[{
                "label": "Only curated species (recommended)",
                "value": "pop"
            }],
            value=["pop"],
            switch=True
        ),

    ], className="settings-group"),
    
    html.Div("1,500+ species with approved images", className="settings-note"),
    
    html.Br(),

    dbc.Checklist(
        id="favs-toggle",
        options=[{"label": "Only species I have favourited", "value": "fav"}],
        value=[], switch=True
    ),
    
    #stop navigation


    # ── Quick-jump buttons (unchanged) ─────────────────────────────
    html.H6("Quick jumps", className="settings-header"),
    dbc.Row([
        dbc.Col(html.Button("jump to shallowest", id="shallowest-btn",
                            className="btn btn-outline-light btn-sm w-100"), width=6),
        dbc.Col(html.Button("jump to deepest",    id="deepest-btn",
                            className="btn btn-outline-light btn-sm w-100"), width=6),
    ], className="gx-1", style={"marginBottom": ".4rem"}),

    dbc.Row([
        dbc.Col(html.Button("jump to smallest", id="smallest-btn",
                            className="btn btn-outline-light btn-sm w-100"), width=6),
        dbc.Col(html.Button("jump to largest",  id="largest-btn",
                            className="btn btn-outline-light btn-sm w-100"), width=6),
    ], className="gx-1"),
    
    # ↓ add this immediately after your two Quick jump rows
    html.H6(id="sow-title", children="Species of the Week", className="settings-header"),
    species_of_week_card,


],
id="adv-box",
style={"display": "none"})


search_header = html.Div(
    #[
    #    html.Span("🔍 Search", id="search-toggle",
    #              style={"fontWeight":"600","cursor":"pointer"})
    #],
    style={"display":"flex","justifyContent":"space-between",
           "alignItems":"center","marginBottom":"0.6rem"}
)


search_panel = html.Div(
    [
        html.Div("×", id="mobile-close-btn", className="mobile-close"),
        search_header,
        search_stack,
        advanced_filters
    ],
    id="search-panel", className="glass-panel search-panel open"
)






# --------------------------------------------------------------------
#  Citations OFF-canvas
# --------------------------------------------------------------------


citations_panel = dbc.Offcanvas(
    id="citations-canvas",
    className="glass-panel",
    placement="end",
    title="Citations",
    is_open=False,
    close_button=False,
    backdrop=False,
    autoFocus=False, 
    scrollable=True,
    style={"width": f"{CITATION_W}px"},   # <-- inject Python var here
    children=html.Div(
        id="citation-box",
        style={"whiteSpace": "pre-wrap"},
        children=[html.Br(), html.Br(),
                  html.Span("Code, background images, animations, "
                            "and UI design: © 2025 Victoria Tiki")]
    )
)





taxonomic_tree = html.Div(
    id="tree-panel",
    className="glass-panel",
    style={
        "display": "none",
        "position": "absolute",
        "inset": "0",
        "padding": 0,
        "boxSizing": "border-box",
        "zIndex": 1,
        "backgroundColor": "rgba(0,0,0,0.60)",
        "color": "#fff",
        "overflow": "auto",              # ← enable scrolling
    },
    children=dcc.Graph(
        id="tree-plot",
        style={"width": "100%", "height": "auto", "backgroundColor": "rgba(0,0,0,0)"},
        config={"displayModeBar": False}
    ),
)





# --------------------------------------------------------------------
#  Centre-page flex wrapper
# --------------------------------------------------------------------

centre_flex = html.Div(id="page-centre-flex", children=[
    html.Div(id="image-wrapper", style={"position": "relative"}, children=[

        # this div now contains the image AND the up/down buttons
        html.Div(id="image-inner", children=[
            html.Img(id="species-img"),
            html.Img( id="arrow-img",src="/assets/species/scale/arrow.webp",style={
              "position": "absolute",
              "left": "50%", "top": "50%",
              "transform": "translate(-50%, -50%)",
              "width": "100%",
              "opacity": 0.9,
              "pointerEvents": "none",  
              "zIndex": 2               
          }),
           html.Img(id="sizecmp-img",style={"position": "absolute","left": 0, "top": 0,"zIndex":2,"opacity": 0.85,"pointerEvents": "auto","cursor": "pointer"}),
            html.Div("i", id="info-handle", style={"display": "block","zIndex":4}),
            dbc.Tooltip("Show more information about this species",target="info-handle",placement="top",style={"fontSize": "0.8rem"}),
            html.Div("♡", id="fav-handle", className="heart-icon"),
            dbc.Tooltip( "Add this species to favourites",target="fav-handle",placement="top",style={"fontSize": "0.8rem"}),
            html.Div("📏", id="compare-handle", className="scale-icon"),
            dbc.Tooltip(id="scale-tooltip",target="compare-handle",placement="top",style={"fontSize": "0.8rem"}, children="Compare size", key="initial"),
            html.Div("🕪", id="sound-handle", className="sound-icon"),  
            dbc.Tooltip("Play species sound", target="sound-handle",placement="top", style={"fontSize": "0.8rem"}),
            html.Div("🧬", id="tree-handle", className="tree-icon"),
            dbc.Tooltip("Show taxonomic tree (including a selection of related taxa)", target="tree-handle",placement="top", style={"fontSize": "0.8rem"}),


        ]),
        
        taxonomic_tree,

        # info card remains outside image-inner
        html.Div(id="info-card", className="glass-panel",children=[
            html.Div(id="info-close", children="✕"),
            html.Div(id="info-content")
        ]),
        html.Audio(id="species-audio", src="", preload="auto",style={"display": "none"}), 
        
    ])
])

center_message=html.Div(
    id="load-message",
    children="Select a species",
    style={
        "position": "fixed",
        "top": "50%",
        "left": "50%",
        "transform": "translate(-50%, -50%)",
        "zIndex": 9999,
        "padding": "1rem 2rem",
        "backgroundColor": "rgba(0, 0, 0, 0.7)",
        "color": "white",
        "fontSize": "1.2rem",
        "borderRadius": "0.5rem",
        "display": "none",  # hidden by default
        "textAlign": "center"
    }
)



# --------------------------------------------------------------------
#  Assemble Layout
# --------------------------------------------------------------------
# footer credit  (replace the faulty line)
footer = html.Div(
    [
        html.Span("created by "),
        html.A("Victoria Tiki",
               href="https://victoriatiki.com/about/",
               target="_blank",
               rel="noopener",
               style={"color": "#fff"})
    ],
    style={
        "position": "fixed",
        "right": "3.5rem",
        "bottom": "1rem",
        "fontSize": ".8rem",
        "opacity": .7
    }
)
  

# replace the whole fav_modal block
fav_modal = dbc.Modal(
    [
        dbc.ModalHeader("Liked species", close_button=True, style={"color": "#000000"}),
        dbc.ModalBody(
            [
                html.Button("⬇ Export (.txt)", id="fav-export",
                            className="btn btn-outline-primary btn-sm w-100"),
                dcc.Download(id="fav-dl"),
                html.Br(),
                html.Br(),
                dcc.Upload("⬆ Load (.txt)", id="fav-upload",
                           className="btn btn-outline-primary btn-sm w-100",
                           multiple=False)
            ],
            className="p-2"
        ),
    ],
    id="fav-modal",
    is_open=False,
    centered=True,
    backdrop=True,
    className="fav-modal",          # <─ NEW
)

#------------- some trick to remove the depth/size toggles from page w/o id errors ------------
invisible_toggles= html.Div(
    [
        dcc.Checklist(
            id="depth-toggle",
            options=[{"label": "Enable navigation by depth", "value": "depth"}],
            value=["depth"],  # or [] if you want them 'off' by default
        ),
        dcc.Checklist(
            id="size-toggle",
            options=[{"label": "Enable navigation by size", "value": "size"}],
            value=["size"],
        ),
    ],
    style={"display": "none"}  # ← this hides it from view
)




# ─── NAVIGATION PANEL w/ DIAL ─────────────────────────────────────────
nav_panel = html.Div([
    # ── Header ────────────────────────────────────────────────
    html.Div([
        html.Span("ⓘ", id="nav-info-icon", className="nav-info-icon"),
    ], className="nav-header"),

    # ── Compass in one layer ───────────────────────────────────
    html.Img(src="/assets/img/dial.webp", className="dial-bg"),

    html.Div([
        html.Button("〉", id="up-btn", className="nav-icon"),
        html.Small("shallower", id="nav-label-up", className="nav-label"),
    ], id="up-wrap", className="nav-wrap up"),

    html.Div([
        html.Button("〉", id="down-btn", className="nav-icon"),
        html.Small("deeper", id="nav-label-down", className="nav-label"),
    ], id="down-wrap", className="nav-wrap down"),

    html.Div([
        html.Button("〉", id="prev-btn", className="nav-icon"),
        html.Small("smaller", id="nav-label-left", className="nav-label"),
    ], id="prev-wrap", className="nav-wrap left"),

    html.Div([
        html.Button("〉", id="next-btn", className="nav-icon"),
        html.Small("larger", id="nav-label-right", className="nav-label"),
    ], id="next-wrap", className="nav-wrap right"),
    
    html.Button("🔄", id="nav-random-btn", className="nav-icon rand-icon",
            style={"position": "absolute", "bottom": "4%", "right": "4%"}),
            
    html.Button("🧬", id="order-lock-btn",className="nav-icon lock-icon",style={"position": "absolute", "bottom": "4%", "left": "4%","opacity": .25}),



    # ── Hidden explanation ─────────────────────────────────────
    html.Div([
        "Navigation Bridge",
        html.Br(), html.Br(),
        "Explore species by size or depth. Move from shallow waters to the deep sea, and from tiny creatures to giants.",
        html.Br(),
        html.Br(),
        "Tap 🔄 to discover a random species, or 🧬 to limit your journey to species within the same taxonomic order (applies to navigation bridge only).",
        html.Br(),
    ],
        id="nav-info-text",
        style={"display": "none"}
    ),
    
    html.Div(id="order-lock-label", className="order-lock-label")
    


], id="nav-panel", className="glass-panel")






#-------------
search_handle = html.Div(["🔍 Search"], id="search-handle", className="search-handle", **{"data-mobile-x": "true"})

depth_store = dcc.Store(id="depth-store", storage_type="session")
feedback_link=html.A("feedback", href="https://forms.gle/YuUFrYPmDWsqyHdt7", target="_blank", style={"textDecoration": "none", "color": "inherit", "cursor": "pointer"})

#  Assemble Layout
app.layout = dbc.Container([
   html.Iframe(id="depth-iframe",src="/viewer/index.html",
            style={"border": "none"},
        ),
    html.Div(id="scale-root", children=[
        html.Div(id="seo-trigger", style={"display": "none"}),
        dcc.Location(id="url", refresh=False),
        dcc.Interval(id="sow-refresh", interval=60_000, n_intervals=0),  # 60s

        search_panel,
        invisible_toggles, 
        search_handle,
        dcc.Store(id="rand-seed", storage_type="session"),
        
        top_bar,
        
        dbc.Tooltip("Toggle ambient depth sound", target="depth-sound-btn",placement="bottom"),
        dcc.Store(id="sound-on", data=False, storage_type="session"),
        html.Audio(id="snd-surface-a", preload="none", style={"display":"none"}),
        html.Audio(id="snd-surface-b", preload="none", style={"display":"none"}),
        html.Audio(id="snd-epi2meso-a",preload="none", style={"display":"none"}),
        html.Audio(id="snd-epi2meso-b",preload="none", style={"display":"none"}),
        html.Audio(id="snd-abyss2hadal-a",preload="none", style={"display":"none"}),
        html.Audio(id="snd-abyss2hadal-b",preload="none", style={"display":"none"}),
        html.Audio(id="snd-meso2bath-a",preload="none", style={"display":"none"}),
        html.Audio(id="snd-meso2bath-b",preload="none", style={"display":"none"}),
        html.Audio(id="snd-bath2abyss-a",preload="none", style={"display":"none"}),
        html.Audio(id="snd-bath2abyss-b", preload="none", style={"display":"none"}),
        html.Div(id="js-audio-sink", style={"display": "none"}),
        dcc.Store(id="audio-src-sink", data=None, storage_type="memory"),  


        
        fav_modal,


        html.Div("citations",      id="citations-tab", className="side-tab"),
        html.Div(feedback_link,   id="bug-tab",       className="side-tab"),

        html.Div(centre_flex, id="main-content", style={"display": "none"}),
        center_message,
        html.Div(id="tree-click-trigger", style={"display": "none"}),
        
        nav_panel,
        dcc.Store(id="order-lock-state", data=False, storage_type="memory"),
        
 
        
        dcc.Store(id="anim-done", data=False, storage_type="session"),
        dcc.Store(id="rand-depth-map", storage_type="session"),
        dcc.Store(id="depth-order-store", storage_type="session"),
        dcc.Store(id="eligible-depth-bounds-all",    storage_type="session"),
        dcc.Store(id="eligible-depth-bounds-locked", storage_type="session"),
        dcc.Store(id="depth-order-store-all",        storage_type="session"),
        dcc.Store(id="depth-order-store-locked",     storage_type="session"),
        dcc.Store(id="depth-store",                  storage_type="session"),


        footer,
        
        
        
        html.Div(id="js-trigger", style={"display": "none"}),
        html.Div(id="url-trigger", style={"display": "none"}),   # new
        dcc.Store(id="selected-species", data=None),
        dcc.Store(id="favs-store",storage_type="local"),      # persists in localStorage
        dcc.Store(id="compare-store", data=False, storage_type="session"),
        dcc.Store(id="common-opt-cache", data=[]),
        


        citations_panel,
    ])
], fluid=True)

################################################
# ---------- Update Dropdown Options ----------#
################################################

@app.callback(
    Output("order-dd",  "options"),
    Output("order-dd",  "value"),
    Input("wiki-toggle",    "value"),
    Input("popular-toggle", "value"),
    Input("favs-toggle",    "value"),
    Input("taxa-toggle",    "value"),
    State("favs-store",     "data"),
    State("order-dd",       "value"),
)
def filter_order(wiki_val, pop_val, fav_val, toggle_val,
                 favs_data, current):
    if "taxa" not in toggle_val:
        return [], None

    df_use = _apply_shared_filters(df_full, wiki_val, pop_val,
                                   fav_val, favs_data)
    # ---------- Order dropdown ----------
    orders = sorted(df_use["order"].dropna().unique())
    opts   = [{"label": _label_with_common(o), "value": o} for o in orders]

    return opts, current if current in orders else None


@app.callback(
    Output("family-dd", "options"),
    Output("family-dd", "value"),
    Input("order-dd",      "value"),
    Input("wiki-toggle",   "value"),
    Input("popular-toggle","value"),
    Input("favs-toggle",   "value"),
    Input("taxa-toggle",   "value"),        # NEW
    State("favs-store",    "data"),
    State("family-dd",     "value"),
)
def filter_family(order_val, wiki_val, pop_val, fav_val, toggle_val,
                  favs_data, current):
    if "taxa" not in toggle_val:
        return [], None      # toggle OFF → blank + cleared

    df_use = _apply_shared_filters(df_full, wiki_val, pop_val,
                                   fav_val, favs_data)
    if order_val:
        df_use = df_use[df_use["order"] == order_val]

    # ---------- Family dropdown ----------
    families = sorted(df_use["family"].dropna().unique())
    opts     = [{"label": _label_with_common(f), "value": f} for f in families]


    return opts, current if current in families else None


@app.callback(
    Output("genus-dd", "options"),
    Output("genus-dd", "value"),
    Input("wiki-toggle",    "value"),
    Input("popular-toggle", "value"),
    Input("favs-toggle",    "value"),
    Input("order-dd",       "value"),      # NEW
    Input("family-dd",      "value"),      # NEW
    State("favs-store",     "data"),
    State("genus-dd", "value"),
)
def filter_genus(wiki_val, pop_val, fav_val,
                 order_val, family_val, favs_data, current):
    df_use = _apply_shared_filters(df_full, wiki_val, pop_val,
                                   fav_val, favs_data)     
    if order_val:
        df_use = df_use[df_use["order"] == order_val]
    if family_val:
        df_use = df_use[df_use["family"] == family_val]

    genera = sorted(df_use["genus"].dropna().unique())     # use df_full’s column
    opts   = [{"label": g, "value": g} for g in genera]
    return opts, current if current in genera else None



@app.callback(
    Output("species-dd", "options"),
    Output("species-dd", "value"),
    Input("genus-dd",      "value"),
    Input("wiki-toggle",   "value"),
    Input("popular-toggle","value"),
    Input("favs-toggle",   "value"),       # NEW
    State("favs-store",    "data"),        # NEW
    State("species-dd", "value"),
)
def update_species_options(genus, wiki_val, pop_val,
                           fav_val, favs_data, current):
    if not genus:
        return [], None

    df_use = _apply_shared_filters(df_light, wiki_val, pop_val,
                                   fav_val, favs_data)
    df_use = df_use[df_use["Genus"] == genus]

    species_list = sorted(df_use["Species"].unique())
    opts = [{"label": s, "value": s} for s in species_list]
    return opts, current if current in species_list else (
        species_list[0] if len(species_list) == 1 else None
    )





# -------------------------------------------------------------------
# Callback 2 – whenever any chooser fires, update selected‑species
# -------------------------------------------------------------------
@app.callback(
    Output("selected-species", "data", allow_duplicate=True),
    Input("species-dd", "value"),
    Input("genus-dd",   "value"),
    Input("common-dd",  "value"),
    Input("random-btn", "n_clicks"),
    Input("nav-random-btn", "n_clicks"),
    State("size-toggle",    "value"),
    State("depth-toggle",   "value"),
    State("wiki-toggle",    "value"),
    State("popular-toggle", "value"),
    State("favs-toggle",    "value"),
    State("favs-store",     "data"),
    State("order-lock-state", "data"),
    State("selected-species", "data"),
    prevent_initial_call=True
)
def choose_species(species_val, genus_val, common_val, rnd, rnd_nav,
                   size_val, depth_val,
                   wiki_val, pop_val,
                   fav_val, favs_data, lock_on,
                   current_sel):

    """
    Decide which species string “Genus Species” should be stored in
    `selected-species` whenever *any* of the four selectors fires.

    • genus‑dd / species‑dd pair  → exact match
    • common‑dd                   → value of the dropdown
    • random‑btn                  → random row honouring every active filter:
        – Wiki‑only
        – Popular‑only
        – Favourites
        – Size/Depth navigation toggles
          (requires full depth‑pair or positive Length_cm)
    """
    trig = ctx.triggered_id

    def _emit(new_gs):
        # If it's the same as what we already have, do nothing.
        if (new_gs or "").strip() == (current_sel or "").strip():
            raise PreventUpdate
        return new_gs

    # 1) Random buttons
    if trig in ("random-btn", "nav-random-btn"):
        size_on  = "size"  in size_val
        depth_on = "depth" in depth_val
        df_use = get_filtered_df(size_on, depth_on, wiki_val, pop_val)

        if fav_val and "fav" in fav_val:
            fav_set = set(json.loads(favs_data or "[]"))
            df_use  = df_use[df_use["Genus_Species"].isin(fav_set)]
        if df_use.empty:
            raise PreventUpdate
            
         # ── honour order-lock *only* for nav-random ─────────────
        if trig == "nav-random-btn" and lock_on and current_sel:
            try:
                cur_order = (
                    df_full.loc[df_full["Genus_Species"] == current_sel, "order"]
                    .iloc[0]
                )
                df_use = df_use[df_use["order"] == cur_order]
            except IndexError:
                pass        # keep whole list if lookup fails      

        # Prefer a *different* species; fall back if only one candidate.
        if len(df_use) > 1 and current_sel in set(df_use["Genus_Species"]):
            df_use = df_use[df_use["Genus_Species"] != current_sel]

        row = df_use.sample(1).iloc[0]
        return _emit(f"{row.Genus} {row.Species}")

    # 2) Common-name dropdown
    if trig == "common-dd" and common_val:
        return _emit(common_val)

    # 3) Genus + species pair
    if trig in ("genus-dd", "species-dd") and genus_val and species_val:
        return _emit(f"{genus_val} {species_val}")

    raise PreventUpdate




# --- CITATIONS panel toggle -----------------------------------
@app.callback(
    Output("citations-canvas", "is_open"),
    Input("citations-tab",     "n_clicks"),
    State("citations-canvas",  "is_open"),
    prevent_initial_call=True
)
def toggle_citations(n, is_open):
    if not n:
        raise PreventUpdate
    return not is_open


    
#------ toggle INFO -------

@app.callback(
    Output("info-card",   "style", allow_duplicate=True),
    Output("info-handle", "style"),
    Input("info-close",   "n_clicks"),
    Input("info-handle",  "n_clicks"),
    State("info-card",    "style"),
    prevent_initial_call=True
)
def toggle_info(_, __, card_style):
    show = card_style.get("display") != "none" if card_style else True
    new_card  = {"display":"none"} if show else {"display":"block"}
    new_handle= {"display":"block"} 
    return new_card, new_handle


# --- push citation text when species changes -------------------------------
@app.callback(Output("citation-box", "children"),
              Input("selected-species", "data"),
              State("sound-on", "data")  )
def fill_citation(gs_name, sound_on):
    if not gs_name:
        raise PreventUpdate

    genus, species = gs_name.split(" ", 1)
    row = df_full.loc[df_full["Genus_Species"] == gs_name].iloc[0]

    # ---------- try Wikimedia Commons -------------

    start = time.time()
    skip_bg = gs_name in transp_set
    thumb, author, lic, lic_url, up, ret = get_commons_thumb(
        genus, species, remove_bg=not skip_bg)
    print(f"Image time: {time.time() - start:.2f}s")

    # ---------- build the image block if any ------------
    image_block = []
    if author:
        image_block = [
            html.Span("Image: "), html.Strong(author),
            html.Span(", "),
            html.Span((lic or "") + " "),
            html.A("(license link)", href=lic_url, target="_blank") if lic_url else None,
            html.Span(f" — uploaded {up}, retrieved {ret} from Wikimedia Commons"),
        ]

        # add the rembg citation only when we **really** removed the background
        if gs_name not in transp_set:
            image_block.extend([
                html.Br(), html.Br(),
                html.Span("Background removed using "),
                html.A("rembg", href="https://github.com/danielgatis/rembg", target="_blank"),
                html.Span(", an open‑source background removal tool by Daniel Gatis."),
            ])
        image_block.extend([html.Br(), html.Br()])

    # ---------- Wikipedia text excerpt (always) ----------
    today = datetime.date.today().isoformat()
    wiki_block = [
        html.Span("Text excerpt: Wikipedia — CC BY‑SA 4.0, retrieved "),
        html.Span(today),
        html.Br(), html.Br(),
    ]

    # ---------- now the data‑source line -------------
    if row.get("Database") == 0:
        data_block = [
            html.Span("Size information retrieved from "),
            html.A("Our World in Data", href="https://ourworldindata.org/human-height", target="_blank"),
            html.Span(", depth from "),
            html.A("Divessi", href="https://www.divessi.com/en/blog/Worlds-Most-Incredible-Freediving-Records-9332.html", target="_blank"),
            html.Span(", danger levels from "),
            html.A("Wikipedia", href="https://en.wikipedia.org/wiki/List_of_animals_deadliest_to_humans", target="_blank"),
            html.Span(" and "),
            html.A("Smithsonian Magazine", href="https://www.smithsonianmag.com/science-nature/humans-take-more-wild-species-than-any-other-predator-on-earth-180982478/", target="_blank"),
            html.Span(", and lifespan from "),
            html.A("Cleveland Clinic", href="https://my.clevelandclinic.org/health/articles/lifespan", target="_blank"),
            html.Span(" — retrieved Jul 14 2025"),
        ]
    elif row.get("Database") == -1:
        data_block = [
        html.Span("Depth estimate from "),
        html.A("Maeda‐Obregon et al. (2025)", 
               href="https://doi.org/10.1002/edn3.70147", 
               target="_blank"),
        html.Span(": "),
        html.Em("Persisting at the Edge of Ecological Collapse: The Impact of Urbanization on Fish and Amphibian Communities From Lake Xochimilco."),
        html.Span(" Published in "),
        html.Span("Environmental DNA, Vol. 7"),
        html.Br(), html.Br(),
        html.Span("Size information from "),
        html.A("Wikipedia", 
               href="https://en.wikipedia.org/wiki/Axolotl", 
               target="_blank"),
        html.Span("— retrieved 29 Jul 2025. ")]
    elif row.get("Database") == -2:
        data_block = [
        html.Span("Depth, length, and habitat information from "),
        html.A("Michigan Natural Features Inventory",
               href="https://mnfi.anr.msu.edu/species/description/10841/Necturus-maculosus",
               target="_blank"),
        html.Span("."), html.Br(), html.Br(),
        html.Span("Longevity information from "),
        html.A("National Geographic (archived)",
               href="https://web.archive.org/web/20070614110211/http://animals.nationalgeographic.com/animals/amphibians/mudpuppy.html",
               target="_blank"),
        html.Span(": "),
        html.Em("“Mudpuppies, Mudpuppy Pictures, Mudpuppy Facts.”"),
        html.Span(" Retrieved 18 April 2010.")]
    elif row.get("Database") == -3:
        data_block = []
    elif row.get("Database") == -4:
        data_block = [
        html.Span("Length data from "),
        html.Em("Kitchener, A. (2001). "),
        html.Span("Beavers. Essex: Whittet Books. ISBN 978-1-873580-55-4."),
        html.Br(), html.Br(),
        html.Span("Depth information from "),
        html.A("Graf, P. M. et al. (2017)", 
               href="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5773300/",
               target="_blank"),
        html.Span(": "),
        html.Em("Diving behavior in a free-living, semi-aquatic herbivore, the Eurasian beaver "),
        html.Span("(Castor fiber). "),
        html.Span("Published in "),
        html.Em("Ecology and Evolution, 8(2), 997–1008"),
        html.Span(". DOI: "),
        html.A("10.1002/ece3.3726", 
               href="https://doi.org/10.1002/ece3.3726", 
               target="_blank")]
    else:
        src      = str(row.get("Database", "")).lower()
        slug     = f"{genus}-{species}".replace(" ", "-")
        src_name = "SeaLifeBase" if src == "sealifebase" else "FishBase"
        editors  = (
            "Palomares, M.L.D. and D. Pauly. Editors."
            if src == "sealifebase" else
            "Froese, R. and D. Pauly. Editors."
        )
        cite_url = (
            f"https://www.sealifebase.se/summary/{slug}.html"
            if src == "sealifebase" else
            f"https://www.fishbase.se/summary/{slug}"
        )
        data_block = [
            html.Span(f"Taxonomic information (genus/species), length, habitat, longevity, danger, depth, and additional comments: {editors} "),
            html.A(src_name, href=cite_url, target="_blank"),
            html.Span(" — retrieved 12 Jul 2025."),
        ]


    sound_block = []
    mp3_rel, txt_rel, _ = _sound_paths(genus, species)
    if os.path.exists(txt_rel):
        try:
            with open(txt_rel, "r", encoding="utf-8") as f:
                citation_text = f.read().strip()
            if citation_text:
                url_pattern = r"(https?://\S+|www\.\S+)"
                
                formatted_text = re.sub(
                    url_pattern,
                    lambda m: (
                        f"[Link]({(link := m.group(0).rstrip('.'))})"
                        + ("." if m.group(0).endswith(".") else "")
                    ),
                    citation_text
                )



                sound_block = [
                    html.Br(), html.Br(),
                    html.Strong("Audio: "),
                    dcc.Markdown(formatted_text, dangerously_allow_html=True)
                ]
        except Exception:
            pass

    taxonomy_block=[html.Br(), html.Br(),  html.Span("Taxonomic information (kingdoms/phyla/classes/orders/families): Derived dataset GBIF.org (7 August 2025) Filtered export of GBIF occurrence data.  "), html.A('DOI', href="https://doi.org/10.15468/dd.wbjqgn", target="_blank"),]
    
    soundtrack_block = []
    if sound_on:
        soundtrack_block = [
            html.Br(), html.Br(),
            html.Span(
                "Ambient soundtrack: mix from C0 sound effects retrieved from Pixabay. "
                "uploaded by users freesound_community, TanwerAman, Prem_Adhikary, CalenethLysariel07, DRAGON-STUDIO")]
    
    victoria_block=[html.Br(), html.Br(), html.Span("All other content, including code, background images, animations, and UI design: © 2025 Victoria Tiki"),]

    return image_block + wiki_block + data_block + taxonomy_block + sound_block + soundtrack_block+ victoria_block


# --- populate image + overlay + titles whenever species or units change ----------
from html.parser import HTMLParser

class SimpleHTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []

    def handle_data(self, d):
        self.result.append(d)

    def get_data(self):
        return ''.join(self.result)

def strip_html_tags(text):
    parser = SimpleHTMLStripper()
    parser.feed(text)
    return parser.get_data()



def format_references_as_spans(text):
    # This regex matches both "(something; Ref. 1234)" and plain "Ref. 1234"
    ref_regex = r'\(?Ref(?:s)?\.\s*\d+(?:\s*,\s*\d+)*\)?'

    result = []
    last_index = 0

    for match in re.finditer(ref_regex, text):
        start, end = match.start(), match.end()
        # Append the plain text before the match
        if start > last_index:
            result.append(text[last_index:start])
        # Append the matched reference wrapped in a grey <Span>
        result.append(html.Span(match.group(0), style={"color": "#A0A0A0"}))
        last_index = end

    # Add any remaining text
    if last_index < len(text):
        result.append(text[last_index:])

    return result


def _apply_shared_filters(frame: pd.DataFrame,
                          wiki_val, pop_val, fav_val=None, favs_data=None):
    mask = pd.Series(True, index=frame.index)
    if "wiki" in wiki_val:
        mask &= frame["has_wiki_page"]
    if "pop" in pop_val:
        mask &= frame["Genus_Species"].isin(popular_set)
    if fav_val and "fav" in fav_val:
        fav_set = set(json.loads(favs_data or "[]"))
        mask &= frame["Genus_Species"].isin(fav_set)
    return frame.loc[mask]              # view → O(1) no RAM / time
    

def get_filtered_df(size_on, depth_on, wiki_val, pop_val, seed=None):
    """
    seed is accepted only for backward-compatibility.
    It’s no longer used because RandDepth is pre-computed once per session.
    """
    df_use = _apply_shared_filters(df_full, wiki_val, pop_val)

    # ── SIZE ───────────────────────────────────────────────
    if size_on:
        # require a *real* positive measurement in centimetres
        df_use = df_use[df_use["Length_cm"].notna() & (df_use["Length_cm"] > 0)]

    # ── DEPTH ──────────────────────────────────────────────
    if depth_on:
        df_use = df_use[
            # 1️⃣ commercial pair complete
            (df_use["DepthRangeComShallow"].notna() &
             df_use["DepthRangeComDeep"   ].notna())
            |
            # 2️⃣ generic pair complete
            (df_use["DepthRangeShallow"   ].notna() &
             df_use["DepthRangeDeep"      ].notna())
        ]

    return df_use






def replace_links(text):
    # Replace any existing HTML links with 'Link' (preserving the href)
    return re.sub(
        r'<a\s+[^>]*href=[\'"]([^\'"]+)[\'"][^>]*>.*?</a>',
        lambda m: f'<a href="{m.group(1)}" target="_blank" style="text-decoration: none; color: inherit;">Link</a>',
        text
    )


def _units(value_bool):
    """False = metric,  True = imperial (because pill right = ft)."""
    return "imperial" if value_bool else "metric"

def _sound_paths(genus: str, species: str):
    base = f"{genus}_{species}".replace(" ", "_")
    base_dir = os.path.join("assets", "species", "sound")

    candidates = [f"{base}.ogg", f"{base}.mp3", f"{base}.wav"]

    audio_rel = ""
    audio_url = ""

    if USE_R2:
        # Check R2 for whichever extension exists
        for fname in candidates:
            rel_path = f"assets/species/sound/{fname}"
            if _r2_has_path(rel_path):
                audio_url = "/" + rel_path        # keep leading slash; media_url() will rewrite
                break
    else:
        # Local dev: use the filesystem like before
        for fname in candidates:
            rel = os.path.join(base_dir, fname)
            if os.path.exists(rel):
                audio_rel = rel
                audio_url = f"/assets/species/sound/{fname}"
                break

    txt_rel = os.path.join(base_dir, f"{base}.txt")
    return audio_rel, txt_rel, audio_url




# NEW: sound – show/hide icon and set audio src when species changes
# Species sound: keep your existing filename/extension detection,
# only rewrite the base to R2 when USE_R2=True.
@app.callback(
    Output("sound-handle",  "style"),
    Output("species-audio", "src"),
    Input("selected-species", "data"),
    prevent_initial_call=True
)
def update_sound_controls(gs_name):
    if not gs_name:
        raise PreventUpdate

    genus, species = gs_name.split(" ", 1)

    # your original resolver (unchanged)
    audio_rel, txt_rel, rel_url = _sound_paths(genus, species)

    # if no local match → hide, exactly like before
    if not rel_url:
        return {"display": "none"}, ""

    # minimal change: when R2 is on, just change the base
    url = media_url(rel_url.lstrip("/")) if USE_R2 else rel_url
    return {"display": "block"}, url



# sound – client-side click handler to play the audio
app.clientside_callback(
    """
    function(n) {
        if (!n) { return window.dash_clientside.no_update; }
        const el = document.getElementById("species-audio");
        if (el) {
            if (!el.paused) {
                el.pause();  // pause if already playing
            } else {
                el.currentTime = 0;
                el.play();   // play from start if paused
            }
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("js-trigger", "children"),
    Input("sound-handle", "n_clicks"),
    prevent_initial_call=True
)

def dagre_layout():
    return {
        "name": "dagre",
        "rankDir": "TB",
        "nodeDimensionsIncludeLabels": True,
        "rankSep": 30,
        "nodeSep": 60,
        "fit": True,              # keep
        "padding": 20,            # a bit more breathing space
        "animate": False,
    }




@app.callback(
    Output("order-lock-label", "children"),
    Output("order-lock-label", "className"),
    Input("order-lock-state",  "data"),      # ON / OFF toggle
    Input("selected-species",  "data"),      # species changed
    State("order-lock-label",  "className"), # (kept for symmetry; not required)
    prevent_initial_call=True
)
def update_order_lock_label(locked, species_id, old_class):
    base_class = "order-lock-label"
    if not locked or not species_id:
        return "", base_class               # hide when OFF

    order = df_full.loc[df_full["Genus_Species"] == species_id, "order"]
    order_name = order.iloc[0] if not order.empty else "?"
    return f"Navigating among {order_name} only", base_class + " active"

# --- Auto-release order lock on cross-order selection --------------------------
@app.callback(
    Output("order-lock-state", "data", allow_duplicate=True),
    Output("order-lock-btn",   "className", allow_duplicate=True),
    Input("selected-species",  "data"),
    State("order-lock-state",  "data"),
    State("depth-order-store-locked", "data"),
    prevent_initial_call=True
)
def _auto_release_order_lock(new_gs, lock_on, locked_list):
    # If the order lock is ON but the newly selected species isn't in the
    # currently locked set (derived from the previous species' order),
    # automatically turn the lock OFF so the user can roam freely.
    if not lock_on or not new_gs:
        raise PreventUpdate
    try:
        if isinstance(locked_list, (list, tuple)) and locked_list and new_gs not in locked_list:
            return False, "nav-icon lock-icon"  # unlock + de-highlight
    except Exception:
        pass
    raise PreventUpdate



@app.callback(
    Output("species-img",  "src"),
    Output("species-img",  "alt"),
    Output("info-content", "children"),
    Input("selected-species", "data"),
    Input("units-toggle",     "value")     # value is True/False
)
def update_image(gs_name, units_bool):
    units = _units(units_bool)             # ← translate once
    habitat_defs = {
        "benthopelagic":     "swims near the sea floor and in open water",
        "pelagic-oceanic":   "lives in the open ocean, away from land or sea floor",
        "reef-associated":   "lives near coral reefs",
        "benthic":           "lives on or in the sea floor",
        "pelagic":           "inhabits open water, not near the bottom",
        "demersal":          "lives close to the bottom, often resting there",
        "pelagic-neritic":   "lives in coastal open water, above the continental shelf",
        "bathydemersal":     "inhabits deep waters near the sea floor",
        "sessile":           "attached to a surface and doesn’t move",
        "bathypelagic":      "inhabits the open‑waters at the ocean’s mid‑depths (roughly 1 000–4 000 m)",
        "others":             "other habitats, may not be strictly aquatic"
    }


    if not gs_name:
        raise PreventUpdate

    genus, species = gs_name.split(" ", 1)
    summary, url = get_blurb(genus, species, 4)
    # ── skip bg‐removal for any species on the blacklist
    skip_bg = gs_name in transp_set
    thumb, *_ = get_commons_thumb(
        genus, species,
        remove_bg=not skip_bg
    )

    # -------- pull the chosen row once -------
    #row = df_wiki.loc[df_wiki["Genus_Species"] == gs_name].iloc[0]
    
    row_full = df_full.loc[df_full["Genus_Species"] == gs_name]
    if row_full.empty:                 
        raise PreventUpdate
    row = row_full.iloc[0]

    # ---------- LENGTH ----------
    if units == "metric":
        if pd.notna(row.Length_cm):
            if row.Length_cm >= 100:
                max_length = f"{row.Length_cm/100:.2f} m"
            else:
                max_length = f"{row.Length_cm:.1f} cm"
        else:
            max_length = "?"
    else:
        if pd.notna(row.Length_in):
            if row.Length_in >= 12:
                max_length = f"{row.Length_in/12:.2f} ft"
            else:
                max_length = f"{row.Length_in:.1f} in"
        else:
            max_length = "?"

    # --- Richer tooltip & text depending on CommonLength ----------------------
    ltype_max = row.get("LTypeMaxM")
    comm_cm   = row.get("CommonLength")
    has_common = pd.notna(comm_cm)

    # → 1. tooltip
    if row.get("Database") == 0:
        length_tooltip = "Global average height"
    elif has_common and pd.notna(ltype_max):
        length_tooltip = f"({ltype_max}, male)"
    elif pd.notna(ltype_max):
        length_tooltip = f"Maximum recorded length of species ({ltype_max}, male)"
    else:
        length_tooltip = "Maximum recorded length of species (male)"

    # → 2. display string
    if has_common:
        if units == "metric":
            if comm_cm >= 100:
                common_str = f"{comm_cm/100:.2f} m"
            else:
                common_str = f"{comm_cm:.1f} cm"
        else:
            comm_in     = cm_to_in(comm_cm)
            common_str  = f"{comm_in/12:.2f} ft" if comm_in >= 12 else f"{comm_in:.1f} in"

        length_display = f"max {max_length}, common {common_str}"
    else:
        length_display = max_length


    if row.get("Database") == 0:
        length_tooltip = "Global average height"
        depth_tooltip  = "Unassisted freediving record depth"
    else:
        depth_tooltip  = (
            "Pelagica shows you this species at a random depth within this range. "
            "Note that this depth range doesn't always reflect the species' diving behavior — it may instead represent the maximum depth of the body of water it inhabits (see citation)."
            #//" E.g., the southern elephant seal is listed to 8000 m (the maximum depth of the South Atlantic) but only dives to a maximum of 2,388 m."
        )
        
    # ---------- DEPTH (prefers the …Com* pair) ----------
    use_com = row.DepthComPreferred
    if units == "metric":
        shallow = row.DepthRangeComShallow if use_com else row.DepthRangeShallow
        deep    = row.DepthRangeComDeep    if use_com else row.DepthRangeDeep
        unit    = " m"
    else:
        shallow = row.DepthRangeComShallow_ft if use_com else row.DepthRangeShallow_ft
        deep    = row.DepthRangeComDeep_ft    if use_com else row.DepthRangeDeep_ft
        unit    = " ft"

    depth = (
        f"{int(shallow)}–{int(deep)}{unit}"
        if pd.notna(shallow) and pd.notna(deep) else "?"
    )

    # ---------- titles ----------
    common = row.FBname
    titles = [html.H1(common), html.H4(gs_name)]

    # ---------- compose info card ----------
    info_lines = [
        html.H5(common, style={"marginBottom": "0.2rem"}),
        html.H6(gs_name, style={"marginTop": "0", "marginBottom": "1rem"}),
        html.Span([
            html.Span("length",
                      title=length_tooltip,
                      style={"textDecoration": "underline dashed"}),
            f": {length_display}  |  ",
            html.Span("depth",
                      title=depth_tooltip,
                      style={"textDecoration": "underline dashed"}),
            f": {depth}"
        ])]


    # ---------- WATER TYPE + PELAGIC ZONE ----------
    if row.get("Fresh") == 1:
        salinity = "freshwater"
    elif row.get("Saltwater") == 1:
        salinity = "saltwater"
    elif row.get("Brack") == 1:
        salinity = "brackish water"
    else:
        salinity = None

    zone = row.get("DemersPelag")
    zone_desc = habitat_defs.get(str(zone).lower()) if pd.notna(zone) else None

    # ───── HABITAT LINE: salinity + zone (like "pelagic") ─────
    habitat_bits = []

    if salinity:
        habitat_bits.append(salinity)

    if zone:
        if habitat_bits:
            habitat_bits.append(", ")

        if zone_desc:
            habitat_bits.append(
                html.Span(zone, title=zone_desc, style={"textDecoration": "underline dashed"})
            )
        else:
            habitat_bits.append(zone)

    if habitat_bits:
        info_lines.extend([
            html.Br(),
            html.Span(["habitat: "] + habitat_bits)
        ])




    # ---------- LONGEVITY ----------
    if pd.notna(row.get("LongevityWild")):
        info_lines.extend([
            html.Br(),
            html.Span(f"lifespan: {int(row.LongevityWild)} years")
        ])


        
        
    # ---------- DANGEROUS ----------
    if pd.notna(row.get("Dangerous")):
        info_lines.append(html.Span(f" | danger level: "))

        # now append just the value, underlining only when Database==0
        if row.get("Database") == 0:
            info_lines.append(html.Span(
                str(row.Dangerous),
                title=(
                    "drives the largest annual biomass loss "
                    "of any species"#, causes more human deaths "
                    #"than any other species except mosquitoes"
                ),
                style={"textDecoration": "underline dashed"}
            ))
        else:
            info_lines.append(html.Span(str(row.Dangerous)))


    # ---------- BLURB ----------
    info_lines.extend([
        html.Br(), html.Br(),
        html.Span(summary or "No summary available."), html.Br(),
        html.A("Wikipedia ↗", href=url, target="_blank"),
        html.Br(), html.Br()
    ])

        

    # ------------------- MAIN LOGIC --------------------
    comments = row.get("Comments")
    src      = str(row.get("Database", "")).lower()

    if pd.notna(comments) and comments.strip():
        slug     = f"{genus}-{species}".replace(" ", "-")
        src_name = "SeaLifeBase" if src=="sealifebase" else "FishBase"
        cite_url = (
          f"https://www.sealifebase.se/summary/{slug}.html"
          if src=="sealifebase"
          else f"https://www.fishbase.se/summary/{slug}"
        )

        raw       = comments.strip()
        cleaned   = strip_html_tags(raw)
        truncated = " ".join(cleaned.split()[:100]) + "…"
        children  = format_references_as_spans(truncated)

        info_lines.extend([
            html.Br(),
            html.Span(children),
            html.Br(),
            html.A(f"{src_name} ↗", href=cite_url, target="_blank")
        ])

    # If no thumbnail was found, use the placeholder but make the URL
    # unique per species so <img src> actually *changes* between picks.
    # ---- build img_src -------------------------------------------------
    slug     = f"{genus}_{species}".replace(" ", "_")
    raw_src  = thumb or "/assets/img/placeholder_fish.webp"
    base_src = to_cdn(raw_src)

    # Add a species-specific key for cached images *and* for the placeholder
    if raw_src.startswith("/cached-images/") or raw_src == "/assets/img/placeholder_fish.webp":
        sep     = "&" if "?" in base_src else "?"
        img_src = f"{base_src}{sep}gs={slug}"
    else:
        img_src = base_src



    alt_text = f"Image of {row.FBname or ''} ({gs_name})".strip()
    gc.collect()
    return img_src, alt_text, info_lines






# ---- slide citations tab (now mirrors settings) -------------------
@app.callback(
    Output("citations-tab", "style"),
    Input("citations-canvas", "is_open")
)
def slide_citation_tab(opened):
    if opened:
        return {"right": f"{CITATION_W}px"}   # push left by its own width
    return {"right": "0px"}





# -------------------------------------------------------------------
# Sync all four dropdowns whenever *selected-species* changes
# -------------------------------------------------------------------
@app.callback(
    Output("common-dd",  "value", allow_duplicate=True),
    Output("genus-dd",   "value", allow_duplicate=True),
    Output("species-dd", "value", allow_duplicate=True),
    Output("family-dd",  "value", allow_duplicate=True),   # NEW
    Output("order-dd",   "value", allow_duplicate=True),   # NEW
    Input("selected-species", "data"),
    prevent_initial_call=True
)
def sync_dropdowns(gs_name):
    if not gs_name:
        raise PreventUpdate                    # safeguard

    genus, species = gs_name.split(" ", 1)

    # df_full already carries GBIF taxonomy columns (order / family / …)
    row     = df_full.loc[df_full["Genus_Species"] == gs_name].iloc[0]   # ← always exactly 1 row
    family  = row.family
    order_  = row.order

    common  = f"{genus} {species}"             # or row.FBname if you prefer
    return common, genus, species, family, order_




@app.callback(
    Output("taxa-row", "style"),
    Input("taxa-toggle", "value"),
)
def _toggle_taxa_row(val):
    return {"display": "block"} if "taxa" in val else {"display": "none"}


# export
@app.callback(Output("fav-dl","data"),
              Input("fav-export","n_clicks"),
              State("favs-store","data"), prevent_initial_call=True)
def do_export(n,favs):
    if not n or not favs: raise PreventUpdate
    txt = base64.b64encode(favs.encode()).decode()
    return dict(content=txt, filename="pelagica_favs.txt", base64=True)

# import
@app.callback(Output("favs-store","data",allow_duplicate=True),
              Input("fav-upload","contents"), prevent_initial_call=True)
def do_import(contents):
    if not contents: raise PreventUpdate
    txt = base64.b64decode(contents.split(",")[1]).decode()
    return txt

@app.callback(
    Output("common-dd", "options"),
    Output("common-opt-cache", "data"),
    Output("common-dd", "value"),       # ← keep this output
    Input("common-dd",  "search_value"),
    Input("wiki-toggle","value"),
    Input("popular-toggle","value"),
    Input("favs-toggle","value"),
    State("favs-store","data"),
    State("common-dd","value"),
    State("common-opt-cache", "data"),
)
def filter_common(search, wiki_val, pop_val, fav_val, favs_data, current, cached):

    df_use = _apply_shared_filters(df_light, wiki_val, pop_val, fav_val, favs_data)

    # ── 1. user isn’t typing → keep everything as is ─────────────────
    if not search or len(search) < 2:
        return no_update, cached, current

    # ── 2. build a suggestion list (≤50) ─────────────────────────────
    mask = df_use["dropdown_label"].str.contains(search, case=False, na=False)
    matches = df_use[mask].head(50)

    options = [
        {"label": r.dropdown_label, "value": r.Genus_Species}
        for _, r in matches.iterrows()
    ]

    # ── 3. skip update if options identical ──────────────────────────
    if options == cached:
        return no_update, cached, no_update

    # 2) If the callback was triggered by typing, leave `value` untouched
    triggered_prop = next(iter(ctx.triggered_prop_ids))
    if triggered_prop == "common-dd.search_value":
        return options, options, no_update   # ← stops the field from resetting

    # 3) Otherwise (filters toggled, etc.) update `value` if it became invalid
    value = current if current in {o["value"] for o in options} else None
    return options, options, value





# toggle the advanced-filters box
@app.callback(
    Output("adv-box", "style"),
    Input("open-settings-btn", "n_clicks"),   
    State("adv-box", "style"),
    prevent_initial_call=True
)
def toggle_advanced(n, style):
    hidden = style and style.get("display") == "none"
    return {} if hidden else {"display": "none"}

@app.callback(
    Output("fav-modal", "is_open"),
    Input("fav-menu-btn", "n_clicks"),
    Input("fav-modal",    "is_open"),   # ← state turns into an Input
    prevent_initial_call=True
)
def toggle_fav_modal(btn_clicks, modal_open):
    # if the heart was clicked, open; otherwise pass the current state through
    if ctx.triggered_id == "fav-menu-btn":
        return True
    return modal_open      # keeps whatever the X sets (False when dismissed)




@app.callback(
    Output("search-panel",  "className"),
    Output("search-handle", "className"),
    Input("search-handle",  "n_clicks"),
    State("search-panel",   "className"),
    prevent_initial_call=True
)
def toggle_search_box(n, current_class):
    current_class = current_class or ""
    is_open = "open" in current_class

    new_class = current_class.replace(" open", "") if is_open else current_class + " open"
    new_toggle_class = "search-handle collapsed" if is_open else "search-handle"

    return new_class.strip(), new_toggle_class

@app.callback(
    Output("search-panel",  "className", allow_duplicate=True),
    Output("search-handle", "className", allow_duplicate=True),
    Input("mobile-close-btn", "n_clicks"),
    State("search-panel",   "className"),
    prevent_initial_call=True
)
def close_search_mobile(n, current_class):
    if not n:
        raise PreventUpdate

    current_class = current_class or ""
    if "open" in current_class:
        new_class = current_class.replace(" open", "")
        return new_class.strip(), "search-handle collapsed"
    raise PreventUpdate
    

@app.callback(
    Output("eligible-depth-bounds-all",    "data"),
    Output("eligible-depth-bounds-locked", "data"),
    Input("wiki-toggle",      "value"),
    Input("popular-toggle",   "value"),
    Input("favs-toggle",      "value"),
    Input("order-lock-state", "data"),   # True/False
    State("favs-store",       "data"),
    State("selected-species", "data"),
)
def build_eligible_bounds(wiki_val, pop_val, fav_val, lock_on, favs_data, current):
    # 1) full eligible set (IGNORE lock here)
    df_all = _apply_shared_filters(df_full, wiki_val, pop_val, fav_val, favs_data)

    # choose Com bounds when present, else raw
    sh_all = df_all["DepthRangeComShallow"].where(df_all["DepthRangeComShallow"].notna(),
                                                  df_all["DepthRangeShallow"])
    dp_all = df_all["DepthRangeComDeep"].where(df_all["DepthRangeComDeep"].notna(),
                                               df_all["DepthRangeDeep"])

    meta_all = (df_all.assign(_sh=sh_all, _dp=dp_all)[["Genus_Species", "_sh", "_dp", "order"]]
                      .dropna())
    meta_all = meta_all[meta_all["_dp"] >= meta_all["_sh"]]

    # 2) locked subset (APPLY lock only for stepping)
    if lock_on and current in df_full["Genus_Species"].values:
        current_order = df_full.loc[df_full["Genus_Species"].eq(current), "order"].iloc[0]
        df_locked = meta_all[meta_all["order"].eq(current_order)]
    else:
        df_locked = meta_all

    # Compact lists: [gs, sh, dp] (and a second list for locked)
    all_list    = [[gs, float(sh), float(dp)] for gs, sh, dp, _ in meta_all.itertuples(index=False, name=None)]
    locked_list = [[gs, float(sh), float(dp)] for gs, sh, dp, _ in df_locked.itertuples(index=False, name=None)]

    return all_list, locked_list



app.clientside_callback(
    """
    function(boundsAll, boundsLocked, seed){
      // bounds*: [[gs, shallow, deep], ...]
      if (!Array.isArray(boundsAll) || !boundsAll.length) {
        return [null, null, null];
      }

      // FNV-1a 32-bit
      function h32(s){
        var h = 2166136261>>>0;
        for (var i=0;i<s.length;i++){ h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
        return h>>>0;
      }
      // Mulberry32 PRNG
      function mulberry32(a){
        return function(){
          var t = a += 0x6D2B79F5;
          t = Math.imul(t ^ t >>> 15, t | 1);
          t ^= t + Math.imul(t ^ t >>> 7, t | 61);
          return ((t ^ t >>> 14) >>> 0) / 4294967296;
        };
      }

      var base = (seed|0)>>>0;

      // Override species → force 0–5 m
      var overrides = new Set([
        "Delphinus delphis",
        "Homo sapiens",
        "Mirounga leonina",
        "Lobodon carcinophaga",
        "Stenella coeruleoalba",
        "Odobenus rosmarus",
        "Stenella frontalis",
        "Pagophilus groenlandicus",
        "Stenella longirostris",
        "Stenella attenuata",
        "Grampus griseus",
        "Tursiops truncatus"
      ]);

      var map   = {};
      var arrAll = [];

      // Build biased depths for ALL eligible species (quick jumps ignore lock)
      for (var i=0; i<boundsAll.length; i++){
        var gs = boundsAll[i][0];
        var s  = +boundsAll[i][1];
        var d  = +boundsAll[i][2];

        // overrides → clamp bounds to 0..5 m
        if (overrides.has(gs)) { s = 0.0; d = 5.0; }

        // skip invalid ranges
        if (!(d >= s)) { continue; }

        // per-species RNG seeded by (session seed XOR hash(gs))
        var rng = mulberry32((base ^ h32(gs))>>>0);
        var u = rng();

        var depth;
        if (s < 200) {
          // shallow bias: u^1.3
          depth = s + Math.pow(u, 1.3) * (d - s);
        } else if (s < 2000) {
          // medium bias: uniform
          depth = s + u * (d - s);
        } else {
          // deep bias: 1 - (1-u)^2
          depth = s + (1 - Math.pow(1 - u, 2.0)) * (d - s);
        }

        map[gs] = depth;
        arrAll.push([gs, depth]);
      }

      // Sort ALL by depth → used by quick jumps (filters only)
      arrAll.sort(function(a,b){ return a[1]-b[1]; });
      var orderAll = arrAll.map(function(x){ return x[0]; });

      // Locked order = same ranking but filtered to the locked set
      var lockedSet = new Set((boundsLocked||[]).map(function(x){ return x[0]; }));
      var orderLocked = orderAll.filter(function(gs){ return lockedSet.has(gs); });

      return [map, orderAll, orderLocked];
    }
    """,
    [
      Output("rand-depth-map",          "data", allow_duplicate=True),
      Output("depth-order-store-all",   "data", allow_duplicate=True),
      Output("depth-order-store-locked","data", allow_duplicate=True),
    ],
    Input("eligible-depth-bounds-all",    "data"),
    Input("eligible-depth-bounds-locked", "data"),
    State("rand-seed", "data"),
    prevent_initial_call=True
)



app.clientside_callback(
    """
    function(nUp, nDown, orderAll, orderLocked, lockOn, current){
      var trig = (dash_clientside.callback_context.triggered[0]||{}).prop_id || "";
      var order = (lockOn && Array.isArray(orderLocked) && orderLocked.length)
                  ? orderLocked : orderAll;
      if (!Array.isArray(order) || !order.length) return window.dash_clientside.no_update;

      var idx = current ? order.indexOf(current) : -1;
      if (idx < 0) idx = 0;

      var dir = trig.startsWith("up-btn") ? -1 : +1;
      var next = order[(idx + dir + order.length) % order.length];
      if (next === current) return window.dash_clientside.no_update;
      return next;
    }
    """,
    Output("selected-species", "data", allow_duplicate=True),
    Input("up-btn",   "n_clicks"),
    Input("down-btn", "n_clicks"),
    State("depth-order-store-all",    "data"),
    State("depth-order-store-locked", "data"),
    State("order-lock-state",         "data"),
    State("selected-species",         "data"),
    prevent_initial_call=True,
)


app.clientside_callback(
    """
    function(nShallow, nDeep, orderAll, current){
      var trig = (dash_clientside.callback_context.triggered[0]||{}).prop_id || "";
      if (!Array.isArray(orderAll) || !orderAll.length) return window.dash_clientside.no_update;

      var target = trig.startsWith("shallowest-btn") ? orderAll[0] : orderAll[orderAll.length-1];
      if (target === current) return window.dash_clientside.no_update;
      return target;
    }
    """,
    Output("selected-species", "data", allow_duplicate=True),
    Input("shallowest-btn", "n_clicks"),
    Input("deepest-btn",    "n_clicks"),
    State("depth-order-store-all","data"),
    State("selected-species",     "data"),
    prevent_initial_call=True,
)


app.clientside_callback(
    """
    function(gs, depthMap){
      if (!gs || !depthMap) return window.dash_clientside.no_update;
      var d = depthMap[gs];
      return (typeof d === "number") ? d : window.dash_clientside.no_update;
    }
    """,
    Output("depth-store", "data", allow_duplicate=True),
    Input("selected-species", "data"),
    State("rand-depth-map",  "data"),
    prevent_initial_call=True,
)

'''app.clientside_callback(
    """
    function(bounds, seed){
      // bounds: [[gs, sh, dp], ...] from server (only when filters change)
      if (!Array.isArray(bounds) || !bounds.length) { return [null, null]; }

      // simple per-string 32-bit hash (FNV-1a)
      function h32(s){ var h=2166136261>>>0;
        for (var i=0;i<s.length;i++){ h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
        return h>>>0;
      }
      // mulberry32 PRNG
      function mulberry32(a){ return function(){
        var t=a+=0x6D2B79F5; t=Math.imul(t^t>>>15, t|1);
        t^= t+Math.imul(t^t>>>7, t|61); return ((t^t>>>14)>>>0)/4294967296;
      };}

      var base = (seed|0)>>>0;  // your session seed
      var map = {};             // {gs: randDepth}
      var arr = [];             // [ [gs, randDepth], ... ]

      for (var i=0;i<bounds.length;i++){
        var gs = bounds[i][0], sh = +bounds[i][1], dp = +bounds[i][2];
        if (!isFinite(sh) || !isFinite(dp) || dp < sh) continue;
        var rng  = mulberry32((base ^ h32(gs))>>>0);  // per-species stable RNG
        var u    = rng();
        var d    = sh + u*(dp - sh);                 // uniform in [sh, dp]
        map[gs]  = d;
        arr.push([gs, d]);
      }

      // depth order for fast stepping & quick jumps
      arr.sort(function(a,b){ return a[1]-b[1]; });
      var order = arr.map(function(x){ return x[0]; });

      return [map, order];
    }
    """,
    Output("rand-depth-map",     "data", allow_duplicate=True),
    Output("depth-order-store",  "data"),
    Input("eligible-depth-bounds","data"),
    State("rand-seed",            "data"),
    prevent_initial_call="initial_duplicate"   # ← add this line
)'''





# ──────────────────────────────────────────────────────────────
# A) Client‑side toggle (runs in the browser)
# ──────────────────────────────────────────────────────────────
# Client-side: toggle favourite, persist locally AND log anonymously to server
app.clientside_callback(
    """
    function(n, favs_json, species_id) {
        if (n === undefined || !species_id) {
            return window.dash_clientside.no_update;
        }

        // local fav set
        const favs = new Set(JSON.parse(favs_json || "[]"));
        const wasFav = favs.has(species_id);
        if (wasFav) { favs.delete(species_id); } else { favs.add(species_id); }

        const filled   = !wasFav;
        const newClass = filled ? "heart-icon filled" : "heart-icon";
        const newGlyph = filled ? "♥" : "♡";

        // GDPR-safe anonymous session id in localStorage
        try {
            let sid = localStorage.getItem("pelagica_sid");
            if (!sid) {
                sid = (crypto && crypto.randomUUID) ? crypto.randomUUID()
                                                    : (Date.now().toString(36) + Math.random().toString(36).slice(2));
                localStorage.setItem("pelagica_sid", sid);
            }
            fetch("/fav/toggle", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({ sid: sid, species: species_id, state: filled ? 1 : 0 })
            }).catch(()=>{ /* best-effort; ignore network errors */ });
        } catch (_) { /* ignore */ }

        return [JSON.stringify([...favs]), newClass, newGlyph];
    }
    """,
    [
        Output("favs-store", "data"),
        Output("fav-handle", "className", allow_duplicate=True),
        Output("fav-handle", "children",  allow_duplicate=True),
    ],
    Input("fav-handle", "n_clicks"),
    [
        State("favs-store",     "data"),
        State("selected-species","data"),
    ],
    prevent_initial_call=True
)




# ──────────────────────────────────────────────────────────────
# B) Python refresh  (runs when you change species)
# ──────────────────────────────────────────────────────────────




@app.callback(
    Output("compare-store", "data", allow_duplicate=True),
    Input("compare-handle", "n_clicks"),
    State("compare-store", "data"),
    prevent_initial_call=True
)
def toggle_size_overlay(_, is_on):
    # first click → True, then simply flip the bool
    return not (is_on or False)



@app.callback(
    Output("fav-handle", "className", allow_duplicate=True),
    Output("fav-handle", "children",  allow_duplicate=True),
    Input("selected-species", "data"),
    State("favs-store", "data"),
    prevent_initial_call=True
)
def refresh_fav_icon(gs_name, favs_json):
    if not gs_name:
        raise PreventUpdate

    favs   = set(json.loads(favs_json or "[]"))
    filled = gs_name in favs
    return (
        "heart-icon filled" if filled else "heart-icon",
        "♥" if filled else "♡"
    )






@app.callback(
    Output("rand-seed", "data"),
    Input("rand-seed", "data"),          # triggers on first page load
    prevent_initial_call=False,
)
def init_seed(cur):
    # If a seed already exists in *this tab*, keep it → map stays stable.
    return cur if cur is not None else secrets.randbits(32)




# ───────── client‑side: push depth to viewer ─────────
app.clientside_callback(
    """
    function (depth, flag) {
      // Ignore until we have a real number
      if (typeof depth !== "number" || !isFinite(depth)) {
        return window.dash_clientside.no_update;
      }
      const skip = !(Array.isArray(flag) && flag.length);

        // 🔊 Pre-fade the audio TOWARD the target band immediately,
        // so the multi-second fade is already underway during the visual tween.
        try {
          const last = (typeof window.pelagicaLastDepth === "number") ? window.pelagicaLastDepth : 0;
          const band = d => (d >= 2000 ? "deep" : (d >= 20 ? "mid" : "surf"));
          if (window.pelagicaAudio && band(last) !== band(depth)) {
            window.pelagicaAudio.preFadeToward(depth);
          }
        } catch (e) {}

        // ▶️ now kick off the visual tween in the iframe
          if (window.dash_clientside?.bridge?.sendDepth) {
          window.dash_clientside.bridge.sendDepth(depth, skip);
      }
      return window.dash_clientside.no_update;
    }
    """,
    Output("depth-iframe", "title"),        # dummy
    Input("depth-store",    "data"),
    State("instant-toggle", "value"),
)





# ─── client‑side bridge for animationDone → anim‑done store ────────
app.clientside_callback(
    """
    function (_, existing) {                // _  = dummy input
        if (!window._animHooked) {
            window.addEventListener("message", e => {
                if (e.data && e.data.type === "animationDone") {
                    /* write True into the dcc.Store without a round‑trip */
                    const storeEl = document.querySelector("#anim-done");
                    if (storeEl && storeEl.setProps) { storeEl.setProps({data: true}); }
                }

            });
            window._animHooked = true;
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("anim-done", "data"),
    Input("depth-iframe", "src"),      # fires once (page‑load)
    State("anim-done",   "data")       # <‑‑ added so arg‑count == 2
)

# Put this near your other clientside callbacks in app.py
app.clientside_callback(
    """
    function (gs) {
        if (!gs) return window.dash_clientside.no_update;
        return `waiting for ${gs} to arrive`;
    }
    """,
    Output("load-message", "children"),
    Input("selected-species", "data"),
    prevent_initial_call=True,
)



# -------------------------------------------------------------------
# Size‑axis navigation (left / right)
# -------------------------------------------------------------------
@app.callback(
    Output("selected-species", "data", allow_duplicate=True),

    # triggers
    Input("next-btn",  "n_clicks"),
    Input("prev-btn",  "n_clicks"),

    # filters
    State("size-toggle",      "value"),
    State("depth-toggle",     "value"),
    State("wiki-toggle",      "value"),
    State("popular-toggle",   "value"),
    State("favs-toggle",      "value"),
    State("favs-store",       "data"),

    # order-lock state
    State("order-lock-state", "data"),

    # context
    State("selected-species", "data"),
    State("rand-seed",        "data"),
    prevent_initial_call=True
)
def step_size(n_next, n_prev,
              size_val, depth_val, wiki_val, pop_val,
              fav_val, favs_data,
              lock_on,                # ← comes from order-lock store
              current, seed):

    if ctx.triggered_id not in ("prev-btn", "next-btn"):
        raise PreventUpdate


    # ---- base dataframe after all UI filters ----------------------
    size_on  = True
    depth_on = False
    df_use = get_filtered_df(size_on, depth_on,
                             wiki_val, pop_val, seed)

    # ---- favourites filter ----------------------------------------
    if fav_val and "fav" in fav_val:
        fav_set = set(json.loads(favs_data or "[]"))
        df_use  = df_use[df_use["Genus_Species"].isin(fav_set)]

    # ---- limit to current order when lock is ON -------------------
    if lock_on:
        try:
            # safest: look up order in the full taxonomy table
            order = df_full.loc[df_full["Genus_Species"] == current, "order"].iloc[0]
            df_use = df_use[df_use["order"] == order]
        except IndexError:
            pass  # current not in df_full – ignore

    if df_use.empty:
        raise PreventUpdate

    # ---- rank by length and step ±1 -------------------------------
    df_use  = df_use.sort_values(["Length_cm", "Length_in"])
    species = df_use["Genus_Species"].tolist()
    if current not in species:
        current = species[0]

    idx = species.index(current)
    idx = (idx - 1) % len(species) if ctx.triggered_id == "prev-btn" \
         else (idx + 1) % len(species)

    new_sel = species[idx]
    if new_sel == current:
        raise PreventUpdate
    return new_sel


# -------------------------------------------------------------------
# Depth‑axis navigation (up / down)
# -------------------------------------------------------------------
'''@app.callback(
    Output("selected-species", "data", allow_duplicate=True),

    # triggers
    Input("up-btn",   "n_clicks"),
    Input("down-btn", "n_clicks"),

    # filter toggles
    State("size-toggle",      "value"),
    State("depth-toggle",     "value"),
    State("wiki-toggle",      "value"),
    State("popular-toggle",   "value"),
    State("favs-toggle",      "value"),
    State("favs-store",       "data"),

    # NEW  ➜  order-lock state
    State("order-lock-state", "data"),

    # context
    State("selected-species", "data"),
    State("rand-depth-map",   "data"),
    prevent_initial_call=True
)
def step_depth(n_up, n_down,
               size_val, depth_val, wiki_val, pop_val,
               fav_val, favs_data,
               lock_on,               # <- order-lock flag
               current, depth_map):

    if ctx.triggered_id not in ("up-btn", "down-btn"):
        raise PreventUpdate


    # ------------------------------------------------------------------
    # build dataframe with all active filters
    # ------------------------------------------------------------------
    size_on  = False
    depth_on = True            # depth axis is ON
    df_use = get_filtered_df(size_on, depth_on,
                             wiki_val, pop_val)

    # favourites filter
    if fav_val and "fav" in fav_val:
        fav_set = set(json.loads(favs_data or "[]"))
        df_use  = df_use[df_use["Genus_Species"].isin(fav_set)]

    # order-lock filter
    if lock_on:
        try:
            order = df_full.loc[df_full["Genus_Species"] == current, "order"].iloc[0]
            df_use = df_use[df_use["order"] == order]
        except IndexError:
            pass   # current not found – ignore

    if df_use.empty:
        raise PreventUpdate

    # ------------------------------------------------------------------
    # inject session depths, sort, and step ±1
    # ------------------------------------------------------------------
    df_use = with_session_depth(df_use, depth_map or {})
    df_use = df_use.sort_values("RandDepth")

    species = df_use["Genus_Species"].tolist()
    if current not in species:
        current = species[0]

    idx = species.index(current)
    idx = (idx - 1) % len(species) if ctx.triggered_id == "up-btn" \
         else (idx + 1) % len(species)

    # ... keep existing code that computes idx ...
    new_sel = species[idx]
    if new_sel == current:
        raise PreventUpdate
    return new_sel'''




# -------------------------------------------------------------------
# Quick‑jump buttons (deepest / shallowest / largest / smallest)
# -------------------------------------------------------------------
# Quick jumps
'''@app.callback(
    Output("selected-species", "data", allow_duplicate=True),
    Input("deepest-btn",    "n_clicks"),
    Input("shallowest-btn", "n_clicks"),
    Input("largest-btn",    "n_clicks"),
    Input("smallest-btn",   "n_clicks"),
    State("wiki-toggle",    "value"),
    State("popular-toggle", "value"),
    State("favs-toggle",    "value"),
    State("favs-store",     "data"),
    State("selected-species","data"),
    State("rand-depth-map", "data"),      # ← add this
    prevent_initial_call=True
)
def jump_to_extremes(n_deep, n_shallow, n_large, n_small,
                     wiki_val, pop_val, fav_val, favs_data,
                     current, depth_map):

    trig = ctx.triggered_id
    if trig is None:
        raise PreventUpdate

    size_on  = trig in ("largest-btn", "smallest-btn")
    depth_on = trig in ("deepest-btn", "shallowest-btn")

    df_use = get_filtered_df(size_on, depth_on, wiki_val, pop_val)

    # per-session depths for the depth cases
    if depth_on:
        df_use = with_session_depth(df_use, depth_map or {})

    if fav_val and "fav" in fav_val:
        fav_set = set(json.loads(favs_data or "[]"))
        df_use  = df_use[df_use["Genus_Species"].isin(fav_set)]
    if df_use.empty:
        raise PreventUpdate

    if trig in ("largest-btn", "smallest-btn"):
        df_use = df_use.sort_values(["Length_cm", "Length_in"])
        row    = df_use.iloc[-1] if trig == "largest-btn" else df_use.iloc[0]
    else:
        df_use = df_use.sort_values("RandDepth")
        row    = df_use.iloc[-1] if trig == "deepest-btn" else df_use.iloc[0]


    new_gs = row["Genus_Species"]
    if new_gs == (current or ""):
        # already at that extreme → don't reload / re-arm image watcher
        raise PreventUpdate
    return new_gs'''
    
# REPLACE the old jump_to_extremes with this size-only version.
@app.callback(
    Output("selected-species", "data", allow_duplicate=True),
    Input("largest-btn",    "n_clicks"),
    Input("smallest-btn",   "n_clicks"),
    State("wiki-toggle",    "value"),
    State("popular-toggle", "value"),
    State("favs-toggle",    "value"),
    State("favs-store",     "data"),
    State("selected-species","data"),
    prevent_initial_call=True
)
def jump_to_size_extremes(n_large, n_small,
                          wiki_val, pop_val, fav_val, favs_data,
                          current):
    trig = ctx.triggered_id
    if trig is None:
        raise PreventUpdate

    # Use your existing helper; depth flag is False here.
    df_use = get_filtered_df(size_on=True, depth_on=False,
                             wiki_val=wiki_val, pop_val=pop_val)

    # Apply favs if enabled
    if fav_val and "fav" in fav_val:
        fav_set = set(json.loads(favs_data or "[]"))
        df_use = df_use[df_use["Genus_Species"].isin(fav_set)]
    if df_use.empty:
        raise PreventUpdate

    # Sort by size; keep your existing tie-breaker
    df_use = df_use.sort_values(["Length_cm", "Length_in"], na_position="last")

    row = df_use.iloc[-1] if trig == "largest-btn" else df_use.iloc[0]
    new_gs = row["Genus_Species"]

    if new_gs == (current or ""):
        raise PreventUpdate
    return new_gs





# ── show/hide size arrows ─────────────────────────────────────────────
@app.callback(
    Output("prev-wrap", "style"),
    Output("next-wrap", "style"),
    Input("selected-species", "data"),
    Input("size-toggle",      "value"),
    prevent_initial_call=True
)
def toggle_size_wrap(gs, size_val):
    if gs: #and "size" in size_val:
        style = {"opacity": "1", "pointerEvents": "auto"}
    else:
        style = {"opacity": "0.3", "pointerEvents": "none"}
    return style, style


# ── show/hide depth arrows ────────────────────────────────────────────
@app.callback(
    Output("up-wrap",   "style"),
    Output("down-wrap", "style"),
    Input("selected-species", "data"),
    Input("depth-toggle",     "value"),
    prevent_initial_call=True
)
def toggle_depth_wrap(gs, depth_val):
    # when depth‐comparison is on and we have a species, make arrows fully visible…
    if gs:# and "depth" in depth_val:
        style = {"opacity": "1", "pointerEvents": "auto"}
    # …otherwise “grey out” (low opacity + no clicks)
    else:
        style = {"opacity": "0.3", "pointerEvents": "none"}
    return style, style


@app.callback(
    Output("nav-info-text", "style"),
    Input("nav-info-icon", "n_clicks"),
    State("nav-info-text", "style"),
    prevent_initial_call=True
)
def toggle_nav_info(n, style):
    if style and style.get("display") == "none":
        return {"display": "block", "marginTop": "0.5rem", "opacity": 0.85}
    return {"display": "none"}


@app.callback(
    Output("scale-tooltip", "children"),
    Output("scale-tooltip", "key"),
    Input("selected-species", "data"),
    Input("compare-store", "data"),
    prevent_initial_call=True
)
def update_scale_tooltip(gs_name, is_on):
    if not gs_name or not is_on:
        raise PreventUpdate

    genus, species = gs_name.split(" ", 1)
    row = df_full.loc[df_full["Genus_Species"] == gs_name].iloc[0]

    if pd.isna(row.Length_cm):
        raise PreventUpdate

    species_len = row.Length_cm
    best = min(_scale_db, key=lambda d: abs(d["length_cm"] - species_len))
    desc = best["desc"]

    # unique key → forces rerender of tooltip
    return (
        f"Compare maximum size (approximate)", # to a {desc} (approximate)",
        f"{genus}_{species}"
    )


@app.callback(
    Output("sizecmp-img", "src"),
    Output("sizecmp-img", "style"),
    Output("sizecmp-img", "title"),
    Input("selected-species", "data"),
    Input("compare-store", "data"),          # existing on/off for overlay
    Input("human-scale-toggle", "value"),    # NEW
    prevent_initial_call=True
)
def update_sizecmp(gs_name, is_on, human_val):
    # OFF or no species → hide the silhouette
    if not gs_name or not is_on:
        return "", {"display": "none"}, ""

    genus, species = gs_name.split(" ", 1)
    row = df_full.loc[df_full["Genus_Species"] == gs_name].iloc[0]
    length = row.Length_cm
    if pd.isna(length) or length == 0:
        return "", {"display": "none"}, ""

    # Pick database: humans if toggled, else the default scale objects.
    use_human = isinstance(human_val, (list, tuple)) and ("human" in human_val)
    db = _humanscale_db if (use_human and _humanscale_db) else _scale_db

    species_len = float(length)
    best = min(db, key=lambda d: abs(d["length_cm"] - species_len))
    scale = best["length_cm"] / species_len

    style = {
        "position": "absolute",
        "left": "50%", "top": "50%",
        "transform": "translate(-50%, -50%)",
        "width": f"{scale*100:.2f}%",
        "zIndex": 3,
        "opacity": 0.85,
        "pointerEvents": "auto",
        "cursor": "pointer",
    }
    title = f"this is a {best['desc']}"
    return best["path"], style, title


@app.callback(
    Output("arrow-img", "style"),
    Input("selected-species", "data"),
    Input("compare-store",    "data"),
    prevent_initial_call=True
)
def toggle_arrow(gs_name, is_on):
    if not gs_name or not is_on:
        return {"display": "none"}
    return {
        "position": "absolute",
        "left": "50%", "top": "50%",
        "transform": "translate(-50%, -50%)",
        "width": "100%", "opacity": 0.9,
        "pointerEvents": "none", "zIndex": 2
    }


@app.callback(
    Output("order-lock-state", "data"),
    Output("order-lock-btn",   "className"),
    Input("order-lock-btn", "n_clicks"),
    State("order-lock-state", "data"),
    prevent_initial_call=True
)
def toggle_order_lock(n, locked):
    locked = not locked
    cls = "nav-icon lock-icon" + (" active" if locked else "")
    return locked, cls

@app.callback(
    Output("selected-species", "data", allow_duplicate=True),
    Input("url", "search"),
    prevent_initial_call=True
)
def load_from_query(search):
    if not search:
        raise PreventUpdate          # no query-string
    qs = parse_qs(search.lstrip("?"))
    raw = (qs.get("species") or [None])[0]
    if not raw:
        raise PreventUpdate          # parameter absent

    # Accept “Genus_species” or “Genus%20species”
    gs = raw.replace("_", " ").replace("%20", " ")
    return gs.strip()

app.clientside_callback(
    """
    function(gs) {
        if (!gs) { return window.dash_clientside.no_update; }
        const slug = gs.replace(/\\s+/g, "_");
        const url  = new URL(window.location);
        url.searchParams.set("species", slug);
        window.history.replaceState({}, "", url);
        return "";          // something to write
    }
    """,
    Output("url-trigger", "children"),    # ← changed
    Input("selected-species", "data")
)

# Update document.title when a species is chosen
app.clientside_callback(
    """
    function(gs){
      if(!gs){ return window.dash_clientside.no_update; }
      document.title = gs + " - Pelagica";
      return window.dash_clientside.no_update;
    }
    """,
    Output("seo-trigger", "children"),
    Input("selected-species", "data"),
    prevent_initial_call=True
)


#app.run(host="0.0.0.0", port=8050, debug=True)  #change to false later                

app.title = "Pelagica - The Aquatic Life Atlas"
app.index_string = '''
<!DOCTYPE html>
<html lang="en">
  <head>
        {%metas%}
        <title>{%title%}</title>
        <link rel="icon" href="/favicon.ico" type="image/x-icon">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link rel="preconnect" href="https://pub-197edf068b764f1c992340f063f4f4f1.r2.dev" crossorigin>

    <!-- Canonical -->
    <link rel="canonical" href="https://pelagica.victoriatiki.com/"/>

    <!-- Basic SEO -->
    <meta name="description" content="Pelagica - explore aquatic biodiversity by depth, size, and taxonomy with curated images and soundscapes." />

    <!-- Open Graph -->
    <meta property="og:title" content="Pelagica - The Aquatic Life Atlas" />
    <meta property="og:author" content="Victoria Tiki" />
    <meta property="og:description" content="Explore aquatic species by depth, size, and taxonomy. Smooth descent animation, curated images, and more." />
    <meta property="og:type" content="website" />
    <meta property="og:url" content="https://pelagica.victoriatiki.com/" />
    <meta property="og:image" content="https://pelagica.victoriatiki.com/assets/og/pelagica_og_1200x630.jpg" />
    <meta property="og:image:width"  content="1200" />
    <meta property="og:image:height" content="630" />

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="Pelagica - The Aquatic Life Atlas" />
    <meta name="twitter:description" content="Explore marine species by depth, size, and taxonomy." />
    <meta name="twitter:image" content="https://pelagica.victoriatiki.com/assets/og/pelagica_1200x630.jpg" />

    <!-- Structured data -->
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "WebSite",
      "name": "Pelagica",
      "url": "https://pelagica.victoriatiki.com/",
      "potentialAction": {
        "@type": "SearchAction",
        "target": "https://pelagica.victoriatiki.com/?species={species}",
        "query-input": "required name=species"
      }
    }
    </script>

    {%css%}
  </head>
  <body>
    {%app_entry%}
    <footer>
      {%config%}
      {%scripts%}
      {%renderer%}
    </footer>
  </body>
</html>
'''

# change the decorator to include compare-store
@app.callback(
    Output("tree-panel", "style"),
    Output("tree-plot",  "figure"),
    Output("compare-store", "data", allow_duplicate=True),   # NEW
    Input("tree-handle",      "n_clicks"),    # toggle button
    Input("selected-species", "data"),        # species picker
    State("tree-panel",       "style"),
    prevent_initial_call=True,
)
def toggle_or_update_tree(n_clicks, species, style):
    if not species:
        raise PreventUpdate

    triggered = ctx.triggered_id
    is_open   = style and style.get("display") != "none"

    # User clicked the 🧬 handle
    if triggered == "tree-handle":
        if is_open:                           # ── close panel ──
            return {**(style or {}), "display": "none"}, no_update, no_update
        # ── open panel ──
        fig = make_tree_figure(df_full, species)
        
        
        # closing the size-compare overlay when opening the tree
        return {**(style or {}), "display": "block"}, fig, False   # ← NEW

    # Species changed while panel already open: refresh figure only
    if is_open and triggered == "selected-species":
        fig = make_tree_figure(df_full, species)
        return no_update, fig, no_update

    raise PreventUpdate

@app.callback(
    Output("tree-panel", "style", allow_duplicate=True),
    Input("compare-store", "data"),
    State("tree-panel", "style"),
    prevent_initial_call=True
)
def hide_tree_when_comparing(is_on, style):
    # If size-compare is ON and the tree is visible, hide the tree.
    if is_on and style and style.get("display") != "none":
        return {**style, "display": "none"}
    raise PreventUpdate


def make_tree_figure(df, target_species):
    from collections import defaultdict
    from functools import lru_cache
    import textwrap
    import plotly.graph_objects as go

    # ---- Build elements & metadata (from taxonomic_tree.py) ----
    els, root = build_taxonomy_elements(df, target_species)

    node_meta = {}
    edges = []
    for e in els:
        d = e.get("data", {})
        if "source" in d and "target" in d:
            edges.append((d["source"], d["target"]))
        else:
            nid = d.get("id")
            if nid:
                node_meta[nid] = {
                    "label": d.get("label", nid),   # may contain sci/common; we’ll format below
                    "rank":  d.get("rank"),
                    "kind":  d.get("kind"),         # "focus" for the current species
                    # if taxonomic_tree.py provided sci/common separately, use them:
                    "sci":   d.get("sci"),
                    "common":d.get("common"),
                }

    # Infer root if not provided
    children = {v for _, v in edges}
    if not root:
        parents = [u for u, _ in edges if u not in children]
        root = parents[0] if parents else (next(iter(node_meta)) if node_meta else None)

    # ---- Graph structure ----
    children_of = defaultdict(list)
    parent_of = {}
    for u, v in edges:
        children_of[u].append(v)
        parent_of[v] = u

    rank_order = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
    rank_index = {r: i for i, r in enumerate(rank_order)}

    def get_rank(n):
        r = node_meta.get(n, {}).get("rank")
        if r in rank_index:
            return r
        p = parent_of.get(n)
        if p:
            pi = rank_index.get(get_rank(p))
            if pi is not None and pi + 1 < len(rank_order):
                return rank_order[pi + 1]
        return "species"

    # Deterministic child ordering
    for u in children_of:
        children_of[u].sort(key=lambda c: (rank_index.get(get_rank(c), 999),
                                           node_meta.get(c, {}).get("label", c)))

    # ---- Tidy layout (top-to-bottom) ----
    @lru_cache(None)
    def leaf_count(n):
        ch = children_of.get(n, [])
        if not ch: return 1
        return sum(leaf_count(c) for c in ch)

    X_SPACING = 150     # tweak if you want wider sibling spacing
    Y_SPACING = 50    # tweak if you want taller row spacing

    x_pos, y_pos = {}, {}
    next_leaf_col = 0

    def layout(n):
        nonlocal next_leaf_col
        ri = rank_index.get(get_rank(n), len(rank_order) - 1)
        y_pos[n] = -ri * Y_SPACING
        ch = children_of.get(n, [])
        if not ch:
            x_pos[n] = next_leaf_col * X_SPACING
            next_leaf_col += 1
        else:
            for c in ch:
                layout(c)
            xs = [x_pos[c] for c in ch]
            x_pos[n] = sum(xs) / len(xs)

    if root: layout(root)

    # ---- After layout() has been called ----
    species_nodes = [n for n in node_meta if get_rank(n) == "species" and n in y_pos]

    for i, n in enumerate(sorted(species_nodes, key=lambda x: x_pos[x])):
        # Alternate between no offset and +species_offset
        offset = 14 if i % 2 == 0 else -14
        y_pos[n] += offset
        
        
    # ---- Helpers for labels/hover ----
    def sci_text(meta):
        # Prefer explicit scientific name if provided
        if meta.get("sci"):
            return meta["sci"]
        lbl = meta.get("label", "") or ""
        # Split off any “sci — common” or “sci (common)” patterns
        for sep in [" — ", " - ", " – "]:
            if sep in lbl:
                return lbl.split(sep, 1)[0].strip()
        if "(" in lbl and lbl.endswith(")"):
            return lbl[:lbl.rfind("(")].strip()
        return lbl.strip()

    def infer_common_from_label(label: str | None) -> str | None:
        if not label:
            return None
        lbl = label
        for sep in [" — ", " - ", " – "]:
            if sep in lbl:
                tail = lbl.split(sep, 1)[1].strip()
                return tail if tail else None
        if "(" in lbl and lbl.endswith(")"):
            return lbl[lbl.rfind("(")+1:-1].strip() or None
        return None
    
    def hover_text(n, meta):
        r = get_rank(n)
        sci = meta.get("sci") or sci_text(meta)

        if r == "species":
            # species: use provided "common" if present; else infer from label
            common = meta.get("common") or infer_common_from_label(meta.get("label", ""))
            if common:
                return f"<b>{sci}</b><br><i>{common}</i>"
            return f"<b>{sci}</b>"

        # higher taxa: look up from COMMON_NAMES
        cmn = COMMON_NAMES.get(sci)
        if cmn:
            return f"<b>{r.title()}</b><br>{sci}<br><i>{cmn}</i>"
        else:
            return f"<b>{r.title()}</b><br>{sci}"

    def wrap(label, width=14):
        return "<br>".join(textwrap.wrap(label, width=width, break_long_words=False)) if label else ""


    # ---- Build traces ----
    # Edges
    edge_x, edge_y = [], []
    for u, v in edges:
        if u in x_pos and v in x_pos:
            edge_x += [x_pos[u], x_pos[v], None]
            edge_y += [y_pos[u], y_pos[v], None]

    # Split nodes into three groups so text color can match marker color
    species_focus = {"x": [], "y": [], "text": [], "hover": [], "gs": []}
    species_other = {"x": [], "y": [], "text": [], "hover": [], "gs": []}
    higher_taxa   = {"x": [], "y": [], "text": [], "hover": [], "gs": []}

    for n, meta in node_meta.items():
        if n not in x_pos: continue
        r = get_rank(n)
        sci = sci_text(meta)
        label = wrap(sci, width=14) if r == "species" else sci

        if r == "species" and meta.get("kind") == "focus":
            species_focus["x"].append(x_pos[n])
            species_focus["y"].append(y_pos[n])
            species_focus["text"].append(label)
            species_focus["hover"].append(hover_text(n, meta))
            species_focus["gs"].append(sci)
        elif r == "species":
            species_other["x"].append(x_pos[n])
            species_other["y"].append(y_pos[n])
            species_other["text"].append(label)
            species_other["hover"].append(hover_text(n, meta))
            species_other["gs"].append(sci)
        else:
            higher_taxa["x"].append(x_pos[n])
            higher_taxa["y"].append(y_pos[n])
            higher_taxa["text"].append(label)
            higher_taxa["hover"].append(hover_text(n, meta))
            higher_taxa["gs"].append(None)


    # Common layout bits
    def nodes_trace(group, marker_color, text_color, text_size, name):
        return go.Scatter(
            x=group["x"], y=group["y"],
            mode="markers+text",
            name=name,
            hovertext=group["hover"],
            hoverinfo="text",
            text=group["text"],
            customdata=group.get("gs"),          # ← canonical "Genus species"
            textposition="bottom center",
            textfont=dict(color=text_color, size=text_size),
            marker=dict(size=10, color=marker_color),
            cliponaxis=False,
            showlegend=False,
        )


    fig = go.Figure(
        data=[
            go.Scatter(
                x=edge_x, y=edge_y,
                mode="lines",
                line=dict(width=1.5, color="rgba(255,255,255,0.2)"),
                hoverinfo="skip",
                showlegend=False,
            ),
            nodes_trace(higher_taxa, marker_color="#bfbfbf", text_color="#bfbfbf", text_size=12, name="Higher taxa"),
            nodes_trace(species_other, marker_color="#2ecc71", text_color="#2ecc71", text_size=11, name="Species"),
            nodes_trace(species_focus, marker_color="#ffd166", text_color="#ffd166", text_size=11, name="Current"),
        ],
        layout=go.Layout(
            margin=dict(t=20, b=40, l=30, r=30),
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            showlegend=False,
            hovermode="closest",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#ffffff"),
        ),
    )
    

    # ---- Padding so nothing is cut off ----
    all_x = higher_taxa["x"] + species_other["x"] + species_focus["x"]
    all_y = higher_taxa["y"] + species_other["y"] + species_focus["y"]
    if all_x and all_y:
        pad_x = 0.7 * X_SPACING
        pad_y = 0.9 * Y_SPACING
        fig.update_xaxes(range=[min(all_x) - pad_x, max(all_x) + pad_x])
        fig.update_yaxes(range=[min(all_y) - pad_y, max(all_y) + pad_y])

        # Let the figure height match content; the panel will scroll if needed
        content_height = (max(all_y) - min(all_y)) + 2 * pad_y + 80
        fig.update_layout(height=max(400, int(content_height)))

    return fig


SOW_PINNED_SPECIES = os.getenv("SOW_PINNED_SPECIES", "Grimpoteuthis discoveryi")  # Oarfish

@app.callback(
    Output("sow-thumb","src"),
    Output("sow-common","children"),
    Output("sow-scientific","children"),
    Output("sow-note","children"),
    Output("sow-title","children"),
    Input("sow-refresh","n_intervals"),
    prevent_initial_call=False
)
def update_species_of_week(_):
    # Production mode: weekly window (Mon–Sun, UTC)
    now = utcnow()
    SOW_LIVE_START_UTC = datetime.datetime(2025, 9, 1, 0, 0, tzinfo=datetime.timezone.utc)
    #cutoff = next_monday_start(now) + datetime.timedelta(days=7)
    cutoff = SOW_LIVE_START_UTC

    # Until Sept 1 → show pinned pick
    if now < cutoff and SOW_PINNED_SPECIES:
        sp = SOW_PINNED_SPECIES
        genus, species = sp.split(" ", 1)
        skip_bg = sp in transp_set
        thumb, *_ = get_commons_thumb(genus, species, remove_bg=not skip_bg)
        thumb = thumb or "/assets/img/placeholder_fish.webp"
        common = COMMON_NAMES.get(sp, "")
        rollout_note = f"Inaugural pick — live weekly rotation starts {cutoff.date().isoformat()} (UTC) based on your most favourited species"
        base = to_cdn(thumb or "/assets/img/placeholder_fish.webp")
        if base.startswith("/cached-images/"):
            base = f"{base}{'&' if '?' in base else '?'}gs={genus}_{species}"
        return (base, common, sp, rollout_note, "Species of the Week")


    # Live weekly favourite w/ suppression + tie-breakers
    record_weekly_winner_if_missing()  # harmless idempotent call
    sp, _scores = top_species(debug=False, option="ever_favved")  # production

    if not sp:
        return ("/assets/img/placeholder_fish.webp", "", "—", "No favourites recorded last week", "Species of the Week")

    genus, species = sp.split(" ", 1)
    skip_bg = sp in transp_set
    thumb, *_ = get_commons_thumb(genus, species, remove_bg=not skip_bg)
    base = to_cdn(thumb or "/assets/img/placeholder_fish.webp")
    if base.startswith("/cached-images/"):
        base = f"{base}{'&' if '?' in base else '?'}gs={genus}_{species}"
    return (base, common, sp, note, "Species of the Week")




@app.callback(
    Output("selected-species", "data", allow_duplicate=True),
    Input("sow-card", "n_clicks"),
    State("sow-scientific", "children"),
    prevent_initial_call=True
)
def pick_sow(n, gs):
    if not n or not gs or gs == "—":
        raise PreventUpdate
    return gs

app.clientside_callback(
    """
    function (href) {
      if (!href) return window.dash_clientside.no_update;

      const hasSpecies = new URL(href).searchParams.has("species");
      if (hasSpecies) {
        // Don’t touch anything if a species is explicitly requested
        return [
          window.dash_clientside.no_update,
          window.dash_clientside.no_update,
          window.dash_clientside.no_update
        ];
      }
      // Clean restart defaults (leave depth unset)
        return [
          window.dash_clientside.no_update,  // depth-store (do not force 0)
          {},                                // rand-depth-map
          false                              // compare-store
        ];
    }
    """,
    Output("depth-store",    "data", allow_duplicate=True),
    Output("rand-depth-map", "data", allow_duplicate=True),
    Output("compare-store",  "data", allow_duplicate=True),
    Input("url", "href"),
    prevent_initial_call="initial_duplicate"
)

app.clientside_callback(
    """
    function(n, cur) {
        if (typeof n === "undefined") return cur || false;
        return !cur;
    }
    """,
    Output("sound-on", "data"),
    Input("depth-sound-btn", "n_clicks"),
    State("sound-on", "data"),
    prevent_initial_call=True
)

# Merge toggle + depth, but only touch audio on TOGGLE
app.clientside_callback(
    """
    function(on, depth) {
        const ctx = dash_clientside && dash_clientside.callback_context;
        const trig = (ctx && ctx.triggered && ctx.triggered[0] && ctx.triggered[0].prop_id) || "";
        const byToggle = trig.indexOf("sound-on.") === 0;

        // cache depth for the bridge
        if (typeof depth === "number") window.pelagicaLastDepth = depth;

        // publish toggle state for the bridge
        window.pelagicaSoundOn = !!on;

        // UI affordance
        const btn = document.getElementById("depth-sound-btn");
        if (btn) btn.style.opacity = on ? "1" : "0.5";

        // audio elements
        const ids = [
          "snd-surface-a","snd-surface-b",
          "snd-epi2meso-a","snd-epi2meso-b",
          "snd-abyss2hadal-a","snd-abyss2hadal-b"
        ];
        const els = ids.map(id => document.getElementById(id)).filter(Boolean);
        if (!els.length) return "";

        // ⬇️ Only on TOGGLE do we mute/play. On depth changes, do NOTHING here.
        if (byToggle) {
          if (!on) {
            els.forEach(a => { if (a){ a.volume = 0; if (!a.paused) a.pause(); }});
            return "";
          }
          // turn ON: start all at volume 0 (bridge will fade)
          els.forEach(a => { if (a){ a.volume = 0; if (a.paused) a.play().catch(()=>{}); }});
        }

        return "";
    }
    """,
    Output("js-audio-sink", "children"),
    Input("sound-on", "data"),
    Input("depth-store", "data"),
)



app.clientside_callback(
    f"""
    function(on) {{
      const CDN = "{R2_BASE if USE_R2 else ''}";   // empty→local, R2 base→prod
      const map = {{
        "snd-surface-a":     (CDN||"") + "/assets/sound/surface.mp3",
        "snd-surface-b":     (CDN||"") + "/assets/sound/surface.mp3",
        "snd-epi2meso-a":    (CDN||"") + "/assets/sound/epi_to_meso.mp3",
        "snd-epi2meso-b":    (CDN||"") + "/assets/sound/epi_to_meso.mp3",
        "snd-abyss2hadal-a": (CDN||"") + "/assets/sound/abyss_to_hadal.mp3",
        "snd-abyss2hadal-b": (CDN||"") + "/assets/sound/abyss_to_hadal.mp3",
        "snd-meso2bath-a":   (CDN||"") + "/assets/sound/meso_to_bath.mp3",
        "snd-meso2bath-b":   (CDN||"") + "/assets/sound/meso_to_bath.mp3",
        "snd-bath2abyss-a":  (CDN||"") + "/assets/sound/bath_to_abyss.mp3",
        "snd-bath2abyss-b":  (CDN||"") + "/assets/sound/bath_to_abyss.mp3"
      }};
      Object.keys(map).forEach(id => {{
        const el = document.getElementById(id);
        if (!el) return;
        if (on) {{
          if (!el.dataset.srcset) {{
            el.src = map[id];
            el.dataset.srcset = "1";
            el.load();
          }}
        }} else {{
          try {{ el.pause(); }} catch(e) {{}}
          el.removeAttribute("src");
          el.load();
          delete el.dataset.srcset;
        }}
      }});
      return on ? "on" : "off";
    }}
    """,
    Output("audio-src-sink", "data"),
    Input("sound-on", "data"),
)



app.clientside_callback(
    """
    function(clickData, currentSpecies) {
        if (!clickData) return window.dash_clientside.no_update;
        const pt = (clickData.points && clickData.points[0]) || null;
        if (!pt) return window.dash_clientside.no_update;

        // 1) Prefer canonical sci name from customdata
        let gs = pt.customdata;
        if (Array.isArray(gs)) gs = gs[0];

        // 2) Fallback: extract from <b>...</b> in hovertext
        if (typeof gs !== "string" || !gs.includes(" ")) {
            const ht = (pt.hovertext || "").toString();
            const m = ht.match(/<b>([^<]+)<\\/b>/i);
            if (m) gs = m[1].trim();
        }

        // 3) Last resort: parse the rendered label text
        if (typeof gs !== "string" || !gs.includes(" ")) {
            let label = (pt.text || "").toString()
                .replace(/<br\\s*\\/?>(?!$)/gi, " ")  // undo wrap safely
                .replace(/<[^>]+>/g, "")
                .replace(/\\s+/g, " ")
                .trim();
            const parts = label.split(" ");
            if (parts.length >= 2) {
                gs = parts.slice(0, 2).join(" ");
            } else {
                return window.dash_clientside.no_update;
            }
        }

        if (currentSpecies && currentSpecies.trim() === gs) {
            return window.dash_clientside.no_update;
        }

        const url = new URL(window.location);
        url.searchParams.set("species", gs.replace(/\\s+/g, "_"));
        window.history.replaceState({}, "", url);
        window.dispatchEvent(new Event("popstate"));
        return "";
    }
    """,
    Output("tree-click-trigger", "children"),
    Input("tree-plot", "clickData"),
    State("selected-species", "data"),
    prevent_initial_call=True
)




if __name__ == "__main__" and os.getenv("USE_DEV_SERVER", "0") == "1":
    app.run_server(debug=True, port=8050)
