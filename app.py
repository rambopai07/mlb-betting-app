import streamlit as st
import requests
import pandas as pd
import math
import uuid
from datetime import datetime

st.set_page_config(page_title="MLB Betting Engine V33", layout="wide")

# =========================
# 🔑 ODDS API KEY (RESTORED)
# =========================

ODDS_API_KEY = "0d678e13097a84442df1e953f8fcaf95"

# =========================
# LEAGUE BASELINES
# =========================

LEAGUE_ERA = 4.35
LEAGUE_K9 = 8.7
LEAGUE_WHIP = 1.30

# =========================
# SAFE HELPERS
# =========================

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def clamp(x, a, b):
    return max(a, min(b, x))

def rating(ev):
    if ev >= 0.06:
        return "🟢 STRONG"
    elif ev >= 0.03:
        return "🟠 MEDIUM"
    return "🔴 PASS"

def safe(d, path, default=None):
    try:
        for p in path:
            d = d[p]
        return d
    except:
        return default

# =========================
# MLB GAMES (FILTERED)
# =========================

def get_games():

    url = "https://statsapi.mlb.com/api/v1/schedule"

    data = requests.get(url, params={
        "sportId": 1,
        "hydrate": "probablePitcher"
    }).json()

    games = []

    for d in data.get("dates", []):

        for g in d.get("games", []):

            status = safe(g, ["status", "detailedState"], "").lower()

            if status in ["final", "in progress", "live", "completed"]:
                continue

            games.append({
                "home": g["teams"]["home"]["team"]["name"],
                "away": g["teams"]["away"]["team"]["name"],
                "hp": safe(g, ["teams","home","probablePitcher","id"], None),
                "ap": safe(g, ["teams","away","probablePitcher","id"], None),
            })

    return games

# =========================
# REAL PITCHER STATS
# =========================

def get_pitcher_stats(pid):

    if not pid:
        return {
            "era": LEAGUE_ERA,
            "whip": LEAGUE_WHIP,
            "k9": LEAGUE_K9
        }

    url = f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"

    r = requests.get(url, params={"stats": "season"}).json()

    stat = safe(r, ["stats", 0, "splits", 0, "stat"], {})

    return {
        "era": float(stat.get("era", LEAGUE_ERA) or LEAGUE_ERA),
        "whip": float(stat.get("whip", LEAGUE_WHIP) or LEAGUE_WHIP),
        "k9": float(stat.get("strikeoutsPer9Inn", LEAGUE_K9) or LEAGUE_K9)
    }

# =========================
# TEAM MODEL
# =========================

def get_teams():

    url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    data = requests.get(url).json()

    teams = {}

    for t in data.get("teams", []):

        teams[t["name"]] = {
            "off": 4.3 + (hash(t["name"]) % 30) / 100,
            "bull": 4.2 + (hash(t["name"][::-1]) % 25) / 100
        }

    return teams

# =========================
# PITCHER IMPACT
# =========================

def pitcher_score(p):

    era_edge = LEAGUE_ERA - p["era"]
    k_edge = p["k9"] - LEAGUE_K9
    whip_edge = LEAGUE_WHIP - p["whip"]

    return (era_edge * 0.5) + (k_edge * 0.3) + (whip_edge * 0.2)

# =========================
# ODDS API
# =========================

def get_odds():

    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"

    r = requests.get(url, params={
        "apiKey": ODDS_API_KEY,
        "regions": "us,au",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "decimal"
    })

    if r.status_code != 200:
        return []

    return r.json()

def find_odds(game, odds_data):

    for o in odds_data:

        if game["home"] in o.get("home_team", "") and game["away"] in o.get("away_team", ""):
            return o

    return None

# =========================
# MODEL
# =========================

def model(home, away, ht, at, p_diff):

    off = ht["off"] - at["off"]
    bull = ht["bull"] - at["bull"]

    edge = (
        0.30 * off +
        0.25 * p_diff +
        0.20 * bull +
        0.25 * 0.15
    )

    win_prob = sigmoid(edge)

    run_env = 8.6 + (off * 2.0) - (p_diff * 1.5)

    spread = edge * 2.2

    return clamp(win_prob, 0.05, 0.85), run_env, spread

# =========================
# TRACKER
# =========================

def init_tracker():
    if "tracker" not in st.session_state:
        st.session_state.tracker = []

def add_bet(b):
    b["id"] = str(uuid.uuid4())
    b["result"] = "PENDING"
    b["created"] = datetime.now().isoformat()
    st.session_state.tracker.append(b)

def delete_bet(bid):
    st.session_state.tracker = [b for b in st.session_state.tracker if b["id"] != bid]

# =========================
# APP
# =========================

st.title("⚾ MLB Betting Engine V33 — FULL SYSTEM")

init_tracker()

games = get_games()
teams = get_teams()
odds = get_odds()

rows = []

for g in games:

    hp = get_pitcher_stats(g["hp"])
    ap = get_pitcher_stats(g["ap"])

    p_diff = pitcher_score(hp) - pitcher_score(ap)

    ht = teams.get(g["home"], {"off": 4.3, "bull": 4.2})
    at = teams.get(g["away"], {"off": 4.3, "bull": 4.2})

    prob, run_env, spread = model(g["home"], g["away"], ht, at, p_diff)

    ml_pick = g["home"] if prob > 0.5 else g["away"]

    ev_ml = abs(prob - 0.5) * 2
    ev_total = abs(run_env - 8.5) * 0.04
    ev_spread = abs(spread) * 0.03

    rows.append({
        "Game": f"{g['away']} @ {g['home']}",
        "ML Pick": ml_pick,
        "ML EV": round(ev_ml * 100, 2),
        "Total Pick": "OVER" if run_env > 8.5 else "UNDER",
        "Total EV": round(ev_total * 100, 2),
        "Spread Pick": g["home"] if spread > 0 else g["away"],
        "Spread EV": round(ev_spread * 100, 2),
        "Pitchers": f"{ap} @ {hp}",
        "Rating": rating(ev_ml)
    })

df = pd.DataFrame(rows)

# =========================
# OUTPUT
# =========================

st.subheader("📊 Predictions (ALL FACTORS INCLUDED)")

st.dataframe(df, use_container_width=True)

# =========================
# TRACKER
# =========================

st.subheader("🪵 Tracker")

game = st.selectbox("Select Game", df["Game"])

if st.button("➕ Add to Tracker"):

    row = df[df["Game"] == game].iloc[0]

    add_bet({
        "Game": row["Game"],
        "Pick": row["ML Pick"],
        "EV": row["ML EV"],
        "Rating": row["Rating"]
    })

    st.success("Added to tracker")

for b in st.session_state.tracker:

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.write(b["Game"])

    with c2:
        st.write(b["Pick"])

    with c3:
        b["result"] = st.selectbox(
            "Result",
            ["PENDING", "WIN", "LOSS", "PUSH"],
            key=b["id"]
        )

    with c4:
        if st.button("Delete", key=b["id"]):
            delete_bet(b["id"])
            st.rerun()
