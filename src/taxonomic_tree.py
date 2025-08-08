import pandas as pd
import networkx as nx

# ────────────────────────────────────────────────────────────────
# Helper: safe sampling without throwing when len(df) < n
def _safe_head_or_sample(frame: pd.DataFrame, n: int):
    if frame.empty:
        return frame
    if len(frame) <= n:
        return frame
    # use sample for randomness when we have enough rows
    return frame.sample(n=n, random_state=None)

# ────────────────────────────────────────────────────────────────
def _safe_sample(df, n):
    """Sample up to n rows without error if len(df) < n."""
    if df.empty:
        return df
    if len(df) <= n:
        return df
    return df.sample(n=n, random_state=None)

def build_taxonomy_elements(df: pd.DataFrame, target_species: str):
    """
    Build Cytoscape elements for a single species tree view.
    Returns:
        elements :  list[dict]  (Cytoscape nodes + edges)
        root_id  :  str | None  (highest non-missing rank)
    """
    row = df.loc[df["Genus_Species"] == target_species]
    if row.empty:
        return [], None
    row = row.iloc[0]

    RANKS   = ["kingdom", "phylum", "class", "order", "family", "genus"]
    MISSING = "?"
    elements, nodes = [], set()
    root_id = None

    # ───────────────────────── helpers ──────────────────────────
    def add_node(label, *, rank=None, kind=None, subtitle=None):
        if pd.isna(label) or label == "":
            return
        if label not in nodes:
            # ► build a single multi-line label
            if subtitle and pd.notna(subtitle) and subtitle.strip():
                full = f"{label}\n({subtitle.strip()})"
            else:
                full = label

            node = {"data": {"id": label, "label": full}}
            if rank: node["data"]["rank"] = rank
            if kind: node["data"]["kind"] = kind
            elements.append(node)
            nodes.add(label)


    def add_edge(src, tgt):
        if src in nodes and tgt in nodes:
            elements.append({"data": {"source": src, "target": tgt}})

    # ─────────────────────── vertical lineage ───────────────────
    parent = None
    for rank in RANKS:
        raw   = row.get(rank)
        label = raw if pd.notna(raw) and raw else MISSING
        add_node(label, rank=rank, kind="taxon")

        if not root_id and label != MISSING:
            root_id = label
        if parent:
            add_edge(parent, label)
        parent = label

    # ───────────────────────── focal species ────────────────────
    add_node(target_species,
             rank="species",
             kind="focus",
             subtitle=row.get("FBname"))
    add_edge(parent, target_species)

    # ──────────────────── sibling species (same genus) ──────────
    genus = row.get("genus")
    if genus:
        sibs = df[(df["genus"] == genus) &
                  (df["Genus_Species"] != target_species)]
        for _, srow in _safe_sample(sibs, 3).iterrows():
            sid = srow["Genus_Species"]
            add_node(sid, rank="species", kind="example",
                     subtitle=srow.get("FBname"))
            add_edge(genus, sid)

    # ───── 2 other genera in same family (+ one species each) ───
    family = row.get("family")
    if family:
        other_genera = (df[(df["family"] == family) &
                           (df["genus"] != genus)]["genus"]
                        .dropna().unique())[:2]
        for g in other_genera:
            add_node(g, rank="genus")
            add_edge(family, g)

            ex = df[df["genus"] == g].iloc[:1]
            if not ex.empty:
                sid = ex["Genus_Species"].values[0]
                cname = ex["FBname"].values[0] if "FBname" in ex else None
                add_node(sid, rank="species", kind="example",
                         subtitle=cname)
                add_edge(g, sid)

    # ───────────── one extra family in same order (optional) ────
    order = row.get("order")
    if order:
        other_fam = (df[(df["order"] == order) &
                        (df["family"] != family)]["family"]
                     .dropna().unique())[:1]
        for fam in other_fam:
            add_node(fam, rank="family")
            add_edge(order, fam)

    # ── nudge example labels so siblings don’t overlap ──────────
    for i, el in enumerate(elements):
        if el["data"].get("kind") == "example":
            el["position"] = {"x": 0, "y": 25 * (i % 2)}

    return elements, root_id

