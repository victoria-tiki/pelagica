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
import numpy as np 
import json, base64   


from src.process_data import load_species_data, load_homo_sapiens
from src.wiki import get_blurb, get_commons_thumb      
from src.utils import assign_random_depth
import os

import gc
import re


# ---------- Load & prep dataframe ---------------------------------------------------
df = load_species_data()       

df_wiki = df[df["has_wiki_page"]].copy() #only those with wikipedia page

df_light = df[["Genus", "Species", "Genus_Species", "FBname", "has_wiki_page"]].copy()
df_light["dropdown_label"] = df_light["FBname"] + " (" + df_light["Genus"] + " " + df_light["Species"] + ")"

# --- Popular-species whitelist -----------------------------------
popular_df   = pd.read_csv("data/processed/popular_species.csv")        # <-- path in /mnt/data
popular_set  = set(popular_df["Genus"] + " " + popular_df["Species"])


# Genus dropdown options
genus_options = [{"label": g, "value": g} for g in sorted(df_wiki["Genus"].unique())]

# Common-name dropdown options (label = “Common (Genus species)”)
common_options = [{"label": r["dropdown_label"], "value": r["Genus_Species"]}
                  for _, r in df_wiki.iterrows()]

# ---------- Build Dash app ----------------------------------------------------------
# external sheets (font + bootstrap)
external_stylesheets = [
    dbc.themes.LUX,
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap"
]
app = Dash(__name__, external_stylesheets=external_stylesheets)

@app.server.route('/cached-images/<path:filename>')
def serve_cached_images(filename):
    return send_from_directory('image_cache', filename)

# ─── TOP BAR ───────────────────────────────────────────────

units_toggle = html.Div(
    [
        html.Span("m"),
        dbc.Switch(id="units-toggle", value=True, className="mx-1", label=""),
        html.Span("ft"),
    ],
    style={"display":"flex","alignItems":"center","fontSize":".8rem"}
)


top_bar = html.Div(
    [
        # 1. logo & tagline (unchanged)
        html.Div(
            [
                html.Img(src="/assets/logo_pelagica_colour.webp",
                         style={"height":"50px"}),
                html.Span("The Aquatic Life Atlas",
                          className="tagline",
                          style={"marginLeft":".5rem","fontSize":".9rem",
                                 "fontWeight":500,"color":"#f5f5f5"})
            ], style={"display":"flex","alignItems":"center"}
        ),

        # spacer
        html.Div(style={"flex":"1"}),

        # 2. favourites button (text + heart = one hit‑area)
        # in top_bar, replace the two separate children with this:
        html.Div(
            [html.Div("♡ Favourites", id="fav-menu-btn",
                         className="top-heart",
                         style={"cursor":"pointer", "marginRight":"1rem"}),
                units_toggle],
            style={"display":"flex","alignItems":"center"}
        ),
    ],
    id="top-bar", className="glass-panel",
    style={"display":"flex","alignItems":"center",
           "padding":"0.5rem 1rem"}
)



# ─── SEARCH STACK ───────────────────────────────────────────────
search_stack = html.Div(id="search-stack", children=[
    html.Div(
        dcc.Dropdown(id="common-dd", options=common_options,
                     placeholder="Common name…", className="dash-dropdown")
    ),
    html.Div(
        dbc.Row([
            dbc.Col(
                dcc.Dropdown(id="genus-dd", options=genus_options,
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

advanced_filters = html.Div(                # collapsible area
    [
    html.H6("Filters", className="settings-header"),

    html.Div([
        dbc.Checklist(
            id="wiki-toggle",
            options=[{"label": "Only species with Wikipedia entry", "value": "wiki"}],
            value=["wiki"],
            switch=True
        )
    ], className="settings-group"),

    html.Div([
        dbc.Checklist(
            id="popular-toggle",
            options=[{"label": "Only popular species", "value": "pop"}],
            value=["pop"],
            switch=True
        ),
        html.Div("Limits to ~1000 curated species. Longer loading times if toggled off.", className="settings-note")
    ], className="settings-group"),
    
    dbc.Checklist(
    id="favs-toggle",
    options=[{"label":"Only favourites","value":"fav"}],
    value=[], switch=True
    ),


    html.H6("Depth Comparison", className="settings-header"),

    html.Div([
        dbc.Checklist(
            id="depth-toggle",
            options=[{"label": "Show depth comparison", "value": "depth"}],
            value=["depth"],
            switch=True
        ),
        html.Div("For navigation, we use a random depth within the species' depth range.",
                 className="settings-note"),
    ], className="settings-group"),

    html.H6("Size Comparison", className="settings-header"),

    html.Div([
        dbc.Checklist(
            id="size-toggle",
            options=[{"label": "Show size comparison", "value": "size"}],
            value=["size"],
            switch=True
        ),
        html.Div("Uses length as a proxy for size.",
                 className="settings-note")
        #dbc.Checklist(
        #    id="order-toggle",
        #    options=[{"label": "…only within same order", "value": "order"}],
        #    value=[],
        #    switch=True,
        #    style={"display": "none"}
        #)
    ], className="settings-group"),

    html.Hr(style={"opacity": .3}),

        html.H6("Quick jumps"),
        dbc.Row(
            [
                dbc.Col(
                    html.Button("jump to shallowest", id="shallowest-btn",
                                className="btn btn-outline-light btn-sm w-100"),
                    width=6
                ),
                
                dbc.Col(
                    html.Button("jump to deepest",    id="deepest-btn",
                                className="btn btn-outline-light btn-sm w-100"),
                    width=6
                ),
            ],
            className="gx-1", style={"marginBottom": ".4rem"}
        ),
        

        dbc.Row(
            [
                dbc.Col(
                    html.Button("jump to smallest",  id="smallest-btn",
                                className="btn btn-outline-light btn-sm w-100"),
                    width=6
                ),
                dbc.Col(
                    html.Button("jump to largest",   id="largest-btn",
                                className="btn btn-outline-light btn-sm w-100"),
                    width=6
                ),
            ],
            className="gx-1"
        ),

    ],
    id="adv-box",
    style={"display": "none"} 
)

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



'''# --------------------------------------------------------------------
#  Settings OFF-canvas
# --------------------------------------------------------------------
settings_panel = dbc.Offcanvas(
    id="settings-canvas",
    placement="end",
    title="Controls",
    is_open=False,
    close_button=False,
    style={"width": f"{SETTINGS_W}px"},
    children=[
        # --- Units ----------------------------------------------------------
        html.H6("Units"),
        dbc.RadioItems(
            id="units-toggle",
            value="metric",
            inline=True,
            options=[
                {"label": "Metric",   "value": "metric"},
                {"label": "Imperial", "value": "imperial"},
            ],
        ),
        html.Hr(style={"opacity": .3}),

        # --- NEW FILTERS ----------------------------------------------------
        html.H6("Filters"),
        dbc.Checklist(
            id="wiki-toggle",
            options=[{"label": "Only species with Wikipedia entry", "value": "wiki"}],
            value=["wiki"],
            switch=True,
        ),

        dbc.Checklist(                       # ▸ popular – wiring stub for later
            id="popular-toggle",
            options=[{"label": "Only popular species", "value": "pop"}],
            value=["pop"],
            switch=True,
        ),
        
        html.Div(
            "Limits species to 1000 most popular species (1% of the entire dataset).",
            style={"fontSize": "0.8rem", "marginTop": "-0.5rem", "marginBottom": "1.0rem", "opacity": 0.75}
        ),
        
        html.Hr(style={"opacity": .3}),

        # --- Size-comparison ------------------------------------------------
        html.H6("Size Comparison"),
        dbc.Checklist(
            id="size-toggle",
            options=[{"label": "Show size comparison", "value": "size"}],
            value=["size"],
            switch=True,
        ),
        
        html.Div(
            "Only species with known size are shown when this is on."
            " If off, species are compared by depth range (beta).",
            style={"fontSize": "0.8rem", "marginTop": "-0.5rem", "marginBottom": "1.0rem", "opacity": 0.75}
        ),


        dbc.Checklist(                       # hidden until size-toggle is on
            id="order-toggle",
            options=[{"label": "…but only within same order", "value": "order"}],
            value=[],
            switch=True,
            style={"display": "none"},
        ),
    ],
)'''


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




# --------------------------------------------------------------------
#  Centre-page flex wrapper
# --------------------------------------------------------------------

centre_flex = html.Div(id="page-centre-flex", children=[
    html.Div(id="image-wrapper", children=[

        # this div now contains the image AND the up/down buttons
        html.Div(id="image-inner", children=[
            html.Img(id="species-img"),
            html.Div("i", id="info-handle", style={"display": "none"}),
            html.Div("♡", id="fav-handle", className="heart-icon"),
        ]),

        # info card remains outside image-inner
        html.Div(id="info-card", className="glass-panel",children=[
            html.Div(id="info-close", children="✕"),
            html.Div(id="info-content")
        ])
    ])
])

center_message=html.Div(
    id="load-message",
    children="Loading species…",
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
),



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
        "right": "1rem",
        "bottom": "1rem",
        "fontSize": ".8rem",
        "opacity": .7
    }
)
  

# replace the whole fav_modal block
fav_modal = dbc.Modal(
    [
        dbc.ModalHeader("Liked species", close_button=True),
        dbc.ModalBody(
            [
                html.Button("⬇ Export (.txt)", id="fav-export",
                            className="btn btn-outline-primary btn-sm w-100"),
                dcc.Download(id="fav-dl"),
                html.Br(),
                dcc.Upload("⬆ Load (.txt)", id="fav-upload",
                           className="btn btn-outline-primary btn-sm w-100",
                           style={"display":"block"},  # fills full width
                           multiple=False),
            ],
            className="p-2",            # minimal padding
            style={"maxWidth":"280px"}  # hugs the content
        ),
    ],
    id="fav-modal",
    is_open=False,
    centered=True,
    backdrop=True,
    size="sm",
)




# ─── NAVIGATION PANEL w/ DIAL ─────────────────────────────────────────
nav_panel = html.Div([
    # ── Header ────────────────────────────────────────────────
    html.Div([
        html.Span("ⓘ", id="nav-info-icon", className="nav-info-icon"),
    ], className="nav-header"),

    # ── Compass in one layer ───────────────────────────────────
    html.Img(src="/assets/dial.webp", className="dial-bg"),

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

    # ── Hidden explanation ─────────────────────────────────────
    html.Div([
        "Navigation Menu",
        html.Br(), html.Br(),
        "Explore species by size or depth. Move from shallow waters to the deep sea, and from tiny creatures to giants."
    ],
        id="nav-info-text",
        style={"display": "none"}
    )

], id="nav-panel", className="glass-panel")







search_handle = html.Div(["🔍 Search"], id="search-handle", className="search-handle", **{"data-mobile-x": "true"})


    
#  Assemble Layout
app.layout = dbc.Container([
    search_panel,
    search_handle,
    dcc.Store(id="rand-seed", storage_type="session"),
    top_bar,
    
    fav_modal,

    #settings_panel,

    # -- side tabs, rendered once and slid by callbacks --
    html.Div("citations",      id="citations-tab", className="side-tab"),
    #html.Div("⚙ Control Panel",id="settings-tab",  className="side-tab"),
    html.Div("report a bug",   id="bug-tab",       className="side-tab"),

    html.Div(centre_flex, id="main-content", style={"display": "none"}),
    nav_panel,


    footer,
    dcc.Store(id="selected-species", data=None),
    dcc.Store(id="favs-store",storage_type="local"),      # persists in localStorage

    citations_panel,
], fluid=True)


@app.callback(
    Output("genus-dd", "options"),
    Output("genus-dd", "value"),
    Input("wiki-toggle",    "value"),
    Input("popular-toggle", "value"),
    Input("favs-toggle",    "value"),      # NEW
    State("favs-store",     "data"),       # NEW
    State("genus-dd", "value"),
)
def filter_genus(wiki_val, pop_val, fav_val, favs_data, current):
    df_use = _apply_shared_filters(df_light, wiki_val, pop_val,
                                   fav_val, favs_data)

    opts   = [{"label": g, "value": g}
              for g in sorted(df_use["Genus"].unique())]
    valid  = {o["value"] for o in opts}
    return opts, current if current in valid else None



# -------------------------------------------------------------------
# Callback 1 – populate species options whenever genus changes
# -------------------------------------------------------------------
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
# Callback 2 – whenever any chooser fires, update selected-species
# -------------------------------------------------------------------
@app.callback(
    Output("selected-species", "data", allow_duplicate=True),
    Input("species-dd", "value"),
    Input("genus-dd",   "value"),
    Input("common-dd",  "value"),
    Input("random-btn", "n_clicks"),
    State("wiki-toggle",    "value"),
    State("popular-toggle", "value"),
    State("favs-toggle",    "value"),      # NEW
    State("favs-store",     "data"),       # NEW
    prevent_initial_call=True
)
def choose_species(species_val, genus_val, common_val, rnd,
                   wiki_val, pop_val, fav_val, favs_data):
    trig = ctx.triggered_id

    # ---------- build the filtered frame -----------------
    df_use = _apply_shared_filters(df, wiki_val, pop_val,
                                   fav_val, favs_data)

    # ---------- Random button ----------------------------
    if trig == "random-btn":
        if df_use.empty:
            raise PreventUpdate
        row = df_use.sample(1).iloc[0]
        return f"{row.Genus} {row.Species}"

    # ---------- Common-name dropdown ---------------------
    if trig == "common-dd" and common_val:
        return common_val

    # ---------- Genus + Species pair ---------------------
    if trig in ("genus-dd", "species-dd") and genus_val and species_val:
        return f"{genus_val} {species_val}"

    raise PreventUpdate




'''# --- SETTINGS panel toggle ------------------------------------
@app.callback(
    Output("settings-canvas",  "is_open"),
    Output("citations-canvas", "is_open", allow_duplicate=True),
    Output("info-card",        "style",  allow_duplicate=True),
    Output("info-handle",      "style",  allow_duplicate=True),   # 👈 NEW
    Input("settings-tab",      "n_clicks"),
    State("settings-canvas",   "is_open"),
    prevent_initial_call=True
)
def toggle_settings(n, settings_open):
    if not n:
        raise PreventUpdate

    new_settings = not settings_open
    return (
        new_settings,          # open / close settings
        False,                 # always close citations
        {"display": "none"},   # hide info card
        {"display": "block"}   # show little "i" handle
    )'''

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
    new_handle= {"display":"block"} if show else {"display":"none"}
    return new_card, new_handle


# --- push citation text when species changes -------------------------------
@app.callback(Output("citation-box", "children"),
              Input("selected-species", "data"))
def fill_citation(gs_name):
    if not gs_name:
        raise PreventUpdate

    genus, species = gs_name.split(" ", 1)
    row = df.loc[df["Genus_Species"] == gs_name].iloc[0]

    # ---------- try Wikimedia Commons -------------
    import time
    start = time.time()
    thumb, author, lic, lic_url, up, ret = get_commons_thumb(genus, species)
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
            html.Br(), html.Br(),
            html.Span("Background removed using "),
            html.A("rembg", href="https://github.com/danielgatis/rembg", target="_blank"),
            html.Span(", an open-source background removal tool by Daniel Gatis."),
            html.Br(), html.Br(),
        ]

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

    return image_block + wiki_block + data_block


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





def replace_links(text):
    # Replace any existing HTML links with 'Link' (preserving the href)
    return re.sub(
        r'<a\s+[^>]*href=[\'"]([^\'"]+)[\'"][^>]*>.*?</a>',
        lambda m: f'<a href="{m.group(1)}" target="_blank" style="text-decoration: none; color: inherit;">Link</a>',
        text
    )


def _units(value_bool):
    return "metric" if value_bool else "imperial"



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
    thumb, *_ = get_commons_thumb(genus, species)

    # -------- pull the chosen row once -------
    #row = df_wiki.loc[df_wiki["Genus_Species"] == gs_name].iloc[0]
    
    row_full = df.loc[df["Genus_Species"] == gs_name]
    if row_full.empty:                 
        raise PreventUpdate
    row = row_full.iloc[0]

    # ---------- LENGTH ----------
    if units == "metric":
        if pd.notna(row.Length_cm):
            if row.Length_cm >= 100:
                # show in meters to two decimals
                length = f"{row.Length_cm/100:.2f} m"
            else:
                length = f"{row.Length_cm:.1f} cm"
        else:
            length = "?"
    else:
        if pd.notna(row.Length_in):
            if row.Length_in >= 12:                     # 12 in = 1 ft
                length = f"{row.Length_in/12:.2f} ft"   # decimal feet
            else:
                length = f"{row.Length_in:.1f} in"
        else:
            length = "?"


    if row.get("Database") == 0:
        length_tooltip = "Global average height"
        depth_tooltip  = "Unassisted freediving record depth"
    else:
        length_tooltip = "Maximum recorded length of species"
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
            f": {length}  |  ",
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

    '''# ---------- DATABASE COMMENTS (only when present) ----------------
    comments = row.get("Comments")
    src      = str(row.get("Database", "")).lower()      # "sealifebase" / "fishbase"
    
    if pd.notna(comments) and comments.strip():
        slug = f"{genus}-{species}".replace(" ", "-")
        src_name = "SeaLifeBase" if src == "sealifebase" else "FishBase"
        cite_url = (
            f"https://www.sealifebase.se/summary/{slug}.html"
            if src == "sealifebase" else
            f"https://www.fishbase.se/summary/{slug}"
        )

        info_lines.extend([
            html.Br(),
            html.Span(" ".join(comments.strip().split()[:100]) + "…"), html.Br(),
            html.A(f"{src_name} ↗", href=cite_url, target="_blank")
        ])'''
        

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
            html.A(f"{src_name} ↗", href=cite_url, target="_blank", style={"textDecoration": "none", "color": "inherit"})
        ])








    gc.collect() 
    return thumb or "/assets/placeholder_fish.webp", info_lines


@app.callback(
    Output("main-content", "style"),
    Input("selected-species", "data")
)
def show_main_content(gs_name):
    if not gs_name:
        return {"display": "none"}
    return {"display": "block"}


# ---- slide citations tab (now mirrors settings) -------------------
@app.callback(
    Output("citations-tab", "style"),
    Input("citations-canvas", "is_open")
)
def slide_citation_tab(opened):
    if opened:
        return {"right": f"{CITATION_W}px"}   # push left by its own width
    return {"right": "0px"}


'''# move settings tab
@app.callback(
    Output("settings-tab", "style"),
    Input("settings-canvas", "is_open")
)
def slide_settings_tab(opened):
    if opened:
        return {"right": f"{SETTINGS_W}px"}  # slide left
    return {"right": "0px"}'''

'''@app.callback(
    Output("order-toggle", "style"),
    Input("size-toggle", "value"),
)
def show_order_switch(size_val):
    return {"display": "block"} if "size" in size_val else {"display": "none"}'''



@app.callback(
    Output("common-dd",  "value", allow_duplicate=True),
    Output("genus-dd",   "value", allow_duplicate=True),
    Output("species-dd", "value", allow_duplicate=True),  # duplicate of other cb
    Input("selected-species", "data"),
    prevent_initial_call=True
)
def sync_dropdowns(gs_name):
    if not gs_name:
        raise PreventUpdate

    genus, species = gs_name.split(" ", 1)
    common = f"{genus} {species}"          # you can pull FBname if you prefer
    return common, genus, species





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


# ──────────────────────────────────────────────────────────────
# Helper: build one consistent dataframe for the current filters
# ──────────────────────────────────────────────────────────────
def get_filtered_df(size_on: bool, depth_on: bool,
                    wiki_val, pop_val, seed=None):
    """
    Build one dataframe that respects all active toggles.

    • If *size_on*  → keep only rows with Length_cm.
    • If *depth_on* → keep only rows with (any) depth.
    • Both on?      → require **both** length *and* depth.

    When *depth_on* is True we also attach the RandDepth column (needs seed).
    """
    df_use = df.copy()

    # --- per-axis availability ------------------------------------------
    if size_on:
        df_use = df_use[df_use["Length_cm"].notna()]

    if depth_on:
        df_use = df_use[
            df_use["DepthRangeComShallow"].notna() |
            df_use["DepthRangeShallow"].notna()
        ]

    # --- global filters -------------------------------------------------
    if "wiki" in wiki_val:
        df_use = df_use[df_use["has_wiki_page"]]

    if "pop" in pop_val:
        df_use = df_use[df_use["Genus_Species"].isin(popular_set)]

    # --- random depth column (only when needed) -------------------------
    if depth_on and seed is not None:
        df_use = assign_random_depth(df_use, seed)

    return df_use

'''# ─── size-axis navigation (left / right) ────────────────────────────
@app.callback(
    Output("selected-species", "data", allow_duplicate=True),
    Input("next-btn",  "n_clicks"),
    Input("prev-btn",  "n_clicks"),
    Input("size-toggle",     "value"),
    Input("depth-toggle",    "value"),   # ← ADD THIS
    Input("wiki-toggle",     "value"),
    Input("popular-toggle",  "value"),
    State("rand-seed",       "data"),
    prevent_initial_call=True
)
def next_prev_species(n_next, n_prev, current,
                      size_val, depth_val,          # ← …and THIS
                      wiki_val, pop_val, seed):

    # -------- guard rails -------------------------------------------
    if not current or "size" not in size_val:    # size axis is off
        raise PreventUpdate

    trig_prev = ctx.triggered_id == "prev-btn"
    trig_next = ctx.triggered_id == "next-btn"
    if not (trig_prev or trig_next):
        raise PreventUpdate

    # -------- build filtered frame ----------------------------------
    size_on  = True                              # we know it’s on
    depth_on = "depth" in depth_val
    df_use   = get_filtered_df(size_on, depth_on,
                               wiki_val, pop_val, seed)

    if df_use.empty:
        raise PreventUpdate

    # -------- order by length only (size axis) ----------------------
    df_use = df_use.sort_values(["Length_cm", "Length_in"])
    species = df_use["Genus_Species"].tolist()
    if current not in species:
        current = species[0]

    idx = species.index(current)
    idx = (idx - 1) % len(species) if trig_prev else (idx + 1) % len(species)
    return species[idx]'''


'''@app.callback(
    Output("prev-btn", "children"),
    Output("next-btn", "children"),
    Input("selected-species", "data"),
    Input("size-toggle",      "value"),
)
def set_size_labels(current, size_val):
    if "size" not in size_val or not current:
        return "‹", "›"
    return ["‹", html.Span("smaller", className="label")], \
           ["›", html.Span("larger", className="label")]


@app.callback(
    Output("up-btn",   "children"),
    Output("down-btn", "children"),
    Input("selected-species", "data"),
    Input("depth-toggle",     "value"),
)
def set_depth_labels(current, depth_val):
    if "depth" not in depth_val or not current:
        return "‹", "›"                   
    return [
        html.Span("‹", className="chev"),
        html.Span("shallower", className="label")
    ], [
        html.Span("deeper", className="label"),
        html.Span("›", className="chev")
    ]'''




####------------------------------------------------------------

@app.callback(
    Output("common-dd", "options"),
    Output("common-dd", "value"),
    Input("wiki-toggle",   "value"),
    Input("popular-toggle","value"),
    Input("favs-toggle",   "value"),       # NEW
    State("favs-store",    "data"),        # NEW
    State("common-dd", "value"),
)
def filter_common(wiki_val, pop_val, fav_val, favs_data, current):
    df_use = _apply_shared_filters(df_light, wiki_val, pop_val,
                                   fav_val, favs_data)

    opts = [
        {"label": row["dropdown_label"], "value": row["Genus_Species"]}
        for _, row in df_use.iterrows()
        if pd.notna(row["dropdown_label"])
    ]
    valid = {o["value"] for o in opts}
    return opts, current if current in valid else None




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


app.clientside_callback(
"""
function(n, currentGS, favsJSON){
    const nu = dash_clientside.no_update;
    if(!currentGS){ return [nu, nu, nu]; }

    const favs = favsJSON ? JSON.parse(favsJSON) : [];
    const hit  = favs.includes(currentGS);

    // toggle if the click came from the heart itself
    if(dash_clientside.callback_context.triggered[0].prop_id === "fav-handle.n_clicks"){
        if(hit){ favs.splice(favs.indexOf(currentGS),1); }
        else    { favs.push(currentGS); }
        document.cookie = "pelagica_favs="+btoa(JSON.stringify(favs))+";path=/;max-age=31536000";
    }

    const glyph = favs.includes(currentGS) ? "♥" : "♡";
    const cls   = favs.includes(currentGS) ? "heart-icon filled" : "heart-icon";
    return [glyph, cls, JSON.stringify(favs)];
}
""",
    Output("fav-handle", "children"),
    Output("fav-handle", "className"),
    Output("favs-store", "data"),
    Input("fav-handle", "n_clicks"),
    Input("selected-species", "data"),
    State("favs-store", "data"),
)


# -------------------------------------------------------------------
# 0 · helpers
# -------------------------------------------------------------------
def _apply_shared_filters(frame, wiki_val, pop_val,
                          fav_val=None, favs_data=None):
    """Return a copy of *frame* after wiki/pop/fav filters."""
    df_use = frame.copy()
    if "wiki" in wiki_val:
        df_use = df_use[df_use["has_wiki_page"]]
    if "pop" in pop_val:
        df_use = df_use[df_use["Genus_Species"].isin(popular_set)]
    if fav_val and "fav" in fav_val:
        fav_set = set(json.loads(favs_data or "[]"))
        df_use = df_use[df_use["Genus_Species"].isin(fav_set)]
    return df_use





@app.callback(
    Output("rand-seed", "data", allow_duplicate=True),
    Input("rand-seed", "data"),
    prevent_initial_call=True
)
def _init_seed(cur):
    if cur is None:                       # first page-load in this tab
        import random
        return random.randint(0, 2**32-1)
    raise PreventUpdate


# -------------------------------------------------------------------
# Size‑axis navigation (left / right)
# -------------------------------------------------------------------
@app.callback(
    Output("selected-species", "data", allow_duplicate=True),
    Input("next-btn",  "n_clicks"),
    Input("prev-btn",  "n_clicks"),
    State("size-toggle",      "value"),
    State("depth-toggle",     "value"),
    State("wiki-toggle",      "value"),
    State("popular-toggle",   "value"),
    State("favs-toggle",      "value"),     # ← NEW
    State("favs-store",       "data"),      # ← NEW
    State("selected-species", "data"),
    State("rand-seed",        "data"),
    prevent_initial_call=True
)
def step_size(n_next, n_prev,
              size_val, depth_val, wiki_val, pop_val,
              fav_val, favs_data,
              current, seed):

    if ctx.triggered_id not in ("prev-btn", "next-btn"):
        raise PreventUpdate
    if "size" not in size_val:              # size axis is off
        raise PreventUpdate

    # ---- build dataframe respecting ALL filters -------------------
    size_on  = True
    depth_on = "depth" in depth_val

    df_use = get_filtered_df(size_on, depth_on,
                             wiki_val, pop_val, seed)

    # favourites post‑filter
    if fav_val and "fav" in fav_val:
        fav_set = set(json.loads(favs_data or "[]"))
        df_use  = df_use[df_use["Genus_Species"].isin(fav_set)]

    if df_use.empty:
        raise PreventUpdate

    # ---- rank by length and step ±1 --------------------------------
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
    Input("up-btn",   "n_clicks"),
    Input("down-btn", "n_clicks"),
    State("size-toggle",      "value"),
    State("depth-toggle",     "value"),
    State("wiki-toggle",      "value"),
    State("popular-toggle",   "value"),
    State("favs-toggle",      "value"),     # ← NEW
    State("favs-store",       "data"),      # ← NEW
    State("selected-species", "data"),
    State("rand-seed",        "data"),
    prevent_initial_call=True
)
def step_depth(n_up, n_down,
               size_val, depth_val, wiki_val, pop_val,
               fav_val, favs_data,
               current, seed):

    if ctx.triggered_id not in ("up-btn", "down-btn"):
        raise PreventUpdate
    if "depth" not in depth_val:            # depth axis is off
        raise PreventUpdate

    size_on  = "size"  in size_val
    depth_on = True

    df_use = get_filtered_df(size_on, depth_on,
                             wiki_val, pop_val, seed)

    # favourites filter
    if fav_val and "fav" in fav_val:
        fav_set = set(json.loads(favs_data or "[]"))
        df_use  = df_use[df_use["Genus_Species"].isin(fav_set)]

    if df_use.empty:
        raise PreventUpdate

    df_use  = df_use.sort_values("RandDepth")
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
@app.callback(
    Output("selected-species", "data", allow_duplicate=True),
    Input("deepest-btn",    "n_clicks"),
    Input("shallowest-btn", "n_clicks"),
    Input("largest-btn",    "n_clicks"),
    Input("smallest-btn",   "n_clicks"),
    State("wiki-toggle",    "value"),
    State("popular-toggle", "value"),
    State("favs-toggle",    "value"),     # ← NEW
    State("favs-store",     "data"),      # ← NEW
    State("rand-seed",      "data"),
    prevent_initial_call=True
)
def jump_to_extremes(n_deep, n_shallow,
                     n_large, n_small,
                     wiki_val, pop_val,
                     fav_val, favs_data,
                     seed):

    trig = ctx.triggered_id
    if trig is None:
        raise PreventUpdate

    # ---------------- Base dataframe -------------------------------
    size_on  = trig in ("largest-btn", "smallest-btn")
    depth_on = trig in ("deepest-btn", "shallowest-btn")

    df_use = get_filtered_df(size_on, depth_on,
                             wiki_val, pop_val, seed)

    # favourites filter
    if fav_val and "fav" in fav_val:
        fav_set = set(json.loads(favs_data or "[]"))
        df_use  = df_use[df_use["Genus_Species"].isin(fav_set)]

    if df_use.empty:
        raise PreventUpdate

    # ---------------- Pick extreme -------------------------------
    if trig in ("largest-btn", "smallest-btn"):
        df_use = df_use.sort_values(["Length_cm", "Length_in"])
        row    = df_use.iloc[-1] if trig == "largest-btn" else df_use.iloc[0]
    else:
        df_use = df_use.sort_values("RandDepth")
        row    = df_use.iloc[-1] if trig == "deepest-btn" else df_use.iloc[0]

    return row["Genus_Species"]



# ─── left / right buttons — show only when size-comp is ON and a species picked
'''@app.callback(
    Output("prev-btn", "children"),
    Output("prev-btn", "style"),
    Output("next-btn", "children"),
    Output("next-btn", "style"),
    Input("selected-species", "data"),
    Input("size-toggle",      "value"),
    prevent_initial_call=True
)
def render_size_buttons(current, size_val):

    active = current and ("size" in size_val)

    if not active:
        # hide buttons completely
        return "‹", {"display": "none"}, "›", {"display": "none"}

    # visible + correct labels
    return (
        ["‹", html.Span("smaller", className="label")], {},
        ["›", html.Span("larger",  className="label")], {}
    )'''


# ─── up / down buttons — show only when depth-comp is ON and a species picked
'''@app.callback(
    Output("up-btn",   "children"),
    Output("up-btn",   "style"),
    Output("down-btn", "children"),
    Output("down-btn", "style"),
    Input("selected-species", "data"),
    Input("depth-toggle",     "value"),
    prevent_initial_call=True
)
def render_depth_buttons(current, depth_val):

    active = current and ("depth" in depth_val)

    if not active:
        return "‹", {"display": "none"}, "›", {"display": "none"}

    return (
        [html.Span("‹", className="chev"),
         html.Span("shallower", className="label")], {},

        [html.Span("deeper", className="label"),
         html.Span("›", className="chev")], {}
    )'''

# ── show/hide size arrows ─────────────────────────────────────────────
@app.callback(
    Output("prev-wrap", "style"),
    Output("next-wrap", "style"),
    Input("selected-species", "data"),
    Input("size-toggle",      "value"),
    prevent_initial_call=True
)
def toggle_size_wrap(gs, size_val):
    if gs and "size" in size_val:
        style = {"opacity": "1", "pointer-events": "auto"}
    else:
        style = {"opacity": "0.3", "pointer-events": "none"}
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
    if gs and "depth" in depth_val:
        style = {"opacity": "1", "pointer-events": "auto"}
    # …otherwise “grey out” (low opacity + no clicks)
    else:
        style = {"opacity": "0.3", "pointer-events": "none"}
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


app.run(host="0.0.0.0", port=8050, debug=True)

#if __name__ == "__main__":
#    app.run(debug=True)
#    raise PreventUpdate                      
