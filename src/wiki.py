
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
#from rembg import remove
import io, base64

from src.image_cache import (
    url_to_stem, load_cached_image_and_meta, save_image_to_cache,
    save_metadata_to_cache, enforce_cache_limit, get_cached_image_path
)
from src.text_cache import load_cached_blurb, save_cached_blurb
import os
import gc

import threading


# ---- Background-removal feature flag (env-driven) ----
ENABLE_BG_REMOVAL = os.getenv("ENABLE_BG_REMOVAL", "1") == "1"
_BG_MAX_SIDE = int(os.getenv("BG_MAX_SIDE", "800"))
_REMBG_SEM = threading.BoundedSemaphore(int(os.getenv("REMBG_MAX_CONCURRENCY", "1")))

# Toggle for cache writes: "1" = allow writes, "0" = read-only
CACHE_WRITE = os.getenv("CACHE_WRITE", "1") == "1"

#R2 toggle
IS_FLY = any(k in os.environ for k in ("FLY_APP_NAME", "FLY_ALLOC_ID", "FLY_REGION"))
USE_R2 = IS_FLY or os.getenv("USE_R2", "").strip().lower() in ("1", "true", "yes", "on")


# Internal: these are set only if/when ENABLE_BG_REMOVAL=True
_REMBG_SESSION = None
_REMBG_LOCK = threading.Lock()
_rembg_remove = None
_sessions_class = None
_ort = None
_Image = None  # <-- we'll set this lazily


def _lazy_load_rembg_stack():
    """Load rembg + onnxruntime + Pillow only when the feature is enabled."""
    global _rembg_remove, _sessions_class, _ort, _Image
    if _rembg_remove is not None:
        return
    from rembg import remove as _rm
    from rembg.sessions import sessions_class as _sc
    import onnxruntime as ort
    from PIL import Image as _PILImage  # <-- import PIL here
    _rembg_remove = _rm
    _sessions_class = _sc
    _ort = ort
    _Image = _PILImage

def _mem_saver_session(model_name="u2netp", providers=None):
    """Create an ORT session with arenas disabled so RSS returns after spikes."""
    # Find matching session class
    session_class = None
    for sc in _sessions_class:
        if sc.name() == model_name:
            session_class = sc
            break
    if session_class is None:
        session_class = _sessions_class[0]

    opts = _ort.SessionOptions()
    nthreads = int(os.getenv("OMP_NUM_THREADS", "1"))
    opts.intra_op_num_threads = nthreads
    opts.inter_op_num_threads = nthreads
    opts.enable_cpu_mem_arena = False    # key to avoid “sticky” RSS
    opts.enable_mem_pattern = False

    if providers is None:
        providers = ["CPUExecutionProvider"]
    return session_class(model_name, opts, providers)

def _get_rembg_session():
    """Singleton session (created on first use) with memory-friendly options."""
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        with _REMBG_LOCK:
            if _REMBG_SESSION is None:
                _lazy_load_rembg_stack()
                _REMBG_SESSION = _mem_saver_session(os.getenv("REMBG_MODEL", "u2netp"))
    return _REMBG_SESSION
    
def _maybe_remove_bg(img_bytes: bytes) -> bytes:
    if not ENABLE_BG_REMOVAL:
        return img_bytes

    # Ensure rembg + onnx + PIL are loaded
    _lazy_load_rembg_stack()

    # Pre-resize BEFORE model to cap memory
    try:
        with _Image.open(io.BytesIO(img_bytes)) as im:
            im = im.convert("RGBA")
            w, h = im.size
            mx = max(w, h)
            if mx > _BG_MAX_SIDE:
                scale = _BG_MAX_SIDE / float(mx)
                new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
                im = im.resize(new_size, _Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="PNG", optimize=True)
            img_bytes = buf.getvalue()
    except Exception:
        # If PIL not present or anything fails, skip pre-resize and continue
        pass

    try:
        with _REMBG_SEM:
            img_bytes = _rembg_remove(img_bytes, session=_get_rembg_session())
    except Exception:
        pass

    # Optional: encourage glibc to return free pages on Linux
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass

    return img_bytes


 
HEADERS = {
    "User-Agent": "Pelagica/0.1 (https://pelagica.victoriatiki.com; contact: victoria.t.tiki@gmail.com)"
}



TAGSTRIP = re.compile(r"<[^>]+>")  # remove any HTML tags

def clean_html(raw: str) -> str:
    return TAGSTRIP.sub("", raw or "").strip()


# ---------- Text summary (Wikipedia REST API) ----------------------

# Manual redirect equivalents for Wikipedia summary lookup
WIKI_NAME_EQUIVALENTS = {
    "Lutra felina": "Lontra felina",   
    "Magnapinna pacifica": "Bigfin squid",
    "Hydrophis platura" : "Hydrophis platurus",
    #"Aliger gigas": "queen conch"
}


@lru_cache(maxsize=512)
def get_blurb(genus: str, species: str, sentences: int = 2) -> tuple[str | None, str | None]:
    key_string = f"{genus.strip().lower()}_{species.strip().lower()}_{sentences}"
    stem = url_to_stem(key_string)

    cached = load_cached_blurb(stem)
    if cached:
        return cached.get("summary"), cached.get("page_url")

    def try_fetch(title: str):
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(title)}"
        try:
            with requests.get(url, headers=HEADERS, timeout=10) as r:
                r.raise_for_status()
                data = r.json()
            summary = html.unescape(data.get("extract", ""))
            summary = ". ".join(summary.split(". ")[:sentences]).strip() + "."
            page_url = data.get("content_urls", {}).get("desktop", {}).get("page")
            return summary, page_url
        except Exception as e:
            return None, None

    # Try the direct title first
    main_title = f"{genus}_{species}".replace(" ", "_")
    summary, page_url = try_fetch(main_title)

    if not summary:
        alt = WIKI_NAME_EQUIVALENTS.get(f"{genus} {species}")
        if alt:
            print(f"[blurb] Fallback to Wikipedia title for {genus} {species} → {alt}")
            summary, page_url = try_fetch(alt.replace(" ", "_"))

    if summary:
        if CACHE_WRITE:
            save_cached_blurb(stem, {"summary": summary, "page_url": page_url})
            gc.collect()
        else:
            # read-only mode: serve result but don't persist it
            pass
    else:
        print(f"[blurb] Failed to fetch summary for {genus} {species}")


    return summary, page_url


        
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


@lru_cache(maxsize=128)
def get_commons_thumb(genus: str,
                      species: str,
                      width: int = 640,
                      remove_bg: bool = True
) -> tuple[str | None, str | None, str | None, str | None,
           str | None, str | None]:

    title_plain = f"{genus} {species}"
    fallback_name = WIKI_NAME_EQUIVALENTS.get(title_plain)
    if fallback_name:
        title_plain = fallback_name

    # NEW: if the caller asked for background removal, always prefer the
    # already-processed cache first (independent of ENABLE_BG_REMOVAL).
    if remove_bg:
        proc_key  = f"{title_plain}_{width}"              # your processed key
        # try both key forms in case cache stored by stem in the past
        for candidate in (proc_key, url_to_stem(proc_key)):
            cached_path, cached_meta = load_cached_image_and_meta(candidate)
            if cached_meta:  # JSON present == cached
                stem_cand = url_to_stem(candidate)
                fname = os.path.basename(get_cached_image_path(stem_cand))
                return (
                    f"/cached-images/{fname}" + ("" if remove_bg else "?variant=raw"),
                    cached_meta.get("author"),
                    cached_meta.get("licence"),
                    cached_meta.get("licence_url"),
                    cached_meta.get("upload_date"),
                    cached_meta.get("retrieval_date"),
                )


    # ORIGINAL flow resumes here:
    effective_remove = remove_bg and ENABLE_BG_REMOVAL
    key  = f"{title_plain}_{width}" if effective_remove else f"{title_plain}_{width}_raw"
    stem = url_to_stem(key)

    _cached_path, cached_meta = load_cached_image_and_meta(key)
    if cached_meta:  # JSON present ⇒ cached
        fname = os.path.basename(get_cached_image_path(stem))  # "<stem>.webp"
        return (
            f"/cached-images/{fname}" + ("" if effective_remove else "?variant=raw"),
            cached_meta.get("author"),
            cached_meta.get("licence"),
            cached_meta.get("licence_url"),
            cached_meta.get("upload_date"),
            cached_meta.get("retrieval_date"),
        )


    # ---- Try PageImages for lead image + thumbnail URL ----
    try:
        with requests.get(
            "https://en.wikipedia.org/w/api.php",
            params=dict(action="query", titles=title_plain,
                        prop="pageimages", piprop="thumbnail|name",
                        pithumbsize=width, redirects=1, format="json"),
            headers=HEADERS, timeout=10
        ) as r:
            pages = r.json().get("query", {}).get("pages", {})
            page = next(iter(pages.values()), {})
            file_name = page.get("pageimage")
            raw_thumb_url = page.get("thumbnail", {}).get("source")
    except Exception as e:
        print(f"[Commons] Failed to get PageImages: {e}")
        return (None,) * 6

    # ---- Fallback: list images if no lead thumbnail ----
    if not raw_thumb_url:
        try:
            with requests.get(
                "https://en.wikipedia.org/w/api.php",
                params=dict(action="query", titles=title_plain,
                            prop="images", imlimit=50, redirects=1, format="json"),
                headers=HEADERS, timeout=10
            ) as r2:
                pages2 = r2.json().get("query", {}).get("pages", {})
                files = [img["title"] for p in pages2.values() for img in p.get("images", [])]

            file_name = next(
                (f.split("File:")[-1] for f in files if f.lower().endswith((".jpg", ".jpeg", ".png"))),
                None
            )
            if not file_name:
                return (None,) * 6

            raw_thumb_url = (
                f"https://commons.wikimedia.org/w/index.php"
                f"?title=Special:FilePath/{quote_plus(file_name)}&width={width}"
            )
        except Exception as e:
            print(f"[Commons fallback] Failed to list images: {e}")
            return (None,) * 6

    # ---- Get image metadata (author, license, upload date) ----
    try:
        with requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params=dict(action="query", titles=f"File:{file_name}",
                        prop="imageinfo", iiprop="extmetadata|url|timestamp",
                        iiurlwidth=width, format="json"),
            headers=HEADERS, timeout=10
        ) as r3:
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
    except Exception as e:
        print(f"[Commons metadata] Failed: {e}")
        return (None,) * 6

    # ---- Download -> (optional) pre-resize -> (optional) remove-bg ----
    try:
        import io
        from PIL import Image

        with requests.get(raw_thumb_url, headers=HEADERS, timeout=10) as response:
            response.raise_for_status()
            img_bytes = response.content

        # --- SAFETY A: hard cap per-image payload (default 1 MB) ---
        MAX_IMAGE_KB = int(os.getenv("MAX_IMAGE_KB", "1024"))
        if len(img_bytes) > MAX_IMAGE_KB * 1024:
            try:
                # Re-encode smaller (prefer WEBP; fall back to JPEG if WEBP unsupported)
                with Image.open(io.BytesIO(img_bytes)) as im:
                    im = im.convert("RGB")
                    buf = io.BytesIO()
                    quality = int(os.getenv("WEBP_QUALITY", "80"))
                    try:
                        im.save(buf, format="WEBP", quality=quality, method=6)  # WEBP path
                    except Exception:
                        im.save(buf, format="JPEG", quality=85, optimize=True)  # fallback
                    img_bytes = buf.getvalue()
            except Exception as e:
                print(f"[safety] shrink failed: {e}")
                return (None,) * 6
            if len(img_bytes) > MAX_IMAGE_KB * 1024:
                # Still too large? Bail to avoid unexpected egress.
                return (None,) * 6

        if effective_remove and img_bytes:
            # Pre-resize BEFORE rembg to cap memory/latency
            try:
                with Image.open(io.BytesIO(img_bytes)) as im:
                    im = im.convert("RGBA")
                    w, h = im.size
                    mx = max(w, h)
                    if mx > _BG_MAX_SIDE:
                        scale = _BG_MAX_SIDE / float(mx)
                        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
                        im = im.resize(new_size, Image.LANCZOS)
                    buf = io.BytesIO()
                    im.save(buf, format="PNG", optimize=True)
                    img_bytes = buf.getvalue()
            except Exception:
                pass

            # Single pass of rembg with shared session + bounded concurrency
            try:
                with _REMBG_SEM:
                    img_bytes = _rembg_remove(img_bytes, session=_get_rembg_session())
            except Exception:
                pass

            # Optional: nudge glibc to return free pages (Linux)
            try:
                import ctypes
                ctypes.CDLL("libc.so.6").malloc_trim(0)
            except Exception:
                pass

        if CACHE_WRITE:
            # Write image + metadata to the local cache, then serve /cached-images/...
            meta = {
                "author": author,
                "licence": licence,
                "licence_url": licence_url,
                "upload_date": upload_date,
                "retrieval_date": retrieval_date,
            }
            try:
                save_image_to_cache(stem, img_bytes)         # write image file
                save_metadata_to_cache(stem, meta)            # write JSON
                enforce_cache_limit()                         # optional: evict if needed
                fname = os.path.basename(get_cached_image_path(stem))
                return (
                    f"/cached-images/{fname}" + ("" if effective_remove else "?variant=raw"),
                    author, licence, licence_url, upload_date, retrieval_date
                )
            except Exception as e:
                # If writing fails for any reason, fall back to read-only behavior
                print(f"[cache write] Failed to save {title_plain} ({width}px): {e}")
                if effective_remove and img_bytes:
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    return (f"data:image/png;base64,{b64}",
                            author, licence, licence_url, upload_date, retrieval_date)
                else:
                    return (raw_thumb_url,
                            author, licence, licence_url, upload_date, retrieval_date)


        # Read-only (no write happened):
        # → Do NOT invent a cached filename on R2. Serve a real URL.
        if effective_remove and img_bytes:
            # background removed in-memory → return data: URL
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            return (f"data:image/png;base64,{b64}", author, licence, licence_url, upload_date, retrieval_date)
        else:
            # no BG removal → serve the real Commons/Wikipedia thumb URL
            return (raw_thumb_url, author, licence, licence_url, upload_date, retrieval_date)

        # Local (no R2): fall back to data: (if bg-removed) or the Commons thumb URL
        if effective_remove and img_bytes:
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            return (f"data:image/png;base64,{b64}", author, licence, licence_url, upload_date, retrieval_date)
        else:
            return (raw_thumb_url, author, licence, licence_url, upload_date, retrieval_date)

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
    try:
        r = requests.get(image_url, headers=headers, timeout=10)
        r.raise_for_status()
        input_data = r.content

        # Only remove if enabled; otherwise just return original as PNG b64
        out = _maybe_remove_bg(input_data) if ENABLE_BG_REMOVAL else input_data
        b64_img = base64.b64encode(out).decode("utf-8")
        return f"data:image/png;base64,{b64_img}"
    except Exception as e:
        print(f"[rembg] Failed to process image: {e}")
        return None






