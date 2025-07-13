# app.py  – Pelagica MVP v0.2
# ----------------------------------------------
# Dash app with:
#   • Genus → Species cascading dropdowns
#   • Searchable common-name dropdown
#   • Random-species button
#   • Image + blurb + full citation panel

from dash.exceptions import PreventUpdate
from dash import Dash, dcc, html, Input, Output, State, ctx
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
app = Dash(__name__, external_stylesheets=[dbc.themes.LUX])

app.layout = dbc.Container([
    html.H1("Pelagica", className="my-3"),

    # Row 1: Genus → Species cascading
    dbc.Row([
        dbc.Col(dcc.Dropdown(id="genus-dd",
                             options=genus_options,
                             placeholder="Select Genus")),
        dbc.Col(dcc.Dropdown(id="species-dd",
                             placeholder="Select Species")),
    ], className="gy-2"),

    # Row 2: Common-name quick search
    dbc.Row([
        dbc.Col(dcc.Dropdown(id="common-dd",
                             options=common_options,
                             searchable=True,
                             placeholder="Search by common name…")),
        dbc.Col(html.Button("🔀 Random", id="random-btn",
                            className="btn btn-secondary"), width="auto"),
    ], className="gy-2 mb-4"),

    # Display panel
    html.Div(id="species-panel"),

    # Citation toggle
    html.Details([
        html.Summary("📚 Citations"),
        html.Div(id="citation-box", style={"whiteSpace": "pre-line",
                                           "fontSize": "0.9rem"})
    ], open=False, className="mt-4 mb-5"),
], fluid=True)


# -------------------------------------------------------------------
# Layout  (unchanged except we add dcc.Store)
# -------------------------------------------------------------------
app.layout = dbc.Container([
    html.H1("Pelagica", className="my-3"),

    dbc.Row([
        dbc.Col(dcc.Dropdown(id="genus-dd",
                             options=genus_options,
                             placeholder="Select Genus")),
        dbc.Col(dcc.Dropdown(id="species-dd",
                             placeholder="Select Species")),
    ], className="gy-2"),

    dbc.Row([
        dbc.Col(dcc.Dropdown(id="common-dd",
                             options=common_options,
                             searchable=True,
                             placeholder="Search by common name…")),
        dbc.Col(html.Button("🔀 Random", id="random-btn",
                            className="btn btn-secondary"), width="auto"),
    ], className="gy-2 mb-4"),

    html.Div(id="species-panel"),
    html.Details([
        html.Summary("📚 Citations"),
        html.Div(id="citation-box",
                 style={"whiteSpace": "pre-line", "fontSize": "0.9rem"})
    ], open=False, className="my-4"),

    # Hidden store to hold current selection ("Genus Species")
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



# -------------------------------------------------------------------
# Callback 3 – render panel & citations from the Store ONLY
# -------------------------------------------------------------------
@app.callback(
    Output("species-panel", "children"),
    Output("citation-box", "children"),
    Input("selected-species", "data"),
    prevent_initial_call=True
)
def render_panel(gs_name):
    if not gs_name:
        return "", ""

    genus, species = gs_name.split(" ", 1)

    # Wikipedia
    summary, wiki_url = get_blurb(genus, species)
    thumb, author, lic, lic_url, up, ret = get_commons_thumb(genus, species)

    img_src = thumb if thumb else "/assets/placeholder_fish.webp"
    img = html.Img(src=img_src, style={"maxWidth": "400px"})


    panel = [
        html.H2(gs_name),
        html.P(summary or "No Wikipedia summary available."),
        html.A("Read full article ↗", href=wiki_url, target="_blank"),
        html.Br(), img
    ]

    today = datetime.date.today().isoformat()
    cite = (
        f"Image © {author}, {lic} ({lic_url}) — uploaded {up}, retrieved {ret}\n\n"
        f"Text excerpt from Wikipedia — CC BY-SA 4.0, retrieved {today}\n"
        f"Species metadata (taxonomy, length, depth) from FishBase / SeaLifeBase"
    )

    return panel, cite



if __name__ == "__main__":
    app.run(debug=True)

