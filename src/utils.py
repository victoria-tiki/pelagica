
# src/utils.py
# ------------------------------------------------------------
import numpy as np
import pandas as pd
from scipy.stats import beta

'''def assign_random_depth(df: pd.DataFrame, seed: int) -> pd.DataFrame: #triangular probability distribution
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
    return out'''


'''def assign_random_depth(df: pd.DataFrame, seed: int,
                        e_shallow: float = 2.0,
                        e_deep:    float = 0.2) -> pd.DataFrame:

    
    # For each species with depth bounds [s,d], compute r = (d−s)/max_width.
# Interpolate exponent e = (1−r)*e_shallow + r*e_deep (e_shallow>1 biases toward s, e_deep<1 biases toward d).
# Draw u ∼ Uniform(0,1) and set depth = s + (u**e)*(d−s), giving a smooth transition from shallow‐biased to deep‐biased sampling.

    rng = np.random.default_rng(seed)
    out = df.copy()

    # 1) extract shallow/deep for every row
    def get_bounds(row):
        s = row["DepthRangeComShallow"] if pd.notna(row["DepthRangeComShallow"]) \
            else row["DepthRangeShallow"]
        d = row["DepthRangeComDeep"]   if pd.notna(row["DepthRangeComDeep"])   \
            else row["DepthRangeDeep"]
        return s, d

    bounds = out.apply(get_bounds, axis=1).tolist()
    widths = np.array([d - s for s, d in bounds], dtype=float)
    max_width = widths.max() if len(widths) > 0 else 0.0

    # 2) sampling fn that picks exponent by normalized width
    def _sample(s: float, d: float) -> float:
        if pd.isna(s) or pd.isna(d) or s == d or max_width == 0.0:
            return s  # fallback
        r = (d - s) / max_width
        e = (1 - r) * e_shallow + r * e_deep
        u = rng.random()
        return s + (u ** e) * (d - s)

    # 3) build new column
    out["RandDepth"] = [
        _sample(s, d)
        for s, d in bounds
    ]
    return out'''
    
    
import numpy as np, pandas as pd
from scipy.stats import beta

'''def assign_random_depth(df, seed,
                        small_thresh=200,   # “small” range if w < small_thresh
                        surf_thresh=150,    # “surface” if s < surf_thresh
                        k_min=2.0,          # flattest Beta
                        k_max=20.0):        # tightest Beta
    """
    For each row with [s,d]:
      - compute w = d-s
      - B_small = φ_small(w)   high when w small
      - B_surf  = φ_surf(s)    high when s small
      - B_shallow = B_small + B_surf
      - B_range = φ_large(w)   high when w large
      - B_deep  = B_range + φ_deep(s)  high when s > surf_thresh
      - a = B_shallow / (B_shallow + B_deep)
      - mode m = a*s + (1-a)*d
      - k = k_min + (1 - w/w_max) * (k_max - k_min)
      - α = 1 + k*(m-s)/(d-s)
      - β = 1 + k*(d-m)/(d-s)
      - draw u ~ Beta(α,β)
      - RandDepth = s + u*(d-s)
    """
    rng = np.random.default_rng(seed)
    out = df.copy()

    # helper “soft steps”
    def phi_small(w):
        # ≈1 for w<<small_thresh, ≈0 for w>>small_thresh
        return np.exp(-w / small_thresh)

    def phi_large(w):
        # ≈1 for w>>small_thresh, ≈0 for w<<small_thresh
        return 1 - np.exp(-w / small_thresh)

    def phi_surf(s):
        # ≈1 for s<<surf_thresh, ≈0 for s>>surf_thresh
        return np.exp(-s / surf_thresh)

    def phi_deep(s):
        # ≈1 for s>>surf_thresh, ≈0 for s<<surf_thresh
        return 1 - np.exp(-s / surf_thresh)

    # get s, d for every row
    def bounds(row):
        s = row["DepthRangeComShallow"] \
            if pd.notna(row["DepthRangeComShallow"]) \
            else row["DepthRangeShallow"]
        d = row["DepthRangeComDeep"] \
            if pd.notna(row["DepthRangeComDeep"]) \
            else row["DepthRangeDeep"]
        return float(s), float(d)

    bnds = out.apply(bounds, axis=1).tolist()
    widths = np.array([d-s for s, d in bnds])
    w_max  = widths.max() if len(widths) else 0.0

    depths = []
    for s, d in bnds:
        if np.isnan(s) or np.isnan(d) or s == d or w_max == 0:
            depths.append(s)
            continue

        w = d - s

        # build shallow/deep bias terms
        B_small   = phi_small(w)
        B_surf    = phi_surf(s)
        B_shallow = B_small + B_surf

        B_range = phi_large(w)
        B_deep  = B_range + phi_deep(s)

        a = B_shallow / (B_shallow + B_deep)

        # mode and concentration
        m = a*s + (1 - a)*d
        k = k_min + (1 - w/w_max)*(k_max - k_min)

        x0 = (m - s) / (d - s)
        α  = 1 + k * x0
        β  = 1 + k * (1 - x0)

        u = rng.beta(α, β)
        depths.append(s + u * (d - s))

    out["RandDepth"] = depths
    return out'''
    
    
def assign_random_depth(df, seed,
                        small_thresh=200,   # “small” range if w < small_thresh
                        surf_thresh=150,    # “surface” if s < surf_thresh
                        k_min=2.0,          # flattest Beta
                        k_max=20.0,         # tightest Beta
                        zero_boost=5.0):    # extra surface‑bias when s == 0
    """
    ...
      - same as before, plus:
      - if s == 0 or ComShallow == 0, B_surf is multiplied by zero_boost,
        making the final a = B_shallow/(B_shallow+B_deep) ≈ 1 → extreme shallow bias.
    """
    import numpy as np, pandas as pd
    from scipy.stats import beta

    rng = np.random.default_rng(seed)
    out = df.copy()

    def phi_small(w): return np.exp(-w / small_thresh)
    def phi_large(w): return 1 - np.exp(-w / small_thresh)
    def phi_surf(s):  return np.exp(-s / surf_thresh)
    def phi_deep(s):  return 1 - np.exp(-s / surf_thresh)

    # extract bounds
    def bounds(row):
        s = row["DepthRangeComShallow"] if pd.notna(row["DepthRangeComShallow"]) \
            else row["DepthRangeShallow"]
        d = row["DepthRangeComDeep"]   if pd.notna(row["DepthRangeComDeep"])   \
            else row["DepthRangeDeep"]
        return float(s), float(d)

    bnds   = out.apply(bounds, axis=1).tolist()
    widths = np.array([d-s for s, d in bnds], dtype=float)
    w_max  = widths.max() if len(widths) else 0.0

    depths = []
    for s, d in bnds:
        if np.isnan(s) or np.isnan(d) or s == d or w_max == 0:
            depths.append(s)
            continue

        w = d - s

        # shallow/deep bias building
        B_small = phi_small(w)
        B_surf  = phi_surf(s)
        # BOOST the surface bias if the shallow bound is zero
        if s == 0:
            B_surf *= zero_boost

        B_shallow = B_small + B_surf

        B_range = phi_large(w)
        B_deep  = B_range + phi_deep(s)

        # mix ratio
        a = B_shallow / (B_shallow + B_deep)

        # mode m and concentration k
        m = a*s + (1 - a)*d
        k = k_min + (1 - w/w_max)*(k_max - k_min)

        x0 = (m - s) / (d - s)
        α  = 1 + k * x0
        β  = 1 + k * (1 - x0)

        u = rng.beta(α, β)
        depths.append(s + u * (d - s))

    out["RandDepth"] = depths
    return out


