import streamlit as st
import requests
import pandas as pd
import math
import uuid
from datetime import datetime, timedelta

st.set_page_config(page_title="MLB Betting Engine V35", layout="wide")

# =========================
# 🔑 API KEY
# =========================
ODDS_API_KEY = "0d678e13097a84442df1e953f8fcaf95"

# =========================
# CONSTANTS
# =========================
LEAGUE_ERA = 4.35
LEAGUE_K9 = 8.7
LEAGUE_WHIP = 1.30

# =========================
# HELPERS
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
# 🌍 TIMEZONE FIX
# =========================
def get_us_date():
    now_utc = datetime.utcnow()
    adjusted = now_utc - timedelta(hours=6)
    return adjusted.strftime("%Y-%m-%d")

# =========================
# GAMES
# =========================
def get_games():

    url = "https://statsapi.mlb.com/api/v1/schedule"

    data = requests.get(url, params={
        "sportId": 1,
        "date": get_us_date(),
        "hydrate": "probablePitcher"
    }).json()

    games = []

    for d in data.get("dates", []):
        for g in d.get("games", []):

            status = safe(g, ["status","detailedState"], "").lower()

            if status in ["final","in progress","live","completed"]:
                continue

            games.append({
                "home": g["teams"]["home"]["team"]["name"],
                "away": g["teams"]["away"]["team"]["name"],
                "home_pitcher_id": safe(g, ["teams","home","probablePitcher","id"]),
                "away_pitcher_id": safe(g, ["teams","away","probablePitcher","id"]),
                "home_pitcher_name": safe(g, ["teams","home","probablePitcher","fullName"], "TBD"),
                "away_pitcher_name": safe(g, ["teams","away","probablePitcher","fullName"], "TBD"),
            })

    return games

# =========================
# PITCHER STATS
# =========================
def get_pitcher_stats(pid):

    if not pid:
        return {"era":LEAGUE_ERA,"whip":LEAGUE_WHIP,"k9":LEAGUE_K9}

    r = requests.get(
        f"https://statsapi.mlb.com/api/v1/people/{pid}/stats",
        params={"stats":"season"}
    ).json()

    stat = safe(r, ["stats",0,"splits",0,"stat"], {})

    return {
        "era": float(stat.get("era", LEAGUE_ERA) or LEAGUE_ERA),
        "whip": float(stat.get("whip", LEAGUE_WHIP) or LEAGUE_WHIP),
        "k9": float(stat.get("strikeoutsPer9Inn", LEAGUE_K9) or LEAGUE_K9)
    }

def pitcher_score(p):
    return (
        (LEAGUE_ERA - p["era"]) * 0.5 +
        (p["k9"] - LEAGUE_K9) * 0.3 +
        (LEAGUE_WHIP - p["whip"]) * 0.2
    )

# =========================
# TEAM BASE
# =========================
def get_teams():
    data = requests.get("https://statsapi.mlb.com/api/v1/teams?sportId=1").json()

    teams = {}
    for t in data.get("teams", []):
        teams[t["name"]] = {
            "off": 4.3 + (hash(t["name"]) % 30)/100,
            "bull": 4.2 + (hash(t["name"][::-1]) % 25)/100
        }
    return teams

# =========================
# ODDS
# =========================
def get_odds():
    r = requests.get(
        "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/",
        params={
            "apiKey": ODDS_API_KEY,
            "regions": "us,au",
            "markets": "h2h,totals,spreads",
            "oddsFormat": "decimal"
        }
    )
    if r.status_code != 200:
        return []
    return r.json()

def match_odds(game, odds):
    for o in odds:
        if game["home"] in o.get("home_team","") and game["away"] in o.get("away_team",""):
            return o
    return None

# =========================
# MODEL
# =========================
def model(home, away, ht, at, p_diff):

    off_diff = ht["off"] - at["off"]
    bull_diff = ht["bull"] - at["bull"]

    edge = (0.30*off_diff + 0.25*p_diff + 0.20*bull_diff + 0.25*0.15)

    win_prob = sigmoid(edge)

    total_runs = 8.6 + (off_diff*2.0) - (p_diff*1.5)

    # 🔥 TEAM TOTAL SPLIT
    home_runs = (total_runs/2) + (edge*1.1)
    away_runs = total_runs - home_runs

    spread = edge * 2.2

    return clamp(win_prob,0.05,0.85), total_runs, spread, home_runs, away_runs

def implied_prob(o):
    return 1/o if o else 0

def calc_ev(p, odds):
    return p - implied_prob(odds) if odds else 0

# =========================
# TRACKER
# =========================
def init_tracker():
    if "tracker" not in st.session_state:
        st.session_state.tracker = []

def add_bet(b):
    b["id"] = str(uuid.uuid4())
    b["result"] = "PENDING"
    st.session_state.tracker.append(b)

def delete_bet(bid):
    st.session_state.tracker = [b for b in st.session_state.tracker if b["id"] != bid]

# =========================
# APP
# =========================

st.title("⚾ MLB Betting Engine V35 — FULL SYSTEM")

init_tracker()

games = get_games()
teams = get_teams()
odds = get_odds()

rows = []

for g in games:

    hp_stats = get_pitcher_stats(g["home_pitcher_id"])
    ap_stats = get_pitcher_stats(g["away_pitcher_id"])

    p_diff = pitcher_score(hp_stats) - pitcher_score(ap_stats)

    ht = teams.get(g["home"], {"off":4.3,"bull":4.2})
    at = teams.get(g["away"], {"off":4.3,"bull":4.2})

    prob, total_runs, spread, home_runs, away_runs = model(
        g["home"], g["away"], ht, at, p_diff
    )

    ml_pick = g["home"] if prob > 0.5 else g["away"]

    # EV (basic)
    ev_ml = abs(prob - 0.5)*2
    ev_total = abs(total_runs - 8.5)*0.04
    ev_spread = abs(spread)*0.03
    ev_home_tt = abs(home_runs - 4.5)*0.03
    ev_away_tt = abs(away_runs - 4.5)*0.03

    rows.append({
        "Game": f"{g['away']} @ {g['home']}",
        "Pitchers": f"{g['away_pitcher_name']} vs {g['home_pitcher_name']}",

        "ML Pick": ml_pick,
        "ML EV %": round(ev_ml*100,2),

        "Total Pick": "OVER" if total_runs > 8.5 else "UNDER",
        "Total EV %": round(ev_total*100,2),

        "Spread Pick": g["home"] if spread > 0 else g["away"],
        "Spread EV %": round(ev_spread*100,2),

        "Home TT": round(home_runs,2),
        "Home TT EV %": round(ev_home_tt*100,2),

        "Away TT": round(away_runs,2),
        "Away TT EV %": round(ev_away_tt*100,2),

        "Rating": rating(ev_ml)
    })

df = pd.DataFrame(rows)

# =========================
# OUTPUT
# =========================

st.subheader("📊 Betting Board")

if df.empty:
    st.warning("No games available")
else:
    st.dataframe(df, use_container_width=True)

# =========================
# TRACKER
# =========================

st.subheader("🪵 Tracker")

if not df.empty:

    game = st.selectbox("Select Game", df["Game"])

    if st.button("➕ Add Bet"):
        row = df[df["Game"] == game].iloc[0]
        add_bet(row.to_dict())
        st.success("Added")

for b in st.session_state.tracker:

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.write(b["Game"])

    with c2:
        st.write(b["ML Pick"])

    with c3:
        b["result"] = st.selectbox(
            "Result",
            ["PENDING","WIN","LOSS","PUSH"],
            key=b["id"]
        )

    with c4:
        if st.button("Delete", key=b["id"]):
            delete_bet(b["id"])
            st.rerun()
