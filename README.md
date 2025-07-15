# pelagica
aquatic species size visualization 

fetch_data: gets data from sealifebase and fishbase put into data/processed/filtered_combined_species.csv
enrich_with_wiki: edits filtered_combined_species.csv to append flag on wether it has a wikipage
process_data: returns df with rows filtered (online)

sudo apt install llvm llvm-dev
to run rembg

sudo docker run -it --rm \
  --network=host \
  -v "$(pwd)":/pelagica \
  -w /pelagica \
  pelagica-dev \
  poetry run python3 app.py

