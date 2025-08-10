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
    df = _raw_csv()#.copy()
    
    # reduce memory
    cat_cols = ["Genus", "Species", "Genus_Species", "FBname", "DemersPelag", "Database", "LTypeMaxM", "LTypeComM", "Dangerous", "Electrogenic","has_wiki_page"]
    for col in cat_cols:
        df[col] = df[col].astype("category")
    df["Length"] = pd.to_numeric(df["Length"], downcast="float")
    for col in ["DepthRangeComShallow", "DepthRangeComDeep",
                "DepthRangeShallow", "DepthRangeDeep"]:
        df[col] = pd.to_numeric(df[col], downcast="float")
    df["LongevityWild"] = pd.to_numeric(df["LongevityWild"], downcast="integer")


    extra = get_extra_species()

    # --- make sure both frames share the same columns -----------------
    for col in df.columns.difference(extra.columns):
        extra[col] = pd.NA
    for col in extra.columns.difference(df.columns):
        df[col] = pd.NA

    df = pd.concat([df, extra[df.columns]], ignore_index=True)
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

@lru_cache(maxsize=1)
def load_species_with_taxonomy() -> pd.DataFrame:
    """Return the master species table WITH kingdom-…-genus columns."""
    df_sp  = load_species_data()                # your 52 MB main table
    df_tax = pd.read_csv("data/processed/gbif_taxonomy.csv")

    # normalise join key
    df_tax["scientificName"] = df_tax["scientificName"].str.strip()
    df_sp["Genus_Species"]   = df_sp["Genus_Species"].str.strip()

    merged = (
        df_sp
        .merge(df_tax, left_on="Genus_Species", right_on="scientificName",
               how="left", suffixes=("", "_tax"))
        .copy()
    )

    # optional: down-cast the taxonomy columns to category to save RAM
    for col in ["kingdom", "phylum", "class", "order", "family", "genus"]:
        merged[col] = merged[col].astype("category")

    return merged
    
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
        "Genus_Species":        "Homo sapiens",
        


        

    }])
    
    '''        "kingdom": "Animalia",
        "phylum": 	"Chordata",
        "class": 	"Mammalia",
        "order": 	"Primates",
        "family": 	"Hominidae",
        "genus":    "Homo"
        '''
    
def get_extra_species():
    """Concatenate all manually added species."""
    species_list = [
        load_homo_sapiens(),
        load_ambystoma_mexicanum(),
        load_necturus_maculosus(),
        load_castor_canadensis(),
        load_castor_fiber()

        # add more here like load_canis_lupus(), etc.
    ]
    return pd.concat(species_list, ignore_index=True)


def load_ambystoma_mexicanum():
    return pd.DataFrame([{
        "SpecCode": "1",                      # just needs to be unique
        "Genus": "Ambystoma",
        "Species": "mexicanum",
        "FBname": "Axolotl",
        "has_wiki_page": True,
        "Database": -1,                        # ← this ensures special citation handling

        # everything else is intentionally left blank or None
        "Length": 45,
        "DepthRangeComShallow": 0.0,
        "DepthRangeComDeep": 1.0,
        "DepthRangeShallow": None,
        "DepthRangeDeep": None,
        "DemersPelag": None,
        "Vulnerability": None,
        "LTypeMaxM": None,
        "CommonLength": None,
        "LTypeComM": None,
        "LongevityWild": None,
        "Electrogenic": None,
        "Comments": None,

        "Fresh": 1,
        "Saltwater": 0,
        "Brack": 0,
        "Dangerous": None,
        "Longevity": None,

        "Genus_Species": "Ambystoma mexicanum"
    }])


def load_necturus_maculosus():
    return pd.DataFrame([{
        "SpecCode": "2",                      # just needs to be unique
        "Genus": "Necturus",
        "Species": "maculosus",
        "FBname": "Common mudpuppy",
        "has_wiki_page": True,
        "Database": -2,                        # ← this ensures special citation handling

        # everything else is intentionally left blank or None
        "Length": 48.2,
        "DepthRangeComShallow": 0.0,
        "DepthRangeComDeep": 30.48,
        "DepthRangeShallow": None,
        "DepthRangeDeep": None,
        "DemersPelag": "benthopelagic",
        "Vulnerability": None,
        "LTypeMaxM": None,
        "CommonLength": None,
        "LTypeComM": None,
        "LongevityWild": 11,
        "Electrogenic": None,
        "Comments": None,

        "Fresh": 1,
        "Saltwater": 0,
        "Brack": 0,
        "Dangerous": None,
        "Longevity": None,

        "Genus_Species": "Necturus maculosus"
    }])




def load_castor_canadensis():
    return pd.DataFrame([{
        "SpecCode": "3",                      # just needs to be unique
        "Genus": "castor",
        "Species": "canadensis",
        "FBname": "North American Beaver",
        "has_wiki_page": True,
        "Database": -3,                        # ← this ensures special citation handling

        # everything else is intentionally left blank or None
        "Length": None,
        "DepthRangeComShallow": 0.0,
        "DepthRangeComDeep": 1.0,
        "DepthRangeShallow": None,
        "DepthRangeDeep": None,
        "DemersPelag": None,
        "Vulnerability": None,
        "LTypeMaxM": None,
        "CommonLength": None,
        "LTypeComM": None,
        "LongevityWild": None,
        "Electrogenic": None,
        "Comments": None,

        "Fresh": 1,
        "Saltwater": 0,
        "Brack": 0,
        "Dangerous": None,
        "Longevity": None,

        "Genus_Species": "Castor canadensis"
    }])

def load_castor_fiber():
    return pd.DataFrame([{
        "SpecCode": "4",                      # just needs to be unique
        "Genus": "castor",
        "Species": "fiber",
        "FBname": "Eurasian Beaver",
        "has_wiki_page": True,
        "Database": -4,                        # ← this ensures special citation handling

        # everything else is intentionally left blank or None
        "Length": 150, #Kitchener, A. (2001). Beavers. Essex: Whittet Books. ISBN 978-1-873580-55-4.
        "DepthRangeComShallow": 0.0,
        "DepthRangeComDeep": 1.0, 
        "DepthRangeShallow": None,
        "DepthRangeDeep": None,
        "DemersPelag": None,
        "Vulnerability": None,
        "LTypeMaxM": None,
        "CommonLength": None,
        "LTypeComM": None,
        "LongevityWild": None,
        "Electrogenic": None,
        "Comments": None,

        "Fresh": 1,
        "Saltwater": 0,
        "Brack": 0,
        "Dangerous": None,
        "Longevity": None,

        "Genus_Species": "Castor fiber"
    }])
