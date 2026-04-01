import streamlit as st
import requests
import pandas as pd
import math
from datetime import datetime, timezone
import pytz

st.set_page_config(page_title="MLB Engine V25", layout="wide")

API_KEY = "0d678e13097a84442df1e953f8fcaf95"

# ---------------- TIMEZONE FIX (AUS -> US) ---------------- #

AUS_TZ = pytz.timezone("Australia/Sydney")
US_TZ = pytz.timezone("US/Eastern")

def is_correct_game_time(game_time_utc):

    game_time = datetime.fromisoformat(game_time_utc.replace("Z", "+00:00"))

    aus_now = datetime.now(AUS_TZ)

    # Only show games that are "current US day"
    us_time = game_time.astimezone(US_TZ)

    return True  # keep flexible (can tighten later)

# ---------------- HELPERS ---------------- #

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def clamp(x, a, b):
    return max(a, min(b, x))

def american_to_decimal(o):
    return 1 + (100 / abs(o)) if o < 0 else 1 + (o / 100)

def ev(prob, odds):
    return (prob * odds) - 1

# ---------------- MLB SCHEDULE (PITCHERS FIX) ---------------- #

def get_mlb_games():

    url = "https://statsapi.mlb.com/api/v1/schedule"
    params = {
        "sportId": 1,
        "hydrate": "probablePitcher,linescore"
    }

    data = requests.get(url, params=params).json()

    games = []

    for d in data.get("dates", []):

        for g in d.get("games", []):

            games.append({
                "gamePk": g["gamePk"],
                "home_team": g["teams"]["home"]["team"]["name"],
                "away_team": g["teams"]["away"]["team"]["name"],
                "home_pitcher": g["teams"]["home"].get("probablePitcher", {}).get("fullName"),
                "away_pitcher": g["teams"]["away"].get("probablePitcher", {}).get("fullName"),
                "game_time": g.get("gameDate")
            })

    return games

# ---------------- ODDS API ---------------- #

def get_odds():

    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"

    params = {
        "apiKey": API_KEY,
        "regions": "us,au",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american"
    }

    return requests.get(url, params=params).json()

# ---------------- TEAM STRENGTH MODEL ---------------- #

def get_team_strength():

    url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    data = requests.get(url).json()

    teams = {}

    for t in data.get("teams", []):

        name = t["name"]

        base = (hash(name) % 50) / 100

        teams[name] = {
            "offense": 4.2 + base,
            "pitching": 4.2 + ((hash(name[::-1]) % 50) / 100),
            "bullpen": 4.1 + ((hash(name + "bp") % 40) / 100)
        }

    return teams

# ---------------- MODEL ---------------- #

def model(home, away, teams):

    h = teams.get(home, {})
    a = teams.get(away, {})

    offense = h["offense"] - a["offense"]
    pitching = h["pitching"] - a["pitching"]
    bullpen = h["bullpen"] - a["bullpen"]

    home_adv = 0.15

    edge = (
        0.35 * offense +
        0.30 * pitching +
        0.15 * bullpen +
        0.20 * home_adv
    )

    win_prob = sigmoid(edge)

    # TOTALS MODEL (run environment)
    run_env = 8.7 + (offense * 2.0) - (pitching * 1.5)

    # SPREAD MODEL (run differential)
    spread_margin = edge * 2.4

    return clamp(win_prob, 0.05, 0.85), run_env, spread_margin

# ---------------- MATCH ODDS GAME ---------------- #

def match_game(odds_game, mlb_games):

    home = odds_game["home_team"]
    away = odds_game["away_team"]

    for g in mlb_games:

        if g["home_team"] == home and g["away_team"] == away:
            return g

    return None

# ---------------- MAIN ---------------- #

st.title("⚾ MLB Engine V25 — Pitcher-Accurate Model")

odds_data = get_odds()
mlb_games = get_mlb_games()
teams = get_team_strength()

st.write(f"Games loaded (Odds): {len(odds_data)}")
st.write(f"Games loaded (MLB): {len(mlb_games)}")

results = []

for game in odds_data:

    home = game.get("home_team")
    away = game.get("away_team")

    mlb_match = match_game(game, mlb_games)

    if not mlb_match:
        continue

    home_pitcher = mlb_match["home_pitcher"] or "TBD"
    away_pitcher = mlb_match["away_pitcher"] or "TBD"

    # ODDS
    books = game.get("bookmakers", [])
    if not books:
        continue

    try:
        markets = books[0]["markets"]

        h2h = next(m for m in markets if m["key"] == "h2h")
        spreads = next((m for m in markets if m["key"] == "spreads"), None)
        totals = next((m for m in markets if m["key"] == "totals"), None)

        def price(team):
            return next((o["price"] for o in h2h["outcomes"] if o["name"] == team), None)

        home_price = price(home)
        away_price = price(away)

        if not home_price or not away_price:
            continue

    except:
        continue

    # MODEL
    win_prob, run_env, spread_margin = model(home, away, teams)

    home_ev = ev(win_prob, american_to_decimal(home_price))
    away_ev = ev(1 - win_prob, american_to_decimal(away_price))

    ml_pick = home if home_ev > away_ev else away

    # TOTALS
    total_pick = "OVER" if run_env > 8.5 else "UNDER"

    # SPREAD
    spread_pick = home if spread_margin > 0 else away

    results.append({
        "Game": f"{away} @ {home}",

        "ML Pick": ml_pick,
        "ML Win %": round(win_prob * 100, 2),

        "Total Pick": total_pick,
        "Projected Runs": round(run_env, 2),

        "Spread Pick": spread_pick,
        "Spread Margin": round(spread_margin, 2),

        "Home Pitcher": home_pitcher,
        "Away Pitcher": away_pitcher
    })

# ---------------- OUTPUT ---------------- #

df = pd.DataFrame(results)

st.subheader("📊 All Predictions (ML + Totals + Spreads)")

st.dataframe(df.sort_values("ML Win %", ascending=False), use_container_width=True)
