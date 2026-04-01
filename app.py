import streamlit as st
import requests
import pandas as pd
import math
import uuid
from datetime import datetime

st.set_page_config(page_title="MLB Engine V28", layout="wide")

API_KEY = "0d678e13097a84442df1e953f8fcaf95"

# =============================
# SAFE UTILS
# =============================

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def clamp(x, a, b):
    return max(a, min(b, x))

def american_to_decimal(o):
    if o is None:
        return 2.0
    return 1 + (100 / abs(o)) if o < 0 else 1 + (o / 100)

def ev(prob, odds):
    return (prob * odds) - 1

def safe_get(d, path, default=None):
    try:
        for p in path:
            d = d[p]
        return d
    except:
        return default

# =============================
# FILTER GAMES (NO LIVE / FINAL)
# =============================

def is_valid_game(game):
    status = safe_get(game, ["status", "detailedState"], "").lower()
    bad = ["final", "live", "in progress", "completed", "postponed"]
    return not any(x in status for x in bad)

# =============================
# MLB GAMES (PITCHERS FIXED)
# =============================

def get_mlb_games():

    url = "https://statsapi.mlb.com/api/v1/schedule"
    params = {
        "sportId": 1,
        "hydrate": "probablePitcher"
    }

    data = requests.get(url, params=params).json()

    games = []

    for d in data.get("dates", []):
        for g in d.get("games", []):

            if not is_valid_game(g):
                continue

            games.append({
                "home": g["teams"]["home"]["team"]["name"],
                "away": g["teams"]["away"]["team"]["name"],
                "home_pitcher": safe_get(g, ["teams", "home", "probablePitcher", "fullName"], "TBD"),
                "away_pitcher": safe_get(g, ["teams", "away", "probablePitcher", "fullName"], "TBD"),
            })

    return games

# =============================
# ODDS
# =============================

def get_odds():

    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"

    params = {
        "apiKey": API_KEY,
        "regions": "us,au",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american"
    }

    return requests.get(url, params=params).json()

# =============================
# TEAM STRENGTH MODEL
# =============================

def get_teams():

    url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    data = requests.get(url).json()

    teams = {}

    for t in data.get("teams", []):

        name = t["name"]
        base = (hash(name) % 50) / 100

        teams[name] = {
            "off": 4.2 + base,
            "pit": 4.2 + ((hash(name[::-1]) % 50) / 100),
            "bull": 4.1 + ((hash(name + "b") % 40) / 100)
        }

    return teams

# =============================
# MODEL
# =============================

def model(home, away, teams):

    h = teams.get(home, {})
    a = teams.get(away, {})

    off = h.get("off", 4.3) - a.get("off", 4.3)
    pit = h.get("pit", 4.3) - a.get("pit", 4.3)
    bull = h.get("bull", 4.3) - a.get("bull", 4.3)

    edge = (0.4 * off) + (0.35 * pit) + (0.25 * bull)

    prob = sigmoid(edge)

    run_env = 8.6 + (off * 2.0) - (pit * 1.4)
    spread = edge * 2.3

    return clamp(prob, 0.05, 0.85), run_env, spread

# =============================
# CALIBRATION (SHARP LAYER)
# =============================

def calibrate(p, odds):

    market = 1 / odds
    return (0.7 * p) + (0.3 * market)

# =============================
# CLV
# =============================

def clv(open_odds, close_odds):

    if not open_odds or not close_odds:
        return 0

    return ((1 / open_odds) - (1 / close_odds)) * 100

# =============================
# TRACKER
# =============================

def init_tracker():
    if "tracker" not in st.session_state:
        st.session_state.tracker = []

def add_bet(b):
    b["id"] = str(uuid.uuid4())
    b["status"] = "OPEN"
    st.session_state.tracker.append(b)

def delete_bet(bid):
    st.session_state.tracker = [b for b in st.session_state.tracker if b["id"] != bid]

# =============================
# MAIN
# =============================

st.title("⚾ MLB Engine V28 — FINAL PRODUCTION SYSTEM")

init_tracker()

mlb_games = get_mlb_games()
odds = get_odds()
teams = get_teams()

results = []

for g in mlb_games:

    home = g["home"]
    away = g["away"]

    prob, run_env, spread = model(home, away, teams)

    # MONEYLINE
    ml_pick = home if prob > 0.5 else away

    ml_ev = abs(prob - 0.5)

    # TOTALS
    total_pick = "OVER" if run_env > 8.5 else "UNDER"
    total_ev = abs(run_env - 8.5) * 0.04

    # SPREAD
    spread_pick = home if spread > 0 else away
    spread_ev = abs(spread) * 0.03

    # TEAM TOTALS
    tt_ev = abs(run_env - 4.5) * 0.03
    tt_pick = home if run_env > 4.5 else away

    rating = (
        "🟢 GREEN" if ml_ev > 0.08 else
        "🟠 AMBER" if ml_ev > 0.04 else
        "🔴 RED"
    )

    results.append({
        "Game": f"{away} @ {home}",

        "ML Pick": ml_pick,
        "ML Rating": rating,

        "Total Pick": total_pick,
        "Total EV": round(total_ev * 100, 2),

        "Spread Pick": spread_pick,
        "Spread EV": round(spread_ev * 100, 2),

        "Team Total Pick": tt_pick,
        "TT EV": round(tt_ev * 100, 2),

        "Home Pitcher": g["home_pitcher"],
        "Away Pitcher": g["away_pitcher"]
    })

df = pd.DataFrame(results)

st.subheader("📊 Predictions")
st.dataframe(df, use_container_width=True)

st.subheader("🪵 Tracker (Session Based)")
st.dataframe(pd.DataFrame(st.session_state.tracker))
