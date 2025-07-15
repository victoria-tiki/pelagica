import os, hashlib, json, time

TEXT_CACHE_DIR = "./text_cache"
MAX_TEXT_CACHE_SIZE_MB = 500
os.makedirs(TEXT_CACHE_DIR, exist_ok=True)

def key_to_filename(key: str) -> str:
    return os.path.join(TEXT_CACHE_DIR, hashlib.md5(key.encode()).hexdigest() + ".json")

def load_cached_blurb(key: str) -> dict | None:
    path = key_to_filename(key)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_cached_blurb(key: str, data: dict):
    path = key_to_filename(key)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    enforce_text_cache_limit()

def enforce_text_cache_limit():
    max_bytes = MAX_TEXT_CACHE_SIZE_MB * 1024**2
    files = [(f.path, f.stat().st_mtime, f.stat().st_size)
             for f in os.scandir(TEXT_CACHE_DIR) if f.is_file()]
    total = sum(f[2] for f in files)
    if total <= max_bytes:
        return
    for path, _, _ in sorted(files, key=lambda x: x[1]):
        os.remove(path)
        total -= os.path.getsize(path)
        if total <= max_bytes:
            break

