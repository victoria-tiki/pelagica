
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
    
    
'''def assign_random_depth(df, seed,
                        surf_thresh    = 150.0,   # controls how quickly surface bias decays
                        k_max          = 20.0,    # concentration for Beta tails
                        zero_clamp     = 200.0,   # max depth when s==0
                        surface_boost  = 10.0,    # extra push for truly surface species
                        deep_threshold = 5000.0,  # threshold for deep‑push
                        deep_boost     = 3.0):    # moderate deep‑push factor
    """
    For each species with (s,d):
      1. If s==0, clamp d = min(d, zero_clamp).
      2. Compute surface‑bias φ_s = exp(-s/surf_thresh).
         If s==0, φ_s *= surface_boost.
      3. Compute deep‑bias   φ_d = 1 - exp(-s/surf_thresh).
         If d > deep_threshold, φ_d *= deep_boost.
      4. Mix weight a = φ_s / (φ_s + φ_d).
      5. Mode m = a*s + (1-a)*d.
      6. Use Beta(α,β) around m with concentration k_max:
         x0 = (m - s)/(d - s)
         α = 1 + k_max * x0
         β = 1 + k_max * (1 - x0)
         u ~ Beta(α,β)
      7. RandDepth = s + u*(d - s)
    """
    import numpy as np, pandas as pd
    from scipy.stats import beta

    rng = np.random.default_rng(seed)
    out = df.copy()

    # bias functions
    def phi_surf(s):  return np.exp(-s / surf_thresh)
    def phi_deep(s):  return 1 - np.exp(-s / surf_thresh)

    # extract and clamp bounds
    def get_bounds(row):
        s = row.get("DepthRangeComShallow", np.nan)
        if pd.isna(s): s = row["DepthRangeShallow"]
        d = row.get("DepthRangeComDeep", np.nan)
        if pd.isna(d): d = row["DepthRangeDeep"]
        s, d = float(s), float(d)
        if s == 0:
            d = min(d, zero_clamp)
        return s, d

    bounds = out.apply(get_bounds, axis=1).tolist()

    depths = []
    for s, d in bounds:
        if np.isnan(s) or np.isnan(d) or s == d:
            depths.append(s)
            continue

        # 1) surface & deep bias
        Bs = phi_surf(s)
        Bd = phi_deep(s)

        # 2) extra surface‐boost for true surface species
        if s == 0:
            Bs *= surface_boost

        # 3) moderate deep‐boost for ultra‐deep species
        if d > deep_threshold:
            Bd *= deep_boost

        # 4) mix
        a = Bs / (Bs + Bd)

        # 5) mode
        m = a*s + (1 - a)*d

        # 6) Beta sampling with fixed concentration
        x0 = (m - s) / (d - s)
        α  = 1 + k_max * x0
        β  = 1 + k_max * (1 - x0)
        u  = rng.beta(α, β)

        # 7) scale back to [s, d]
        depths.append(s + u * (d - s))

    out["RandDepth"] = depths
    return out'''
    
    


# Species that always get override depth 0–5 m
OVERRIDE_DEPTH = {
    "Delphinus delphis",
    "Homo sapiens",
    "Mirounga leonina", 
    "Lobodon carcinophaga",
    "Stenella coeruleoalba",
    "Odobenus rosmarus",
    "Stenella frontalis", 
    "Pagophilus groenlandicus", 
    "Stenella longirostris", 
    "Stenella attenuata", 
    "Grampus griseus", 
    "Tursiops truncatus"
}

def assign_random_depth(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = df.copy()

    def get_bounds(row):
        s = row.get("DepthRangeComShallow", np.nan)
        if pd.isna(s): s = row.get("DepthRangeShallow", np.nan)
        d = row.get("DepthRangeComDeep", np.nan)
        if pd.isna(d): d = row.get("DepthRangeDeep", np.nan)
        return float(s), float(d)

    def biased_depth(s, d, bias):
        if np.isnan(s) or np.isnan(d) or s == d:
            return s
        u = rng.random()
        if bias == "shallow":
            return s + (u ** 1.3) * (d - s)
        elif bias == "medium":
            return s + u * (d - s)
        elif bias == "deep":
            return s + (1 - (1 - u) ** 2.0) * (d - s)
        else:
            return s + u * (d - s)

    depths = []
    for i, row in out.iterrows():
        gs = row["Genus_Species"]
        if gs in OVERRIDE_DEPTH:
            s, d = 0.0, 5.0
        else:
            s, d = get_bounds(row)

        if s < 200:
            bias = "shallow"
        elif s < 2000:
            bias = "medium"
        else:
            bias = "deep"

        depths.append(biased_depth(s, d, bias))

    out["RandDepth"] = depths
    return out


