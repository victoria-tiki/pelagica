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
from src.wiki import get_blurb, get_commons_thumb          # cached versions!


# ---------- Load & prep dataframe ---------------------------------------------------
df = load_species_data()          # your helper in src/data.py
df_wiki = df[df["has_wiki_page"]].copy() #only those with wikipedia page

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

# --------------------------------------------------------------------
#  Search stack (common • scientific • random)
# --------------------------------------------------------------------

# TOP BAR
top_bar = html.Div(id="top-bar", children=[
    html.Img(src="/assets/logo_pelagica.webp",
             id="logo",
             style={"height": "100px"})      # adjust height if you like
])

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
        html.Button("random", id="random-btn", className="btn btn-secondary"),
        style={"display": "flex", "justifyContent": "center"}
    )
])

# >>> NEW  –  fixed panel that lives on its own
search_panel = html.Div(search_stack, id="search-panel")


# --------------------------------------------------------------------
#  Settings OFF-canvas
# --------------------------------------------------------------------
settings_panel = dbc.Offcanvas(
    id="settings-canvas",
    placement="end",            # panel slides in from the right
    title="Controls",
    is_open=False,
    close_button=False,
    style={"width": "300px"},   # keep width constant for easy math
    children=[
        html.H6("Units"),
        dbc.RadioItems(
            id="units-toggle",
            value="metric",
            inline=True,
            options=[
                {"label": "Metric",   "value": "metric"},
                {"label": "Imperial", "value": "imperial"}
            ]
        ),
        html.Hr(style={"opacity": .3}),
        html.P("More toggles coming soon…", className="text-muted")
    ]
)

# --------------------------------------------------------------------
#  Citations OFF-canvas
# --------------------------------------------------------------------
citations_panel = dbc.Offcanvas(
    id="citations-canvas",
    placement="start",          # panel slides in from the left
    title="Citations",
    is_open=False,
    close_button=False,
    backdrop=False,
    style={"width": "300px"},
    children=html.Div(id="citation-box", style={"whiteSpace": "pre-wrap"})
)



# --------------------------------------------------------------------
#  Centre-page flex wrapper
# --------------------------------------------------------------------
centre_flex = html.Div(id="page-centre-flex", children=[
    html.Div(id="species-titles"),
    html.Div(id="image-wrapper", children=[
        html.Img(id="species-img"),
        # --- info card ---
        html.Div(id="info-card", children=[
            html.Div(id="info-close", children="✕"),
            html.Div(id="info-content")
        ]),
        # --- tiny handle to reopen ---
        html.Div("i", id="info-handle", style={"display":"none"})
    ])
])



# --------------------------------------------------------------------
#  Assemble Layout
# --------------------------------------------------------------------
# footer credit  (replace the faulty line)
footer = html.Div(
    [
        html.Span("created by "),
        html.A("Victoria",
               href="https://victoriatiki.com",
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
#  Assemble Layout
app.layout = dbc.Container([
    search_panel,
    top_bar,
    settings_panel,
    citations_panel,

    # -- side tabs, rendered once and slid by callbacks --
    html.Div("citations",      id="citations-tab", className="side-tab"),
    html.Div("⚙ Control Panel",id="settings-tab",  className="side-tab"),
    html.Div("report a bug",   id="bug-tab",       className="side-tab"),

    html.Div(centre_flex, id="main-content", style={"display": "none"}),
    footer,
    dcc.Store(id="selected-species")
], fluid=True)




# -------------------------------------------------------------------
# Callback 1 – populate species options whenever genus changes
# -------------------------------------------------------------------
@app.callback(
    Output("species-dd", "options"),
    Output("species-dd", "value"),
    Input("genus-dd", "value"),
    prevent_initial_call=True
)
def update_species_options(genus):
    if not genus:
        return [], None
    species_list = sorted(df_wiki.loc[df["Genus"] == genus, "Species"].unique())
    options = [{"label": s, "value": s} for s in species_list]
    # auto-select if only one species
    auto_val = species_list[0] if len(species_list) == 1 else None
    return options, auto_val



# -------------------------------------------------------------------
# Callback 2 – whenever any chooser fires, update selected-species
# -------------------------------------------------------------------
@app.callback(
    Output("selected-species", "data"),
    Input("species-dd", "value"),
    Input("genus-dd", "value"),
    Input("common-dd", "value"),
    Input("random-btn", "n_clicks"),
    prevent_initial_call=True
)
def choose_species(species_val, genus_val, common_val, rnd):
    trig = ctx.triggered_id

    if trig == "random-btn":
        row = df_wiki.sample(1).iloc[0]
        return f"{row.Genus} {row.Species}"

    if trig == "common-dd" and common_val:
        return common_val        # common dropdown already stores "Genus Species"

    if trig in ("genus-dd", "species-dd") and genus_val and species_val:
        return f"{genus_val} {species_val}"

    # no valid selection yet
    raise PreventUpdate


# --- open/close SETTINGS ---------------------------------------------------
@app.callback(Output("settings-canvas","is_open"),
              Input("settings-tab","n_clicks"), State("settings-canvas","is_open"))
def toggle_settings(n, opened):
    if not n:  # None / 0 clicks
        raise PreventUpdate
    return not opened

# --- open/close CITATIONS --------------------------------------------------
@app.callback(Output("citations-canvas","is_open"),
              Input("citations-tab","n_clicks"), State("citations-canvas","is_open"))
def toggle_citations(n, opened):
    if not n:
        raise PreventUpdate
    return not opened
    
#------ toggle INFO -------

@app.callback(
    Output("info-card",   "style"),
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
    _, author, lic, lic_url, up, ret = get_commons_thumb(genus, species)
    today = datetime.date.today().isoformat()

    if not author:  # no image metadata → show fallback text
        return html.I("No image credit available.")

    return [
        html.Span("Image © "),
        html.Strong(author),
        html.Span(", "),
        html.Span((lic or "") + " "),
        html.A("(license link)", href=lic_url) if lic_url else None,
        html.Span(f" — uploaded {up}, retrieved {ret} from WikimediaCommons"),
        html.Br(), html.Br(),

        html.Span("Text excerpt: Wikipedia — CC BY-SA 4.0, retrieved "),
        html.Span(today),
        html.Br(), html.Br(),

        html.Span("Taxonomic data, depths, and lengths from "),
        html.A("FishBase",   href="https://www.fishbase.se/",    target="_blank"),
        html.Span(" / "),
        html.A("SeaLifeBase", href="https://www.sealifebase.ca/", target="_blank")
    ]



# populate image + overlay + titles whenever species changes
@app.callback(
    Output("species-img", "src"),
    Output("info-content", "children"),
    Output("species-titles", "children"),          # <-- new output
    Input("selected-species", "data"))
def update_image(gs_name):
    if not gs_name:
        raise PreventUpdate

    genus, species = gs_name.split(" ", 1)
    summary, url = get_blurb(genus, species)
    thumb, _, _, _, _, _ = get_commons_thumb(genus, species)

    # titles
    common = df_wiki.loc[
        df_wiki["Genus_Species"] == gs_name, "FBname"
    ].iloc[0]
    titles = [
        html.H1(common),
        html.H4(gs_name)
    ]

    info_lines = [
        html.Strong(gs_name),
        html.Br(),
        html.Span("size: …  |  depth: …"),
        html.Br(), html.Br(),
        html.Span(summary or "No summary available."),
        html.Br(),
        html.A("Wikipedia ↗", href=url, target="_blank")
    ]
    return thumb or "/assets/placeholder_fish.webp", info_lines, titles


@app.callback(
    Output("main-content", "style"),
    Input("selected-species", "data")
)
def show_main_content(gs_name):
    if not gs_name:
        return {"display": "none"}
    return {"display": "block"}

PANEL_WIDTH = 300  # must match the width you set via style

# move citations tab
@app.callback(
    Output("citations-tab", "style"),
    Input("citations-canvas", "is_open")
)
def slide_citation_tab(opened):
    if opened:
        return {"left": f"{PANEL_WIDTH}px"}   # slide right
    return {"left": "0px"}

# move settings tab
@app.callback(
    Output("settings-tab", "style"),
    Input("settings-canvas", "is_open")
)
def slide_settings_tab(opened):
    if opened:
        return {"right": f"{PANEL_WIDTH}px"}  # slide left
    return {"right": "0px"}



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




if __name__ == "__main__":
    app.run(debug=True)

