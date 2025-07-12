# Python-side R package setup
import rpy2.robjects.packages as rpackages
from rpy2.robjects.vectors import StrVector

utils = rpackages.importr('utils')
utils.chooseCRANmirror(ind=1)

packages = ['rfishbase', 'dplyr', 'readr', 'purrr', 'tibble']
to_install = [pkg for pkg in packages if not rpackages.isinstalled(pkg)]

if to_install:
    utils.install_packages(StrVector(to_install))

import rpy2.robjects as robjects

r_code = r"""
# R script: fetch_species_tables.R
library(rfishbase)
library(dplyr)
library(readr)     # write_csv()

# ---- pick exactly the columns we care about ----
target_fields <- c(
  "SpecCode", "Genus", "Species", "FBname",
  "DepthRangeShallow", "DepthRangeDeep",
  "DepthRangeComShallow", "DepthRangeComDeep",
  "Fresh", "Brack", "Saltwater", "DemersPelag",
  "Vulnerability", "Length", "LTypeMaxM",
  "CommonLength", "LTypeComM", "LongevityWild",
  "Dangerous", "Electrogenic", "Comments"
)

get_one <- function(db) {
  message("📥  pulling `species` table from ", db)
  fb_tbl("species", server = db) |>
    select(any_of(target_fields)) |>
    filter(                       # lightweight quality gates
      !is.na(Genus) & !is.na(Species),
      rowSums(across(
        c(Length, CommonLength,
          DepthRangeShallow, DepthRangeDeep,
          DepthRangeComShallow, DepthRangeComDeep),
        ~ !is.na(.))) > 0
    ) |>
    mutate(Database = db)         # keep track of provenance
}

combined <- bind_rows(
  get_one("fishbase"),
  get_one("sealifebase")
)

dir.create("data/processed", recursive = TRUE, showWarnings = FALSE)
write_csv(combined, "data/processed/filtered_combined_species.csv")
message("✅ Saved ", nrow(combined), " rows to data/processed/filtered_combined_species.csv")

"""


robjects.r(r_code)

