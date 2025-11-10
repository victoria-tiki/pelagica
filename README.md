# Pelagica – The Aquatic Life Atlas

Pelagica is an interactive web atlas of marine and aquatic life. It combines curated species data, occurrence records, imagery, and sound to visualize where organisms live in the water column and how they relate in depth, scale, and taxonomy.

---

## Project Structure

- `about/` 
  Static HTML describing the project and usage.

- `data/` 
  Data used by the app, including:
  - base datasets from FishBase / SeaLifeBase
  - curated species lists and “favourited” species
  - taxonomy tables and helper files

- `image_cache/`, `text_cache/` 
  Local caches for species images and text fragments 
  (mirrored to R2 in production).

- `depth_viewer/` 
  Depth visualization frontend:
  - `depthanimation.js` drives vertical depth animations
  - tile assets and configuration for the water-column scene.

- `src/` 
  Data and content pipeline utilities, e.g.:
  - `fetch_data`: fetch combined species data from SeaLifeBase / FishBase into `data/processed/filtered_combined_species.csv`
  - `enrich_with_wiki`: flag rows with an associated Wikipedia page
  - `process_data`: filter and prepare records for use in the app, producing the final processed dataset
  - helpers for querying GBIF, caching responses, and other preprocessing.

- `assets/` 
  Shared static assets:
  - ambient sound and UI audio
  - scale comparison images and icons
  - CSS and bridge assets between the app UI and the depth animation.

- `app.py` 
  Application entry point.

- `Dockerfile`, `fly.toml` 
  Container and Fly.io configuration.


---

## Requirements

For optional background removal (via rembg), install:

    sudo apt install llvm llvm-dev

Install Python dependencies:

    poetry install

Run locally:

    poetry run python app.py
    # open http://localhost:8050

## Deployment

Build a read-only image using existing cached data:

    docker build -t pelagica:ro .

Run:

    docker run -d --name pelagica \
      -p 8050:8050 \
      pelagica:ro

Then open:

    http://localhost:8050

(For production on Fly.io, adapt this image using fly.toml.)

## Development

Build with cache writes enabled:

    docker build -t pelagica:dev \
      --build-arg CACHE_WRITE=1 \
      --build-arg ENABLE_BG_REMOVAL=0 .

Run with a bind-mount so new cache and processed files are written into your local checkout:

    docker run --rm -it --name pelagica-dev \
      -p 8050:8050 \
      -e CACHE_WRITE=1 \
      -v "$PWD":/pelagica \
      pelagica:dev

Then open:

    http://localhost:8050
