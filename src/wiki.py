"""
Lightweight helpers for Pelagica
--------------------------------
• get_blurb(genus, species)        → summary, page_url
• get_commons_thumb(genus, species)→ thumb_url, author, licence, licence_url
Both return (None, …) if nothing found, so caller can handle gracefully.
"""

from __future__ import annotations
import requests, html
from urllib.parse import quote_plus
import re, datetime
from functools import lru_cache


HEADERS = {
    # Tell Wikimedia who you are (policy requirement)
    "User-Agent": "Pelagica/0.1 (contact: victoria.t.tiki@gmail.com)"
}


TAGSTRIP = re.compile(r"<[^>]+>")  # remove any HTML tags

def clean_html(raw: str) -> str:
    return TAGSTRIP.sub("", raw or "").strip()


# ---------- Text summary (Wikipedia REST API) ----------------------
@lru_cache(maxsize=1000)
def get_blurb(genus: str, species: str, sentences: int = 2) -> tuple[str | None, str | None]:
    """
    Return a short plain-text blurb and canonical article URL.
    """
    title = f"{genus}_{species}".replace(" ", "_")
    url   = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(title)}"

    r = requests.get(url, headers=HEADERS, timeout=10)
    if r.status_code != 200:
        return None, None

    data     = r.json()
    summary  = html.unescape(data.get("extract", ""))
    summary  = ". ".join(summary.split(". ")[:sentences]) + "."
    page_url = data.get("content_urls", {}).get("desktop", {}).get("page")

    return summary, page_url


# ---------- Image + attribution (robust) ---------------------------
@lru_cache(maxsize=1000)
def get_commons_thumb(genus: str,
                      species: str,
                      width: int = 640
) -> tuple[str | None, str | None, str | None, str | None,
           str | None, str | None]:
    """
    Returns
    -------
    thumb_url, author, licence_short, licence_url,
    upload_date(ISO), retrieval_date(ISO)
    """
    
    
    title_plain = f"{genus} {species}"           # spaces, not underscores
    title_enc   = quote_plus(title_plain)

    # ---- Pass A: PageImages ----
    r = requests.get("https://en.wikipedia.org/w/api.php",
                     params=dict(action="query", titles=title_plain,
                                 prop="pageimages",
                                 piprop="thumbnail|name",
                                 pithumbsize=width,
                                 redirects=1,                # follow redirects
                                 format="json"),
                     headers=HEADERS, timeout=10)
    pages = r.json().get("query", {}).get("pages", {})
    page  = next(iter(pages.values()), {})
    file_name = page.get("pageimage")            # e.g. Blue_Whale_001.jpg
    thumb_url = page.get("thumbnail", {}).get("source")

    # ---- Pass B: fallback if no lead image ----
    if not thumb_url:
        r2 = requests.get("https://en.wikipedia.org/w/api.php",
            params=dict(action="query", titles=title_plain,
                        prop="images", imlimit=50, redirects=1, format="json"),
            headers=HEADERS, timeout=10)
        pages2 = r2.json().get("query", {}).get("pages", {})
        files  = [img["title"] for p in pages2.values()
                               for img in p.get("images", [])]
        file_name = next((f.split("File:")[-1] for f in files
                          if f.lower().endswith((".jpg", ".jpeg", ".png"))),
                         None)
        if not file_name:
            return (None,)*4  # Nothing usable

        # get an on-the-fly thumbnail, same width
        thumb_url = (f"https://commons.wikimedia.org/w/index.php"
                     f"?title=Special:FilePath/{quote_plus(file_name)}"
                     f"&width={width}")

    r3 = requests.get("https://commons.wikimedia.org/w/api.php",
        params=dict(action="query", titles=f"File:{file_name}",
                    prop="imageinfo",
                    iiprop="extmetadata|url|timestamp",
                    iiurlwidth=width,
                    format="json"),
        headers=HEADERS, timeout=10)
    info = next(iter(r3.json()["query"]["pages"].values()))["imageinfo"][0]
    meta = info["extmetadata"]

    # ------- AUTHOR (try Artist, then Credit, then Attribution) -----
    raw_author = (meta.get("Artist", {}).get("value") or
                  meta.get("Credit", {}).get("value") or
                  meta.get("Attribution", {}).get("value") or "")
    author = clean_html(raw_author) or "Unknown author"

    # ------- LICENCE ------------------------------------------------
    licence     = clean_html(meta.get("LicenseShortName", {}).get("value", ""))
    licence_url = meta.get("LicenseUrl", {}).get("value", "")

    # ------- DATES --------------------------------------------------
    upload_date   = info.get("timestamp", "")[:10]          # 'YYYY-MM-DD'
    retrieval_date = datetime.date.today().isoformat()

    return (thumb_url, author, licence, licence_url,
            upload_date, retrieval_date)




