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
import pandas as pd, random, datetime

from src.process_data import load_species_data
from src.wiki import get_blurb, get_commons_thumb         
from src.utils import assign_random_depth


# ---------- Load & prep dataframe ---------------------------------------------------
df = load_species_data()          # your helper in src/data.py
df_wiki = df[df["has_wiki_page"]].copy() #only those with wikipedia page
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


# ─── TOP BAR ───────────────────────────────────────────────
top_bar = html.Div(
    [
        html.Img(src="/assets/logo_pelagica.webp", id="logo",
                 style={"height": "60px"}),
        dbc.RadioItems(                    # units toggle now lives here
            id="units-toggle",
            value="metric",
            inline=True,
            options=[
                {"label": "Metric",   "value": "metric"},
                {"label": "Imperial", "value": "imperial"},
            ],
            style={"marginLeft": "auto"}   # push to far right
        ),
    ],
    id="top-bar",
    style={
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "space-between",
        "padding": "0.25rem 1rem",
        "gap": "1rem",
        "position": "fixed",
        "top": 0, "left": 0, "right": 0,
        "zIndex": 1050,
        "background": "var(--glass-bg)",
        "backdropFilter": "var(--blur-md)"
    }
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

# >>> NEW  –  fixed panel that lives on its own
search_panel = html.Div(search_stack, id="search-panel")



CITATION_W  = 300   
PANEL_WIDTH  = CITATION_W
SEARCH_W, SEARCH_TOP = 440, 120    # width px, distance below top bar

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
        html.Div("Limits to ~100 curated species.", className="settings-note")
    ], className="settings-group"),

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
        #dbc.Row(
        #    [
        #        dbc.Col(
        #            html.Button("jump to shallowest", id="shallowest-btn",
        #                        className="btn btn-outline-light btn-sm w-100"),
        #            width=6
        #        ),
        #        
        #        dbc.Col(
        #            html.Button("jump to deepest",    id="deepest-btn",
        #                        className="btn btn-outline-light btn-sm w-100"),
        #            width=6
        #        ),
        #    ],
        #    className="gx-1", style={"marginBottom": ".4rem"}
        #),
        

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
    [
        html.Span("🔍 Search", id="search-toggle",
                  style={"fontWeight":"600","cursor":"pointer"})
    ],
    style={"display":"flex","justifyContent":"space-between",
           "alignItems":"center","marginBottom":"0.6rem"}
)


search_panel = html.Div(
    [search_header, search_stack, advanced_filters],
    id="search-panel"
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
    placement="end",
    title="Citations",
    is_open=False,
    close_button=False,
    backdrop=False,
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
            html.Div("i", id="info-handle", style={"display": "none"})
        ]),

        # info card remains outside image-inner
        html.Div(id="info-card", children=[
            html.Div(id="info-close", children="✕"),
            html.Div(id="info-content")
        ])
    ])
])




# --------------------------------------------------------------------
#  Assemble Layout
# --------------------------------------------------------------------
# footer credit  (replace the faulty line)
footer = html.Div(
    [
        html.Span("created by "),
        html.A("Victoria Tiki",
               href="https://victoriatiki.com/about",
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
        html.Small("shallower", className="nav-label"),
    ], id="up-wrap", className="nav-wrap up"),

    html.Div([
        html.Button("〉", id="down-btn", className="nav-icon"),
        html.Small("deeper", className="nav-label"),
    ], id="down-wrap", className="nav-wrap down"),

    html.Div([
        html.Button("〉", id="prev-btn", className="nav-icon"),
        html.Small("smaller", className="nav-label"),
    ], id="prev-wrap", className="nav-wrap left"),

    html.Div([
        html.Button("〉", id="next-btn", className="nav-icon"),
        html.Small("larger", className="nav-label"),
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

], id="nav-panel")







search_handle = html.Div("‹", id="search-handle", className="search-handle")

    
#  Assemble Layout
app.layout = dbc.Container([
    search_panel,
    search_handle,
    dcc.Store(id="rand-seed", storage_type="session"),
    top_bar,
    #settings_panel,
    citations_panel,

    # -- side tabs, rendered once and slid by callbacks --
    html.Div("citations",      id="citations-tab", className="side-tab"),
    #html.Div("⚙ Control Panel",id="settings-tab",  className="side-tab"),
    html.Div("report a bug",   id="bug-tab",       className="side-tab"),

    html.Div(centre_flex, id="main-content", style={"display": "none"}),
    nav_panel,


    footer,
    dcc.Store(id="selected-species", data=None)
], fluid=True)


@app.callback(
    Output("genus-dd", "options"),
    Output("genus-dd", "value"),
    Input("wiki-toggle",    "value"),
    Input("popular-toggle", "value"),
    State("genus-dd", "value"),
)
def filter_genus(wiki_val, pop_val, current):
    df_use = df.copy()

    if "wiki" in wiki_val:
        df_use = df_use[df_use["has_wiki_page"]]

    if "pop" in pop_val:
        df_use = df_use[df_use["Genus_Species"].isin(popular_set)]


    opts = [{"label": g, "value": g} for g in sorted(df_use["Genus"].unique())]
    valid = {o["value"] for o in opts}
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
    State("species-dd", "value"),
)
def update_species_options(genus, wiki_val, pop_val, current):
    if not genus:
        return [], None

    df_use = df[df["Genus"] == genus]

    if "wiki" in wiki_val:
        df_use = df_use[df_use["has_wiki_page"]]

    if "pop" in pop_val:
        df_use = df_use[df_use["Genus_Species"].isin(popular_set)]


    species_list = sorted(df_use["Species"].unique())
    opts = [{"label": s, "value": s} for s in species_list]
    return opts, current if current in species_list else (
        species_list[0] if len(species_list) == 1 else None
    )



# -------------------------------------------------------------------
# Callback 2 – whenever any chooser fires, update selected-species
# -------------------------------------------------------------------
@app.callback(
    Output("selected-species", "data",allow_duplicate=True),
    Input("species-dd", "value"),
    Input("genus-dd",   "value"),
    Input("common-dd",  "value"),
    Input("random-btn", "n_clicks"),
    State("wiki-toggle",    "value"),   #  ← new
    State("popular-toggle", "value"),   #  ← new
    prevent_initial_call=True
)
def choose_species(species_val, genus_val, common_val, rnd,
                   wiki_val, pop_val):
    trig = ctx.triggered_id

    # ---------- build the filtered frame -----------------
    df_use = df.copy()
    if "wiki" in wiki_val:
        df_use = df_use[df_use["has_wiki_page"]]
    if "pop" in pop_val:
        df_use = df_use[df_use["Genus_Species"].isin(popular_set)]

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
    Output("info-card",        "style", allow_duplicate=True),
    Output("info-handle",      "style", allow_duplicate=True),
    Input("citations-tab",     "n_clicks"),
    State("citations-canvas",  "is_open"),
    prevent_initial_call=True
)
def toggle_citations(n, citations_open):
    if not n:
        raise PreventUpdate

    new_citations = not citations_open
    return (
        new_citations,         # open / close citations
        {"display": "none"},   # hide info card
        {"display": "block"}   # show little "i" handle
    )

    
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
    thumb, author, lic, lic_url, up, ret = get_commons_thumb(genus, species)

    # ---------- database citation  ----------------
    src      = str(row.get("Database", "")).lower()
    slug     = f"{genus}-{species}".replace(" ", "-")
    src_name = "SeaLifeBase" if src == "sealifebase" else "FishBase"
    cite_url = (
        f"https://www.sealifebase.se/summary/{slug}.html"
        if src == "sealifebase" else
        f"https://www.fishbase.se/summary/{slug}"
    )
    today = datetime.date.today().isoformat()

    # ---------- build blocks ----------------------
    image_block = []
    if author:                                   # only when an image exists
        image_block = [
            html.Span("Image © "), html.Strong(author),
            html.Span(", "),
            html.Span((lic or "") + " "),
            html.A("(license link)", href=lic_url) if lic_url else None,
            html.Span(f" — uploaded {up}, retrieved {ret} from Wikimedia Commons"),
            html.Br(), html.Br(),
        ]

    return image_block + [
        html.Span("Text excerpt: Wikipedia — CC BY-SA 4.0, retrieved "),
        html.Span(today),
        html.Br(), html.Br(),
        html.Span("Taxonomic, length, habitat, longevity, and depth data from "),
        html.A(src_name, href=cite_url, target="_blank"),
        html.Span(" — retrieved 12 Jul 2025.")
    ]




# --- populate image + overlay + titles whenever species or units change ----------
@app.callback(
    Output("species-img",   "src"),
    Output("info-content",  "children"),
    #Output("species-titles","children"),
    Input("selected-species", "data"),
    Input("units-toggle",     "value")        # <-- NEW
)
def update_image(gs_name, units):
    habitat_defs = {
        "benthopelagic":     "swims near the sea floor and in open water",
        "pelagic-oceanic":   "lives in the open ocean, away from land or sea floor",
        "reef-associated":   "lives near coral reefs",
        "benthic":           "lives on or in the sea floor",
        "pelagic":           "inhabits open water, not near the bottom",
        "demersal":          "lives close to the bottom, often resting there",
        "pelagic-neritic":   "lives in coastal open water, above the continental shelf",
        "bathydemersal":     "inhabits deep waters near the sea floor",
        "sessile":           "attached to a surface and doesn’t move"
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
        length = f"{row.Length_cm:.1f} cm" if pd.notna(row.Length_cm) else "?"
    else:
        length = f"{row.Length_in:.1f} in" if pd.notna(row.Length_in) else "?"

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
            html.Span("length", title="Maximum recorded length of species", style={"textDecoration": "underline dashed"}),
            f": {length}  |  ",
            html.Span("depth", title="Pelagica shows you this species at a random depth within this range. Range may be inaccurate for certain species - check citation tab", style={"textDecoration": "underline dashed"}),
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
        info_lines.extend([
            html.Br(),
            html.Span("danger level: " + row.Dangerous)
        ])


    # ---------- BLURB ----------
    info_lines.extend([
        html.Br(), html.Br(),
        html.Span(summary or "No summary available."), html.Br(),
        html.A("Wikipedia ↗", href=url, target="_blank"),
        html.Br(), html.Br()
    ])

    # ---------- DATABASE COMMENTS (only when present) ----------------
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
        ])






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
    Input("wiki-toggle",    "value"),
    Input("popular-toggle", "value"),
    State("common-dd",      "value"),
)
def filter_common(wiki_val, pop_val, current):
    df_use = df.copy()

    if "wiki" in wiki_val:
        df_use = df_use[df_use["has_wiki_page"]]

    if "pop" in pop_val:
        df_use = df_use[df_use["Genus_Species"].isin(popular_set)]

    # rebuild common-name list
    opts = [
        {"label": r["dropdown_label"], "value": r["Genus_Species"]}
        for _, r in df_use.iterrows()
    ]

    valid_vals = {o["value"] for o in opts}
    return opts, current if current in valid_vals else None

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
    Output("search-panel",  "style"),
    Output("search-handle", "children"),
    Output("search-handle", "className"),
    Input("search-handle",  "n_clicks"),
    State("search-panel",   "style"),
    prevent_initial_call=True
)
def toggle_search_box(n, panel_style):
    hidden = panel_style and panel_style.get("display") == "none"
    if hidden:
        return {}, "‹", "search-handle"  # Expand panel
    else:
        return {"display": "none"}, "›", "search-handle collapsed"  # Collapse


# -----------------------------------------------------------------------
#  Quick-jump: extremes in the *current* filtered dataset
# -----------------------------------------------------------------------
@app.callback(
    Output("selected-species", "data", allow_duplicate=True),
    #Input("deepest-btn",    "n_clicks"),
    #Input("shallowest-btn", "n_clicks"),
    Input("largest-btn",    "n_clicks"),
    Input("smallest-btn",   "n_clicks"),
    State("wiki-toggle",    "value"),
    State("popular-toggle", "value"),
    prevent_initial_call=True
)
def jump_to_extremes(n_large, n_small,
                     wiki_val, pop_val):
    trig = ctx.triggered_id
    if trig is None:                       # no button actually clicked
        raise PreventUpdate

    # ---------- build filtered frames ----------
    if trig in ("largest-btn", "smallest-btn"):
        # need rows that *have* a length

        size_on  = trig in ("largest-btn", "smallest-btn")
        depth_on = False                     # quick-jump is size-only now
        df_use   = get_filtered_df(size_on, depth_on,
                                   wiki_val, pop_val, seed=None)

        df_use = df_use.sort_values(["Length_cm", "Length_in"])
        if df_use.empty:
            raise PreventUpdate
        row = df_use.iloc[-1] if trig == "largest-btn" else df_use.iloc[0]

    else:  # depth buttons

        size_on  = trig in ("largest-btn", "smallest-btn")
        depth_on = False                     # quick-jump is size-only now
        df_use   = get_filtered_df(size_on, depth_on,
                                   wiki_val, pop_val, seed=None)

        df_use = df_use.assign(
            sort_shallow=df_use["DepthRangeComShallow"]
                           .fillna(df_use["DepthRangeShallow"]),
            sort_deep=df_use["DepthRangeComDeep"]
                        .fillna(df_use["DepthRangeDeep"])
        )
        # sort by *deep* first, fall back to shallow if needed
        df_use = df_use.sort_values(["sort_deep", "sort_shallow"])
        if df_use.empty:
            raise PreventUpdate
        row = df_use.iloc[-1] if trig == "deepest-btn" else df_use.iloc[0]

    return row["Genus_Species"]


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


@app.callback(
    Output("selected-species", "data", allow_duplicate=True),
    Input("next-btn",  "n_clicks"),
    Input("prev-btn",  "n_clicks"),
    State("size-toggle",      "value"),
    State("depth-toggle",     "value"),
    State("wiki-toggle",      "value"),
    State("popular-toggle",   "value"),
    State("selected-species", "data"),
    State("rand-seed",        "data"),
    prevent_initial_call=True
)
def step_size(n_next, n_prev,
              size_val, depth_val, wiki_val, pop_val,
              current, seed):
    trig = ctx.triggered_id
    if trig not in ("prev-btn", "next-btn"):
        raise PreventUpdate
    size_on  = "size"  in size_val
    depth_on = "depth" in depth_val
    df_use   = get_filtered_df(size_on, depth_on,
                               wiki_val, pop_val, seed)
    if df_use.empty:
        raise PreventUpdate

    df_use = df_use.sort_values(["Length_cm", "Length_in"])
    species = df_use["Genus_Species"].tolist()
    if current not in species:
        current = species[0]

    idx = species.index(current)
    idx = (idx - 1) % len(species) if ctx.triggered_id == "prev-btn" \
         else (idx + 1) % len(species)
    return species[idx]


@app.callback(
    Output("selected-species", "data", allow_duplicate=True),
    Input("up-btn",   "n_clicks"),
    Input("down-btn", "n_clicks"),
    State("size-toggle",      "value"),
    State("depth-toggle",     "value"),
    State("wiki-toggle",      "value"),
    State("popular-toggle",   "value"),
    State("selected-species","data"),
    State("rand-seed",       "data"),
    prevent_initial_call=True
)
def step_depth(n_up, n_down,
               size_val, depth_val, wiki_val, pop_val,
               current, seed):
    trig = ctx.triggered_id
    if trig not in ("up-btn", "down-btn"):
        raise PreventUpdate

    size_on  = "size"  in size_val
    depth_on = "depth" in depth_val
    df_use   = get_filtered_df(size_on, depth_on,
                               wiki_val, pop_val, seed)
    if df_use.empty:
        raise PreventUpdate

    df_use = df_use.sort_values("RandDepth")
    species = df_use["Genus_Species"].tolist()
    if current not in species:
        current = species[0]

    idx = species.index(current)
    idx = (idx - 1) % len(species) if ctx.triggered_id == "up-btn" \
         else (idx + 1) % len(species)
    return species[idx]


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


if __name__ == "__main__":
    app.run(debug=True)

    raise PreventUpdate                      
