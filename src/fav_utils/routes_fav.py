# src/fav_utils/routes_fav.py
import os
from datetime import timedelta
import pandas as pd
from flask import request, jsonify
from .utils_time import utcnow  # adjust import if utils_time is elsewhere

FAV_DIR     = "data/processed"
FAV_EVENTS  = os.path.join(FAV_DIR, "fav_events.csv")
FAV_STATE   = os.path.join(FAV_DIR, "fav_state.csv")

os.makedirs(FAV_DIR, exist_ok=True)

def _append_csv(path, row_dict):
    df = pd.DataFrame([row_dict])
    header = not os.path.exists(path)
    df.to_csv(path, mode="a", index=False, header=header)

def register_fav_routes(app_or_server):
    """
    Accepts either a Dash app or a Flask app.
    Registers POST /fav/toggle in a way that works for both.
    """
    # Resolve to the underlying Flask server
    flask_server = getattr(app_or_server, "server", app_or_server)

    # Avoid double-registration during hot-reload
    endpoint_name = "_pelagica_fav_toggle"
    if endpoint_name in flask_server.view_functions:
        return

    def fav_toggle():
        """
        Body: { sid: str, species: "Genus Species", state: 0|1 }
        - Idempotent: if last_state already equals state → no-op
        - Simple rate-limit: 30s between flips for same (sid, species)
        """
        try:
            j = request.get_json(force=True, silent=False) or {}
        except Exception:
            return jsonify({"ok": False, "err": "bad-json"}), 400

        sid     = j.get("sid")
        species = j.get("species")
        try:
            state = int(j.get("state", 0))
        except Exception:
            state = 0

        if not sid or not species:
            return jsonify({"ok": False, "err": "bad-args"}), 400

        now = utcnow()

        try:
            st = pd.read_csv(FAV_STATE)
        except FileNotFoundError:
            st = pd.DataFrame(columns=["sid","species","last_state","last_ts_utc"])

        mask = (st.sid == sid) & (st.species == species)

        if mask.any():
            try:
                last_state = int(st.loc[mask, "last_state"].iloc[0])
            except Exception:
                last_state = None
            last_ts = pd.to_datetime(
                st.loc[mask, "last_ts_utc"].iloc[0], utc=True, errors="coerce"
            )

            # Idempotent no-op
            if last_state == state:
                return jsonify({"ok": True, "idempotent": True})

            # Lightweight rate limit
            if last_ts is not None and (now - last_ts) < timedelta(seconds=30):
                return jsonify({"ok": False, "err": "too-fast"}), 429

        # Append event (audit/debug)
        _append_csv(
            FAV_EVENTS,
            {"ts_utc": now.isoformat(), "sid": sid, "species": species, "state": state},
        )

        # Upsert current state
        if mask.any():
            st.loc[mask, ["last_state","last_ts_utc"]] = [state, now.isoformat()]
        else:
            st = pd.concat([
                st,
                pd.DataFrame([{
                    "sid": sid, "species": species,
                    "last_state": state, "last_ts_utc": now.isoformat()
                }])
            ], ignore_index=True)

        st.to_csv(FAV_STATE, index=False)
        return jsonify({"ok": True})

    # Register the route on the Flask server
    flask_server.add_url_rule(
        "/fav/toggle", endpoint=endpoint_name, view_func=fav_toggle, methods=["POST"]
    )

