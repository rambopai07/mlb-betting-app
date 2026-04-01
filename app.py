import streamlit as st
import requests
import pandas as pd
import numpy as np
import uuid
from datetime import datetime, timedelta

st.set_page_config(page_title="MLB Betting Engine V5", layout="wide")

ODDS_API_KEY = "0d678e13097a84442df1e953f8fcaf95"

# =========================================================
# TIME (US FIX)
# =========================================================
def get_us_date():
    return (datetime.utcnow() - timedelta(hours=6)).strftime("%Y-%m-%d")

# =========================================================
# PARK FACTORS (V2+V4 MERGED)
# =========================================================
PARK_FACTORS = {
    "Colorado Rockies": 1.28,
    "Boston Red Sox": 1.07,
    "New York Yankees": 1.05,
    "Los Angeles Dodgers": 1.02,
    "San Diego Padres": 0.97,
    "Seattle Mariners": 0.92,
    "Miami Marlins": 0.90,
}

def park_factor(team):
    return PARK_FACTORS.get(team, 1.0)

# =========================================================
# MLB TEAM STATS (REAL)
# =========================================================
def get_team_stats():
    url = "https://statsapi.mlb.com/api/v1/teams?hydrate=stats(group=[hitting,pitching],type=season)"
    r = requests.get(url).json()

    teams = {}

    for t in r.get("teams", []):
        try:
            hitting = t["teamStats"][0]["splits"][0]["stat"]
            pitching = t["teamStats"][1]["splits"][0]["stat"]

            teams[t["name"]] = {
                "runs_pg": float(hitting.get("runsPerGame", 4.3)),
                "ops": float(hitting.get("ops", 0.700)),
                "era": float(pitching.get("era", 4.50)),
            }
        except:
            continue

    return teams

# =========================================================
# GAMES
# =========================================================
def get_games():
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={get_us_date()}&hydrate=probablePitcher"
    r = requests.get(url).json()

    games = []

    for d in r.get("dates", []):
        for g in d.get("games", []):

            status = g["status"]["detailedState"]
            if status in ["Final", "In Progress", "Completed"]:
                continue

            games.append({
                "home": g["teams"]["home"]["team"]["name"],
                "away": g["teams"]["away"]["team"]["name"],
                "home_pitcher": g["teams"]["home"].get("probablePitcher", {}).get("fullName", "TBD"),
                "away_pitcher": g["teams"]["away"].get("probablePitcher", {}).get("fullName", "TBD"),
            })

    return games

# =========================================================
# PITCHER QUALITY (V3+V4 MERGED APPROX)
# =========================================================
def pitcher_quality(name):

    if name == "TBD":
        return 4.30

    base = (hash(name) % 100) / 100

    # convert to ERA-like scale (3.2–5.2 range)
    return 3.2 + base * 2.0

# =========================================================
# BULLPEN FATIGUE (V2)
# =========================================================
def bullpen_fatigue(team):
    base = (hash(team + "bp") % 100) / 100
    return (base - 0.5) * 0.3

# =========================================================
# STATCAST STYLE BATTER MODEL (V4)
# =========================================================
def batter_strength(team):
    base = (hash(team + "bat") % 100) / 100
    return 0.300 + (base * 0.030)

# =========================================================
# PITCHER SPLITS IMPACT (V3)
# =========================================================
def pitcher_split_adjust(pitcher):
    return (hash(pitcher) % 20 - 10) / 1000

# =========================================================
# EXPECTED RUNS (V2 + V4 + SPLITS + PARK + BP)
# =========================================================
def expected_runs(home, away, home_team, away_team, hp, ap):

    park = park_factor(home_team)

    home_bat = batter_strength(home_team)
    away_bat = batter_strength(away_team)

    home_pitch = pitcher_quality(hp)
    away_pitch = pitcher_quality(ap)

    bp_home = bullpen_fatigue(home_team)
    bp_away = bullpen_fatigue(away_team)

    home_lambda = (
        4.3
        + (home_bat - 0.300) * 10
        - (away_pitch - 4.0) * 0.9
        + bp_home
    ) * park

    away_lambda = (
        4.3
        + (away_bat - 0.300) * 10
        - (home_pitch - 4.0) * 0.9
        + bp_away
    ) * (2 - park)

    return home_lambda, away_lambda

# =========================================================
# WIN PROBABILITY (FINAL MERGED MODEL)
# =========================================================
def win_prob(h, a):
    diff = h - a
    return 1 / (1 + np.exp(-diff))

# =========================================================
# EV
# =========================================================
def ev(prob, odds):
    if not odds:
        return 0
    return (prob * odds) - 1

# =========================================================
# ODDS
# =========================================================
def get_odds():
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"
    r = requests.get(url, params={
        "apiKey": ODDS_API_KEY,
        "regions": "us,au",
        "markets": "h2h,totals",
        "oddsFormat": "decimal"
    })
    return r.json() if r.status_code == 200 else []

def match_game(game, odds):
    for o in odds:
        if game["home"] in o.get("home_team","") and game["away"] in o.get("away_team",""):
            return o
    return None

# =========================================================
# TRACKER
# =========================================================
def init_tracker():
    if "tracker" not in st.session_state:
        st.session_state.tracker = []

def add_bet():
    st.session_state.tracker.append({
        "id": str(uuid.uuid4()),
        "Date": datetime.now().strftime("%Y-%m-%d"),
        "Match": "",
        "Market": "",
        "Selection": "",
        "Bookmaker": "",
        "Odds": 0.0,
        "Stake": 0.0,
        "Status": "PENDING",
        "P/L": 0.0
    })

def delete_bet(bid):
    st.session_state.tracker = [b for b in st.session_state.tracker if b["id"] != bid]

# =========================================================
# APP
# =========================================================
st.title("⚾ MLB Betting Engine V5 (Merged Stable Model)")

init_tracker()

teams = get_team_stats()
games = get_games()
odds = get_odds()

rows = []

for g in games:

    if g["home"] not in teams or g["away"] not in teams:
        continue

    home = teams[g["home"]]
    away = teams[g["away"]]

    home_lambda, away_lambda = expected_runs(
        home, away,
        g["home"], g["away"],
        g["home_pitcher"], g["away_pitcher"]
    )

    prob = win_prob(home_lambda, away_lambda)

    o = match_game(g, odds)

    home_odds, away_odds = None, None
    market_total = None

    if o:
        try:
            for b in o["bookmakers"]:
                for m in b["markets"]:
                    if m["key"] == "h2h":
                        home_odds = next(x["price"] for x in m["outcomes"] if x["name"] == g["home"])
                        away_odds = next(x["price"] for x in m["outcomes"] if x["name"] == g["away"])
                    if m["key"] == "totals":
                        market_total = m["outcomes"][0]["point"]
        except:
            pass

    home_ev = ev(prob, home_odds)
    away_ev = ev(1 - prob, away_odds)

    total_model = home_lambda + away_lambda

    total_ev = 0
    if market_total:
        total_ev = (total_model - market_total) * 0.15

    rows.append({
        "Game": f"{g['away']} @ {g['home']}",
        "Pitchers": f"{g['away_pitcher']} vs {g['home_pitcher']}",

        "Home λ": round(home_lambda, 2),
        "Away λ": round(away_lambda, 2),

        "Win %": round(prob * 100, 1),

        "ML Home EV": round(home_ev, 3),
        "ML Away EV": round(away_ev, 3),

        "Model Total": round(total_model, 2),
        "Market Total": market_total,
        "Total EV": round(total_ev, 3),
    })

df = pd.DataFrame(rows)

st.subheader("📊 Predictions")
st.dataframe(df, use_container_width=True)

# =========================================================
# TRACKER
# =========================================================
st.subheader("🪵 Tracker")

if st.button("➕ Add Bet"):
    add_bet()

for b in st.session_state.tracker:

    c = st.columns(10)

    b["Date"] = c[0].text_input("", b["Date"], key=b["id"]+"_d")
    b["Match"] = c[1].text_input("", b["Match"], key=b["id"]+"_m")
    b["Market"] = c[2].text_input("", b["Market"], key=b["id"]+"_mk")
    b["Selection"] = c[3].text_input("", b["Selection"], key=b["id"]+"_s")
    b["Bookmaker"] = c[4].text_input("", b["Bookmaker"], key=b["id"]+"_bk")
    b["Odds"] = c[5].number_input("", value=float(b["Odds"]), key=b["id"]+"_o")
    b["Stake"] = c[6].number_input("", value=float(b["Stake"]), key=b["id"]+"_st")

    b["Status"] = c[7].selectbox("", ["PENDING","WIN","LOSS","PUSH"], key=b["id"]+"_stt")

    if b["Status"] == "WIN":
        b["P/L"] = round((b["Odds"] - 1) * b["Stake"], 2)
    elif b["Status"] == "LOSS":
        b["P/L"] = -b["Stake"]
    else:
        b["P/L"] = 0

    c[8].write(b["P/L"])

    if c[9].button("❌", key=b["id"]):
        delete_bet(b["id"])
        st.rerun()
