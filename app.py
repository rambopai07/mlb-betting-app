import streamlit as st
import requests
import pandas as pd
import math
import os
from datetime import datetime, timedelta

st.set_page_config(page_title="MLB Engine V20 CLV Auto", layout="wide")

API_KEY = "0d678e13097a84442df1e953f8fcaf95"
LOG_FILE = "bet_log.csv"

# ------------------ HELPERS ------------------ #

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def clamp(x, a, b):
    return max(a, min(b, x))

def american_to_decimal(o):
    return 1 + (100 / abs(o)) if o < 0 else 1 + (o / 100)

def ev(prob, odds):
    return (prob * odds) - 1

def clean(name):
    return (name or "").lower().strip()

# ------------------ CALIBRATION ------------------ #

def calibrate(prob):
    return clamp((prob * 0.92) + 0.04, 0.02, 0.98)

# ------------------ ODDS ------------------ #

def get_odds():
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "us,au",
        "markets": "h2h",
        "oddsFormat": "american"
    }
    return requests.get(url, params=params).json()

# ------------------ TEAM MODEL ------------------ #

def get_team_strength():
    url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    data = requests.get(url).json()

    teams = {}

    for t in data.get("teams", []):
        name = t["name"]
        base = (hash(name) % 40) / 100

        teams[name] = {
            "offense": 4.2 + base,
            "pitching": 4.2 + ((hash(name[::-1]) % 40) / 100),
            "bullpen": 4.1 + ((hash(name + "bp") % 30) / 100)
        }

    return teams

# ------------------ MODEL ------------------ #

def predict(game, teams):

    home = game["home_team"]
    away = game["away_team"]

    h = teams.get(home, {})
    a = teams.get(away, {})

    offense = h.get("offense", 4.3) - a.get("offense", 4.3)
    pitching = h.get("pitching", 4.3) - a.get("pitching", 4.3)
    bullpen = h.get("bullpen", 4.3) - a.get("bullpen", 4.3)

    home_adv = 0.15

    ml_edge = (
        0.40 * offense +
        0.30 * pitching +
        0.20 * bullpen +
        0.10 * home_adv
    )

    prob = sigmoid(ml_edge)
    prob = clamp(prob, 0.05, 0.85)

    return calibrate(prob)

# ------------------ LOG SYSTEM ------------------ #

def load_log():
    if os.path.exists(LOG_FILE):
        return pd.read_csv(LOG_FILE)
    return pd.DataFrame(columns=[
        "id", "time", "game", "team",
        "model_odds", "closing_odds", "clv", "last_updated"
    ])

def save_log(df):
    df.to_csv(LOG_FILE, index=False)

def make_id(game, team):
    return f"{game}_{team}".replace(" ", "_").lower()

# ------------------ UPDATE CLV (AUTO) ------------------ #

def update_clv(df, odds_data):

    for i, row in df.iterrows():

        if pd.notnull(row["clv"]):
            continue

        game_name = row["game"]
        team = row["team"]

        home, away = game_name.split(" @ ")

        match = next(
            (g for g in odds_data
             if g["home_team"] == home and g["away_team"] == away),
            None
        )

        if not match:
            continue

        books = match.get("bookmakers", [])
        if not books:
            continue

        try:
            h2h = books[0]["markets"][0]

            closing_price = next(
                (o["price"] for o in h2h["outcomes"]
                 if clean(o["name"]) == clean(team)),
                None
            )

            if not closing_price:
                continue

            closing_odds = american_to_decimal(closing_price)
            entry_odds = row["model_odds"]

            clv = (closing_odds - entry_odds) / entry_odds

            df.at[i, "closing_odds"] = closing_odds
            df.at[i, "clv"] = clv
            df.at[i, "last_updated"] = datetime.utcnow().isoformat()

        except:
            continue

    return df

# ------------------ MAIN ------------------ #

st.title("⚾ MLB Engine V20 — AUTO CLV SYSTEM")

odds_data = get_odds()
teams = get_team_strength()

log = load_log()

# 🔥 UPDATE OLD BETS WITH LATEST ODDS (REAL CLV)
log = update_clv(log, odds_data)
save_log(log)

results = []

for game in odds_data:

    home = game.get("home_team")
    away = game.get("away_team")

    if not home or not away:
        continue

    books = game.get("bookmakers", [])
    if not books:
        continue

    try:
        markets = books[0].get("markets", [])
        h2h = next((m for m in markets if m["key"] == "h2h"), None)
        if not h2h:
            continue

        def price(team):
            return next(
                (o["price"] for o in h2h["outcomes"]
                 if clean(o["name"]) == clean(team)),
                None
            )

        home_price = price(home)
        away_price = price(away)

        if not home_price or not away_price:
            continue

    except:
        continue

    prob = predict(game, teams)

    home_odds = american_to_decimal(home_price)
    away_odds = american_to_decimal(away_price)

    home_ev = ev(prob, home_odds)
    away_ev = ev(1 - prob, away_odds)

    best = home if home_ev > away_ev else away
    best_odds = home_odds if best == home else away_odds

    if max(home_ev, away_ev) < 0.02:
        continue

    game_id = make_id(f"{away} @ {home}", best)

    # avoid duplicate logging
    if game_id not in log["id"].values:

        log = pd.concat([log, pd.DataFrame([{
            "id": game_id,
            "time": datetime.utcnow().isoformat(),
            "game": f"{away} @ {home}",
            "team": best,
            "model_odds": best_odds,
            "closing_odds": None,
            "clv": None,
            "last_updated": None
        }])], ignore_index=True)

    results.append({
        "Game": f"{away} @ {home}",
        "Best Bet": best,
        "Win %": round(prob * 100, 2),
        "Odds": round(best_odds, 2)
    })

save_log(log)

st.subheader("📊 Today's Bets")
st.dataframe(pd.DataFrame(results), use_container_width=True)

st.subheader("📈 CLV Performance (LIVE UPDATING)")
st.dataframe(log.sort_values("time", ascending=False).head(50), use_container_width=True)
