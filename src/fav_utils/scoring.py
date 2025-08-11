# scoring.py
import os, pandas as pd
from src.fav_utils.utils_time import prev_full_hour_window, prev_mon_sun_week, last_60m_window
from datetime import timezone

DATA_DIR   = "data/processed"
FAV_EVENTS = os.path.join(DATA_DIR, "fav_events.csv")
WINNERS    = os.path.join(DATA_DIR, "weekly_winners.csv")

def _load_df(path, cols):
    try: return pd.read_csv(path, usecols=cols)
    except FileNotFoundError: return pd.DataFrame(columns=cols)

def _suppression_multiplier(species, winners_df, week_start_utc, m0=0.6, horizon=8):
    if winners_df.empty: return 1.0
    w = winners_df[winners_df["species"] == species]
    if w.empty: return 1.0
    w["week_start_utc"] = pd.to_datetime(w["week_start_utc"], utc=True)
    past = w[w["week_start_utc"] <= week_start_utc]
    if past.empty: return 1.0
    last = past["week_start_utc"].max()
    n_weeks = int((week_start_utc - last).days // 7)
    if n_weeks >= horizon: return 1.0
    return m0 + (1 - m0) * (n_weeks / horizon)

def top_species(*, debug=False, option="ever_favved", m0=0.6, horizon=8):
    """
    Return (winner_species_or_None, scores_series).
    Tie-breaker: highest score → FEWEST past wins in winners.csv → alphabetical.
    """
    events  = _load_df(FAV_EVENTS, ["ts_utc","sid","species","state"])
    winners = _load_df(WINNERS,    ["week_start_utc","species"])

    if debug:
        # kept for completeness; production uses prev_mon_sun_week()
        start, end = prev_full_hour_window()
        week_start = start.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    else:
        start, end = prev_mon_sun_week()
        week_start = start

    if events.empty:
        return None, pd.Series(dtype=float)

    events["ts_utc"] = pd.to_datetime(events["ts_utc"], utc=True)
    win = events[(events["ts_utc"] >= start) & (events["ts_utc"] < end)]
    if win.empty:
        return None, pd.Series(dtype=float)

    if option == "final_state":
        f = (win.sort_values("ts_utc")
                .groupby(["sid","species"], as_index=False)
                .tail(1))
        base = f[f["state"] == 1].groupby("species")["sid"].nunique()
    else:
        base = win[win["state"] == 1].groupby("species")["sid"].nunique()

    if base.empty:
        return None, pd.Series(dtype=float)

    # scores with suppression
    winners_counts = winners["species"].value_counts() if not winners.empty else pd.Series(dtype=int)
    rows = []
    for sp, cnt in base.items():
        mult = _suppression_multiplier(sp, winners, week_start, m0=m0, horizon=horizon)
        score = cnt * mult
        past_wins = int(winners_counts.get(sp, 0))
        rows.append((sp, score, past_wins))

    df = pd.DataFrame(rows, columns=["species","score","past_wins"])
    df.sort_values(by=["score","past_wins","species"], ascending=[False, True, True], inplace=True)
    winner = None if df.empty else df.iloc[0]["species"]

    # return a Series sorted with the same deterministic order
    ordered = df.set_index("species")["score"]
    return winner, ordered

def record_weekly_winner_if_missing():
    # unchanged logic
    winner, _ = top_species(debug=False)
    if not winner:
        return False
    start, _ = prev_mon_sun_week()
    try:
        w = pd.read_csv(WINNERS)
    except FileNotFoundError:
        w = pd.DataFrame(columns=["week_start_utc","species"])
    key = pd.to_datetime(start, utc=True).isoformat()
    if (w["week_start_utc"] == key).any():
        return False
    w = pd.concat([w, pd.DataFrame([{"week_start_utc": key, "species": winner}])], ignore_index=True)
    w.to_csv(WINNERS, index=False)
    return True

