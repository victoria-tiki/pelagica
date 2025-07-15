import os, json, hashlib, time
from PIL import Image
from io import BytesIO

CACHE_DIR = "./image_cache"
MAX_CACHE_SIZE_GB = 2

os.makedirs(CACHE_DIR, exist_ok=True)

def url_to_stem(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def get_cached_image_path(stem: str) -> str:
    return os.path.join(CACHE_DIR, f"{stem}.webp")

def get_cached_metadata_path(stem: str) -> str:
    return os.path.join(CACHE_DIR, f"{stem}.json")

def save_image_to_cache(stem: str, img_data: bytes):
    img = Image.open(BytesIO(img_data)).convert("RGBA")
    img.save(get_cached_image_path(stem), "WEBP", quality=85)

def save_metadata_to_cache(stem: str, metadata: dict):
    with open(get_cached_metadata_path(stem), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

def load_cached_image_and_meta(url: str) -> tuple[str | None, dict | None]:
    stem = url_to_stem(url)
    image_path = get_cached_image_path(stem)
    meta_path  = get_cached_metadata_path(stem)

    if os.path.exists(image_path) and os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            return image_path, json.load(f)
    return None, None

def enforce_cache_limit():
    max_bytes = MAX_CACHE_SIZE_GB * 1024**3
    total = sum(f.stat().st_size for f in os.scandir(CACHE_DIR) if f.is_file())
    while total > max_bytes:
        files = [(f.path, f.stat().st_mtime) for f in os.scandir(CACHE_DIR)]
        oldest = min(files, key=lambda x: x[1])[0]
        os.remove(oldest)
        total = sum(f.stat().st_size for f in os.scandir(CACHE_DIR) if f.is_file())

