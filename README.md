# pelagica
aquatic species size visualization 

fetch_data: gets data from sealifebase and fishbase put into data/processed/filtered_combined_species.csv
enrich_with_wiki: edits filtered_combined_species.csv to append flag on wether it has a wikipage
process_data: returns df with rows filtered (online)

sudo apt install llvm llvm-dev
to run rembg

####### DEPLOYMENT ##############

# build with your current defaults (CACHE_WRITE=0)
docker build -t pelagica:ro .

# run it
docker run -d --name pelagica \
  -p 8050:8050 \
  pelagica:ro

# open it
# http://localhost:8050

####### DEVELOPMENT ##############

# build with cache writes enabled (background removal optional)
docker build -t pelagica:dev \
  --build-arg CACHE_WRITE=1 \
  --build-arg ENABLE_BG_REMOVAL=0 .

# run: bind-mount your repo so writes land in ./data/processed and you can edit files
docker run --rm -it --name pelagica-dev \
  -p 8050:8050 \
  -e CACHE_WRITE=1 \
  -v "$PWD":/pelagica \
  pelagica:dev

