import pandas as pd, requests
from functools import lru_cache

def cm_to_in(cm):
    return round(cm / 2.54, 1) if pd.notna(cm) else None

def m_to_ft(m):
    return round(m * 3.28084, 1) if pd.notna(m) else None

@lru_cache(maxsize=1)
def _raw_csv(csv_path="data/processed/filtered_combined_species.csv") -> pd.DataFrame:
    """
    Read the 52 MB CSV exactly once per interpreter process and cache it.
    Nothing else should touch disk.
    """
    print("• loading master CSV…")
    return pd.read_csv(csv_path)
    
    
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

@lru_cache(maxsize=1)
def load_species_data() -> pd.DataFrame:
    df = _raw_csv().copy()

    homo = load_homo_sapiens()

    # --- make sure both frames share the same columns -----------------
    missing_in_homo = df.columns.difference(homo.columns)
    for col in missing_in_homo:
        homo[col] = pd.NA

    missing_in_df = homo.columns.difference(df.columns)
    for col in missing_in_df:
        df[col] = pd.NA

    df = pd.concat([df, homo[df.columns]], ignore_index=True)
    # ------------------------------------------------------------------


    # clean + derived cols (vectorised → fast)
    df["Genus"]        = df["Genus"].str.strip()
    df["Species"]      = df["Species"].str.strip()
    df["Genus_Species"]= df["Genus"] + " " + df["Species"]

    # length / depth helpers
    df["Length_cm"] = df["Length"]
    df["Length_in"] = df["Length_cm"].apply(cm_to_in)

    for col in ["DepthRangeComShallow", "DepthRangeComDeep",
                "DepthRangeShallow",    "DepthRangeDeep"]:
        df[f"{col}_ft"] = df[col].apply(m_to_ft)

    df["DepthComPreferred"] = ~(
        df["DepthRangeComShallow"].isna() | df["DepthRangeComDeep"].isna()
    )

    # one‑line dropdown label (matches the *old* behaviour exactly)
    df["dropdown_label"] = (
        df["FBname"].fillna("")
          .str.cat(df["Genus_Species"].radd(" ("), na_rep="")
          .str.rstrip("(").add(")")
          .str.replace(" ()", "", regex=False)
    )

    return df


def load_name_table() -> pd.DataFrame:
    cols = ["Genus", "Species", "FBname", "has_wiki_page", "Genus_Species",
            "dropdown_label"]
    return load_species_data()[cols]
    
    
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
        "Dangerous":           "high",
        "Longevity":         73,
        "Genus_Species":        "Homo sapiens"

    }])
