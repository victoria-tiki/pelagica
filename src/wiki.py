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
from rembg import remove
from PIL import Image
import io, base64

from src.image_cache import (
    url_to_stem, load_cached_image_and_meta, save_image_to_cache,
    save_metadata_to_cache, enforce_cache_limit, get_cached_image_path
)
from src.text_cache import load_cached_blurb, save_cached_blurb
import os
import gc


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
    Uses a persistent disk-backed cache keyed by genus, species, and sentence count.
    """
    key_string = f"{genus.strip().lower()}_{species.strip().lower()}_{sentences}"
    stem = url_to_stem(key_string)

    cached = load_cached_blurb(stem)
    if cached:
        return cached.get("summary"), cached.get("page_url")

    title = f"{genus}_{species}".replace(" ", "_")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(title)}"

    try:
        with requests.get(url, headers=HEADERS, timeout=10) as r:
            r.raise_for_status()
            data = r.json()

        summary = html.unescape(data.get("extract", ""))
        summary = ". ".join(summary.split(". ")[:sentences]).strip() + "."
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page")

        save_cached_blurb(stem, {"summary": summary, "page_url": page_url})

        del data
        gc.collect()
        return summary, page_url

    except Exception as e:
        print(f"[blurb cache] Failed to fetch summary for {genus} {species}: {e}")
        return None, None

        
'''
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

    return summary, page_url'''


# ---------- Image + attribution (robust) ---------------------------


@lru_cache(maxsize=1000)
def get_commons_thumb(genus: str,
                      species: str,
                      width: int = 640
) -> tuple[str | None, str | None, str | None, str | None,
           str | None, str | None]:
    title_plain = f"{genus} {species}"
    key = f"{title_plain}_{width}"
    stem = url_to_stem(key)

    cached_path, cached_meta = load_cached_image_and_meta(key)
    if cached_path and cached_meta:
        return (
            f"/cached-images/{os.path.basename(cached_path)}",
            cached_meta.get("author"),
            cached_meta.get("licence"),
            cached_meta.get("licence_url"),
            cached_meta.get("upload_date"),
            cached_meta.get("retrieval_date"),
        )

    # --- Wikipedia PageImages API ---
    try:
        with requests.get("https://en.wikipedia.org/w/api.php",
                          params=dict(action="query", titles=title_plain,
                                      prop="pageimages", piprop="thumbnail|name",
                                      pithumbsize=width, redirects=1, format="json"),
                          headers=HEADERS, timeout=10) as r:
            pages = r.json().get("query", {}).get("pages", {})
            page = next(iter(pages.values()), {})
            file_name = page.get("pageimage")
            raw_thumb_url = page.get("thumbnail", {}).get("source")

        del r, pages, page
    except Exception as e:
        print(f"[Commons] Failed to get PageImages: {e}")
        return (None,) * 6

    # --- Fallback to image list if no thumbnail ---
    if not raw_thumb_url:
        try:
            with requests.get("https://en.wikipedia.org/w/api.php",
                              params=dict(action="query", titles=title_plain,
                                          prop="images", imlimit=50,
                                          redirects=1, format="json"),
                              headers=HEADERS, timeout=10) as r2:
                pages2 = r2.json().get("query", {}).get("pages", {})
                files = [img["title"] for p in pages2.values()
                         for img in p.get("images", [])]

            file_name = next((f.split("File:")[-1] for f in files
                              if f.lower().endswith((".jpg", ".jpeg", ".png"))), None)

            if not file_name:
                return (None,) * 6

            raw_thumb_url = (f"https://commons.wikimedia.org/w/index.php"
                             f"?title=Special:FilePath/{quote_plus(file_name)}"
                             f"&width={width}")

            del r2, pages2, files
        except Exception as e:
            print(f"[Commons fallback] Failed to list images: {e}")
            return (None,) * 6

    # --- Get metadata from Commons ---
    try:
        with requests.get("https://commons.wikimedia.org/w/api.php",
                          params=dict(action="query", titles=f"File:{file_name}",
                                      prop="imageinfo",
                                      iiprop="extmetadata|url|timestamp",
                                      iiurlwidth=width,
                                      format="json"),
                          headers=HEADERS, timeout=10) as r3:
            page = next(iter(r3.json()["query"]["pages"].values()))
            if "imageinfo" not in page:
                return (None,) * 6
            info = page["imageinfo"][0]
            meta = info["extmetadata"]

        raw_author = (meta.get("Artist", {}).get("value") or
                      meta.get("Credit", {}).get("value") or
                      meta.get("Attribution", {}).get("value") or "")
        author = clean_html(raw_author) or "Unknown author"
        licence = clean_html(meta.get("LicenseShortName", {}).get("value", ""))
        licence_url = meta.get("LicenseUrl", {}).get("value", "")
        upload_date = info.get("timestamp", "")[:10]
        retrieval_date = datetime.date.today().isoformat()

        del r3, page, meta, info
    except Exception as e:
        print(f"[Commons metadata] Failed: {e}")
        return (None,) * 6

    # --- Download + background removal ---
    try:
        with requests.get(raw_thumb_url, headers=HEADERS, timeout=10) as response:
            response.raise_for_status()
            processed_image = remove(response.content)

        save_image_to_cache(stem, processed_image)
        save_metadata_to_cache(stem, {
            "author": author,
            "licence": licence,
            "licence_url": licence_url,
            "upload_date": upload_date,
            "retrieval_date": retrieval_date,
            "thumb_url": raw_thumb_url
        })

        enforce_cache_limit()
        gc.collect()

        return (
            f"/cached-images/{os.path.basename(get_cached_image_path(stem))}",
            author, licence, licence_url, upload_date, retrieval_date
        )

    except Exception as e:
        print(f"[rembg/cache] Failed to process image for {genus} {species}: {e}")
        return (None,) * 6



'''
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
    
    #thumb_url = page.get("thumbnail", {}).get("source")
    raw_thumb_url = page.get("thumbnail", {}).get("source")
    #thumb_url = remove_background_base64(raw_thumb_url, headers=HEADERS)
    
    if raw_thumb_url and "wikimedia.org/static/images/" not in raw_thumb_url:
        thumb_url = remove_background_base64(raw_thumb_url, headers=HEADERS)
    else:
        thumb_url = raw_thumb_url  

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
            return (None,)*6  # Nothing usable

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

    #fallback if no imageinfo
    page = next(iter(r3.json()["query"]["pages"].values()))
    if "imageinfo" not in page:               # ← no image
        return None, None, None, None, None, None

    info = page["imageinfo"][0]
    
    return (thumb_url, author, licence, licence_url,
            upload_date, retrieval_date)'''



def remove_background_base64(image_url: str, headers: dict = None) -> str | None:
    """
    Downloads an image from a URL, removes its background using rembg,
    and returns a base64-encoded PNG string.

    Parameters
    ----------
    image_url : str
        The URL of the image to download and process.
    headers : dict, optional
        HTTP headers to use when fetching the image (e.g. User-Agent)

    Returns
    -------
    str | None
        A data:image/png;base64,... string if successful, or None on failure.
    """
    try:
        r = requests.get(image_url, headers=headers, timeout=10)
        r.raise_for_status()
        input_data = r.content

        output_data = remove(input_data)
        b64_img = base64.b64encode(output_data).decode("utf-8")
        return f"data:image/png;base64,{b64_img}"

    except Exception as e:
        print(f"[rembg] Failed to process image: {e}")
        return None





