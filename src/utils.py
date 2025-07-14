
# src/utils.py
# ------------------------------------------------------------
import numpy as np
import pandas as pd

def assign_random_depth(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    import numpy as np, pandas as pd
    rng  = np.random.default_rng(seed)
    out  = df.copy()

    def _sample(row):
        s = row["DepthRangeComShallow"] if pd.notna(row["DepthRangeComShallow"]) \
            else row["DepthRangeShallow"]
        d = row["DepthRangeComDeep"]     if pd.notna(row["DepthRangeComDeep"])   \
            else row["DepthRangeDeep"]

        # ── 1. missing or identical → just return the shallow value ─────────
        if pd.isna(s) or pd.isna(d) or s == d:
            return s

        # ── 2. genuine range → draw from triangular pdf ─────────────────────
        left, right = sorted([s, d])
        mode = 0.8 * left + 0.2 * right
        return rng.triangular(left, mode, right)

    out["RandDepth"] = out.apply(_sample, axis=1)
    return out

