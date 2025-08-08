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
from flask import send_from_directory

import pandas as pd, random, datetime
import dash_cytoscape as cyto
import numpy as np 
import json, base64   
import glob
import gc
import re
import time

from src.process_data import load_species_data, load_homo_sapiens, load_name_table, cm_to_in,load_species_with_taxonomy
from src.wiki import get_blurb, get_commons_thumb      
from src.utils import assign_random_depth
from src.taxonomic_tree import build_taxonomy_elements
import os

cyto.load_extra_layouts()
print(f"BOOT: __name__={__name__} USE_DEV_SERVER={os.getenv('USE_DEV_SERVER')}")


def with_session_depth(df_use, depth_map):
    return df_use.assign(RandDepth=df_use["Genus_Species"].map(depth_map))
    
# --- Pre‑index scale images ------------------------------------
_scale_db = []
_pat = re.compile(r'(.+?)_(\d+(?:p\d+)?)(cm|m)\.png$')

for p in glob.glob("assets/species/scale/*.png"):
    name = os.path.basename(p)
    m = _pat.match(name)
    if not m:
        continue
    desc, num, unit = m.groups()
    num = float(num.replace('p', '.'))
    length_cm = num if unit == "cm" else num * 100
    _scale_db.append({
        "path": f"/assets/species/scale/{name}",
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
app = Dash(__name__, external_stylesheets=external_stylesheets)
server = app.server

@app.server.route('/cached-images/<path:filename>')
def serve_cached_images(filename):
    return send_from_directory('image_cache', filename)
    
@app.server.route("/viewer/<path:filename>")
def serve_viewer_file(filename):
    return send_from_directory("depth_viewer", filename)

@app.server.route('/favicon.ico')
def serve_favicon():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'favicon.ico')
    
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
        html.Div(
            [
                html.Img(src="/assets/img/logo_pelagica_colour.webp",
                         style={"height": "50px"}),
                html.Span("The Aquatic Life Atlas",
                          className="tagline",
                          style={"marginLeft": ".5rem", "fontSize": ".9rem",
                                 "fontWeight": 500, "color": "#f5f5f5"})
            ],
            style={"display": "flex", "alignItems": "center"}
        ),

        # 2. spacer
        html.Div(style={"flex": "1"}),

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
                     placeholder="Common name…", className="dash-dropdown",clearable=True, searchable=True, persistence=True,persistence_type="session")
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
    
    html.Div("Limits the list to ~ 1,500 curated species (faster loading).", className="settings-note"),
    
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
    children=html.Div(id="citation-box", style={"whiteSpace": "pre-wrap"})
)



# -------------- taxonomic tree ----------------

taxonomic_tree = html.Div(
    id="tree-panel",
    className="glass-panel",
    style={
    "display": "none",
    "position": "absolute",
    "inset": "0",          # fill the image wrapper width exactly
    "zIndex": 1,           # above image/handles
    "padding": "0rem",
    "boxSizing": "border-box",
    },
    children=[
        cyto.Cytoscape(
            id="tree-graph",
            elements=[],

            stylesheet = [
                # Base node: tiny dot + white label below (larger font)
                {"selector": "node", "style": {
                    "width": 8, "height": 8,
                    "background-opacity": 0.95,
                    "border-width": 0,
                    "label": "data(label)",
                    "color": "#fff",
                    "font-size": 17,  
                    "min-zoomed-font-size":15,
                    "font-weight": 600,# larger, as requested
                    "text-outline-width": 2,
                    "text-outline-color": "rgba(0,0,0,.55)",
                    "text-halign": "center",
                    "text-valign": "top",         # label below the dot
                    "text-margin-y": 8,
                    "text-wrap": "wrap",
                    "text-max-width": 170,
                    "text-outline-width": 2,      # soft glow for contrast
                    "text-outline-color": "rgba(0,0,0,0.45)"
                }},
                

                # Focus species
                {"selector": '[kind = "focus"]', "style": {
                    "background-color": "#ffd166",
                    "color" : "#ffd166",
                    "font-weight": 700,
                    "color": "#ffd166",          # label *also* gold
                    "width": 10, "height": 10
                }},
                # Example species
                {"selector": '[kind = "example"]', "style": {
                    "background-color": "#64d2ff",
                    "color": "#64d2ff",
                    "color": "#64d2ff"
                }},


                # Lineage taxon nodes (genus/family/order/class/phylum/kingdom)
                {"selector": '[kind = "taxon"]', "style": {
                    "background-color": "#bfbfbf"
                }},

                # Optional rank tints (subtle)
                {"selector": '[rank = "family"]',  "style": {"background-color": "#a6a6a6"}},
                {"selector": '[rank = "order"]',   "style": {"background-color": "#8c8c8c"}},
                {"selector": '[rank = "class"]',   "style": {"background-color": "#737373"}},
                {"selector": '[rank = "phylum"]',  "style": {"background-color": "#595959"}},
                {"selector": '[rank = "kingdom"]', "style": {"background-color": "#404040"}},

                # Edges
                {"selector": "edge", "style": {
                    "curve-style": "bezier",
                    "width": 1.6,
                    "line-color": "rgba(255,255,255,0.65)"
                }},],


            style={"width": "100%", "height": "min(65vh, 700px)", "display": "block", "margin": "0 auto"}  # will wrapper width
        )
    ]
)


# --------------------------------------------------------------------
#  Centre-page flex wrapper
# --------------------------------------------------------------------

centre_flex = html.Div(id="page-centre-flex", children=[
    html.Div(id="image-wrapper", children=[

        # this div now contains the image AND the up/down buttons
        html.Div(id="image-inner", children=[
            html.Img(id="species-img"),
            html.Img( id="arrow-img",src="/assets/species/scale/arrow.png",style={
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
               href="https://victoriatiki.com/about/?theme=themed",
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
feedback_link=html.A("give feedback", href="https://forms.gle/YuUFrYPmDWsqyHdt7", target="_blank", style={"textDecoration": "none", "color": "inherit", "cursor": "pointer"})

#  Assemble Layout
app.layout = dbc.Container([
    search_panel,
    invisible_toggles, 
    search_handle,
    dcc.Store(id="rand-seed", storage_type="session"),
    
    top_bar,
    
    fav_modal,

    #settings_panel,

    # -- side tabs, rendered once and slid by callbacks --
    html.Div("citations",      id="citations-tab", className="side-tab"),
    html.Div(feedback_link,   id="bug-tab",       className="side-tab"),

    html.Div(centre_flex, id="main-content", style={"display": "none"}),
    center_message,
    
    nav_panel,
    dcc.Store(id="order-lock-state", data=False, storage_type="session"),
    
    html.Iframe(id="depth-iframe",src="/viewer/index.html",
            style={"width": "100%", "height": "100vh", "border": "none"},
        ),
    dcc.Store(id="anim-done", data=False, storage_type="session"),
    dcc.Store(id="rand-depth-map", storage_type="session"),
    
    depth_store,


    footer,
    
    
    
    html.Div(id="js-trigger", style={"display": "none"}),
    dcc.Store(id="selected-species", data=None),
    dcc.Store(id="favs-store",storage_type="local"),      # persists in localStorage
    dcc.Store(id="compare-store", data=False, storage_type="session"),
    dcc.Store(id="common-opt-cache", data=[]),
    


    citations_panel,
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
              Input("selected-species", "data"))
def fill_citation(gs_name):
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
            html.Span("Image © "), html.Strong(author),
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
        cite_url = (
            f"https://www.sealifebase.se/summary/{slug}.html"
            if src == "sealifebase" else
            f"https://www.fishbase.se/summary/{slug}"
        )
        data_block = [
            html.Span("Taxonomic information, length, habitat, longevity, danger, depth, and additional comments from "),
            html.A(src_name, href=cite_url, target="_blank"),
            html.Span(" — retrieved 12 Jul 2025."),
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

    taxonomy_block=[html.Br(), html.Br(),  html.Span("Taxonomic data (beyond Genus and Species): Derived dataset GBIF.org (7 August 2025) Filtered export of GBIF occurrence data https://doi.org/10.15468/dd.wbjqgn"),]

    return image_block + wiki_block + data_block + taxonomy_block + sound_block


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
    for fname in candidates:
        rel = os.path.join(base_dir, fname)
        if os.path.exists(rel):
            audio_rel = rel
            audio_url = f"/assets/species/sound/{fname}"
            break

    txt_rel = os.path.join(base_dir, f"{base}.txt")
    return audio_rel, txt_rel, audio_url



# NEW: sound – show/hide icon and set audio src when species changes
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
    mp3_rel, txt_rel, mp3_url = _sound_paths(genus, species)

    if os.path.exists(mp3_rel):
        # visible icon + primed audio source
        return ({"display": "block"}, mp3_url)
    else:
        # hide icon, clear src
        return ({"display": "none"}, "")


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
    Output("tree-panel", "style"),
    Output("tree-graph", "elements"),
    Output("tree-graph", "layout"),

    Input("tree-handle",        "n_clicks"),     # manual toggle
    Input("selected-species",   "data"),         # auto-refresh on species change

    State("tree-panel",         "style"),
    prevent_initial_call=True
)
def show_or_update_tree(n_clicks, species, style):
    if not species:
        raise PreventUpdate

    triggered = ctx.triggered_id
    open_now = style and style.get("display") != "none"

    # ─── User clicked the 🌳 button ─────────────────────────────
    if triggered == "tree-handle":
        if open_now:
            return {**style, "display": "none"}, no_update, no_update
        # opening the panel → load tree
        elements, root = build_taxonomy_elements(df_full, species)
        return {**style, "display": "block"}, elements, dagre_layout()

    # ─── Species changed while panel is visible ────────────────
    if triggered == "selected-species" and open_now:
        elements, root = build_taxonomy_elements(df_full, species)
        return no_update, elements, dagre_layout()

    raise PreventUpdate


@app.callback(
    Output("order-lock-label", "children"),
    Output("order-lock-label", "className"),
    Input("order-lock-state",  "data"),      # ON / OFF toggle
    Input("selected-species",  "data"),      # species changed
    State("order-lock-label",  "className"), # keep other classes
    prevent_initial_call=True
)
def update_order_lock_label(locked, species_id, old_class):
    base_class = "order-lock-label"
    if not locked or not species_id:
        return "", base_class               # hide when OFF

    # look up order (fallback "?")
    order = df_full.loc[df_full["Genus_Species"] == species_id, "order"]
    order_name = order.iloc[0] if not order.empty else "?"

    text   = f"Navigating among {order_name} only"
    return text, base_class + " active"



@app.callback(
    Output("species-img",  "src"),
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
        ])


    ]


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
    slug      = f"{genus}_{species}".replace(" ", "_")
    base_src  = thumb or "/assets/img/placeholder_fish.webp"

    # add ? or & so the bitmap stays cached but the URL is unique per species
    sep       = "&" if "?" in base_src else "?"
    img_src   = f"{base_src}{sep}gs={slug}"

    gc.collect()
    return img_src, info_lines





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
    Output("rand-depth-map", "data"),
    Input("rand-seed", "data"),
)
def build_depth_map(seed):
    if seed is None:
        raise PreventUpdate
    tmp = assign_random_depth(df_full.copy(), seed)  # returns a frame with RandDepth
    depth_map = dict(zip(tmp["Genus_Species"], tmp["RandDepth"]))
    return depth_map


@app.callback(
    Output("depth-store", "data"),
    Input("selected-species", "data"),
    State("rand-depth-map", "data"),
)
def push_depth(gs_name, depth_map):
    if not gs_name:
        raise PreventUpdate
    depth = (depth_map or {}).get(gs_name)
    return 0 if depth is None or pd.isna(depth) else depth






# ──────────────────────────────────────────────────────────────
# A) Client‑side toggle (runs in the browser)
# ──────────────────────────────────────────────────────────────
app.clientside_callback(
    """
    function(n_clicks, favs_json, species_id) {
        // safety: ignore first load or missing species
        if (n_clicks === undefined || !species_id) {
            return window.dash_clientside.no_update;
        }

        const favs = new Set(JSON.parse(favs_json || "[]"));
        const wasFav = favs.has(species_id);

        // flip state
        if (wasFav) { favs.delete(species_id); }
        else        { favs.add(species_id);   }

        const filled   = !wasFav;
        const newClass = filled ? "heart-icon filled"
                                : "heart-icon";
        const newGlyph = filled ? "♥" : "♡";

        return [JSON.stringify([...favs]), newClass, newGlyph];
    }
    """,
    # outputs (must match the 3‑item return)
    [
        Output("favs-store", "data"),
        Output("fav-handle", "className", allow_duplicate=True),
        Output("fav-handle", "children",  allow_duplicate=True),
    ],
    # input
    Input("fav-handle", "n_clicks"),
    # state
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
    Input("rand-seed", "data")   
)
def init_seed(cur):
    if cur is None:
        return random.randint(0, 2**32 - 1)
    raise PreventUpdate



# ───────── client‑side: push depth to viewer ─────────
app.clientside_callback(
    """
    function (depth, flag) {
        /*
           `flag` is the `value` array from the checklist.
           When the box is checked   → ["on"]  (play)
           When the box is unchecked → []      (skip)
        */
        const skip = !(Array.isArray(flag) && flag.length);  

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

    return species[idx]


# -------------------------------------------------------------------
# Depth‑axis navigation (up / down)
# -------------------------------------------------------------------
@app.callback(
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

    return species[idx]


# -------------------------------------------------------------------
# Quick‑jump buttons (deepest / shallowest / largest / smallest)
# -------------------------------------------------------------------
# Quick jumps
@app.callback(
    Output("selected-species", "data", allow_duplicate=True),
    Input("deepest-btn",    "n_clicks"),
    Input("shallowest-btn", "n_clicks"),
    Input("largest-btn",    "n_clicks"),
    Input("smallest-btn",   "n_clicks"),
    State("wiki-toggle",    "value"),
    State("popular-toggle", "value"),
    State("favs-toggle",    "value"),
    State("favs-store",     "data"),
    State("rand-depth-map", "data"),      # ← add this
    prevent_initial_call=True
)
def jump_to_extremes(n_deep, n_shallow, n_large, n_small,
                     wiki_val, pop_val, fav_val, favs_data,
                     depth_map):

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

    return row["Genus_Species"]




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
    Input("compare-store",    "data"),     # ← boolean
    prevent_initial_call=True
)
def update_sizecmp(gs_name, is_on):
    # OFF or no species → hide the silhouette
    if not gs_name or not is_on:
        return "", {"display":"none"}, ""

    genus, species = gs_name.split(" ", 1)
    row = df_full.loc[df_full["Genus_Species"] == gs_name].iloc[0]
    length = row.Length_cm

    if pd.isna(length) or length == 0:
        return "", {"display": "none"}, ""



    species_len = row.Length_cm
    best = min(_scale_db, key=lambda d: abs(d["length_cm"] - species_len))
    scale = best["length_cm"] / species_len

    style = {
        "position":"absolute", "left":"50%", "top":"50%", "transform":"translate(-50%,-50%)",
        "width":f"{scale*100:.2f}%", "zIndex":3,
        "opacity":0.85, "pointerEvents":"auto", "cursor":"pointer"
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


#app.run(host="0.0.0.0", port=8050, debug=True)  #change to false later                

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Pelagica</title>
        <link rel="icon" href="/favicon.ico" type="image/x-icon">
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


if __name__ == "__main__" and os.getenv("USE_DEV_SERVER", "0") == "1":
    app.run_server(debug=True, port=8050)
