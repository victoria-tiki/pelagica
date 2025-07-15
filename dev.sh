#!/bin/bash
sudo docker run -it --rm \
  --network=host \
  -v "$(pwd)":/pelagica \
  -w /pelagica \
  pelagica-dev \
  poetry run python3 app.py

