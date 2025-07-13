#!/usr/bin/env python3
"""
enrich_with_wiki.py
-------------------
Adds a boolean `has_wiki_page` column to
data/processed/filtered_combined_species.csv
by querying Wikipedia *once* in batched calls
and caching the result on disk.

Run:  python scripts/enrich_with_wiki.py          # uses cache if present
       python scripts/enrich_with_wiki.py --refresh   # force fresh check
"""

import argparse
import json
import pathlib
import time

import pandas as pd
import requests
from tqdm import tqdm

CSV_PATH   = pathlib.Path("data/processed/filtered_combined_species.csv")
CACHE_PATH = pathlib.Path("cache/wiki_exists.json")
CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Pelagica/0.1 (contact: victoria.t.tiki@gmail.com)"
}


# --------------------------------------------------------------------------- #
# Helper: batched Wikipedia existence check
# --------------------------------------------------------------------------- #
def wiki_pages_exist(names, force_refresh=False, batch_size=50):
    """
    names : list[str] of "Genus Species"
    Returns a set of names that *do* have an article.
    Results are cached to cache/wiki_exists.json
    """
    if CACHE_PATH.exists() and not force_refresh:
        return set(json.loads(CACHE_PATH.read_text()))

    url = "https://en.wikipedia.org/w/api.php"
    existing = set()
    start = time.time()

    for i in tqdm(range(0, len(names), batch_size),
                  desc="Querying Wikipedia", unit="batch"):
        batch = names[i:i + batch_size]
        params = {
            "action": "query",
            "titles": "|".join(batch),
            "format": "json"
        }
        res = requests.get(url, params=params, headers=HEADERS, timeout=10)
        res.raise_for_status()
        for page in res.json()["query"]["pages"].values():
            if "missing" not in page:                   # page exists
                existing.add(page["title"])

        # incremental save every ~10 batches
        if (i // batch_size) % 10 == 0:
            CACHE_PATH.write_text(json.dumps(list(existing)))

    CACHE_PATH.write_text(json.dumps(list(existing)))
    print(f"🗂️  Cached {len(existing)} pages in"
          f" {time.time() - start:.1f} s → {CACHE_PATH}")
    return existing


# --------------------------------------------------------------------------- #
# Main enrichment routine
# --------------------------------------------------------------------------- #
def main(refresh=False):
    print("📑 Loading combined CSV …")
    df = pd.read_csv(CSV_PATH)

    # Ensure Genus_Species helper column exists
    if "Genus_Species" not in df.columns:
        df["Genus"] = df["Genus"].astype(str).str.strip()
        df["Species"] = df["Species"].astype(str).str.strip()
        df["Genus_Species"] = df["Genus"] + " " + df["Species"]

    unique_names = sorted(set(df["Genus_Species"]))

    print("🔎 Checking Wikipedia existence …")
    existing = wiki_pages_exist(unique_names, force_refresh=refresh)

    df["has_wiki_page"] = df["Genus_Species"].isin(existing)

    df.to_csv(CSV_PATH, index=False)
    print(f"✅ Enriched CSV saved ({CSV_PATH}).")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Append has_wiki_page flag to species CSV"
    )
    parser.add_argument("--refresh", action="store_true",
                        help="Force rebuild of Wikipedia cache")
    args = parser.parse_args()

    main(refresh=args.refresh)

