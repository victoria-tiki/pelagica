import pandas as pd, requests

def cm_to_in(cm):
    return round(cm / 2.54, 1) if pd.notna(cm) else None

def m_to_ft(m):
    return round(m * 3.28084, 1) if pd.notna(m) else None


# ------------- NEW: batch query Wikipedia once --------------------
def _wiki_pages_exist(names, batch_size=50):
    """
    Return a set of 'Genus Species' strings that have a Wikipedia page.
    Uses api.php titles=... in batches of ≤50 (Wikimedia limit).
    """
    existing = set()
    url = "https://en.wikipedia.org/w/api.php"

    for i in range(0, len(names), batch_size):
        batch = names[i:i + batch_size]
        params = {"action": "query",
                  "titles": "|".join(batch),
                  "format": "json"}
        r = requests.get(url, params=params, timeout=10)
        for pg in r.json().get("query", {}).get("pages", {}).values():
            if "missing" not in pg:                # page exists
                existing.add(pg["title"])          # already "Genus Species"
    return existing
# ------------------------------------------------------------------


def load_species_data(csv_path="data/processed/filtered_combined_species.csv"):
    df = pd.read_csv(csv_path)
    ...
    df["dropdown_label"] = df.apply(
        lambda row: f"{row['FBname']} ({row['Genus_Species']})"
        if pd.notna(row["FBname"]) else row["Genus_Species"],
        axis=1
    )

    # ------------- NEW: mark which species actually exist on Wikipedia --------
    print("🔎 One-time check: which species have a Wikipedia page …")
    existing = _wiki_pages_exist(df["Genus_Species"].tolist())
    df["has_wiki_page"] = df["Genus_Species"].isin(existing)
    # --------------------------------------------------------------------------

    return df


def load_species_data(csv_path="data/processed/filtered_combined_species.csv"):
    df = pd.read_csv(csv_path)
    
    homo = load_homo_sapiens()
    homo = homo.dropna(axis=1, how="all")
    df = pd.concat([df, homo], ignore_index=True)
    
    # Trim whitespace
    df["Genus"] = df["Genus"].astype(str).str.strip()
    df["Species"] = df["Species"].astype(str).str.strip()

    # Full scientific name
    df["Genus_Species"] = df["Genus"] + " " + df["Species"]

    # Filter out species with no usable depth info (both pairs missing)
    no_common = df["DepthRangeComShallow"].isna() | df["DepthRangeComDeep"].isna()
    no_general = df["DepthRangeShallow"].isna() | df["DepthRangeDeep"].isna()
    df = df[~(no_common & no_general)].copy()

    # Convert depth and length values
    df["Length_cm"] = df["Length"]
    df["Length_in"] = df["Length_cm"].apply(cm_to_in)

    for col in ["DepthRangeComShallow", "DepthRangeComDeep",
                "DepthRangeShallow", "DepthRangeDeep"]:
        df[f"{col}_ft"] = df[col].apply(m_to_ft)

    # Depth preference flag
    df["DepthComPreferred"] = ~(df["DepthRangeComShallow"].isna() | df["DepthRangeComDeep"].isna())

    # For search
    df["dropdown_label"] = df.apply(
        lambda row: f"{row['FBname']} ({row['Genus_Species']})" if pd.notna(row["FBname"]) else row["Genus_Species"],
        axis=1
    )

    return df


def load_homo_sapiens():
    return pd.DataFrame([{
        "SpecCode":              "0",
        "Genus":               "Homo",
        "Species":             "sapiens",
        "FBname":              "Human",

        "has_wiki_page":       True,  
        "Database":             0,

        "Length":           165.0, # e.g. 12.3

        "DepthRangeComShallow": None,
        "DepthRangeComDeep":    None,
        "DepthRangeShallow":    0,
        "DepthRangeDeep":       103.0,
        "DemersPelag":          "others",
        "Vulnerability":          None,
        "LTypeMaxM":            "SL",
        "CommonLength":           None,
        "LTypeComM":              None,
        "LongevityWild":          73,
        "Electrogenic":            None, 
        "Comments":                None,
        

        "Fresh":               0,
        "Saltwater":           0,
        "Brack":               0,
        "Dangerous":           "extreme",
        "Longevity":         73,
        "Genus_Species":        "Homo sapiens"

    }])
