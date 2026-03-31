import streamlit as st
import requests
import pandas as pd
import math

st.set_page_config(page_title="MLB Betting Engine V14", layout="wide")

API_KEY = "0d678e13097a84442df1e953f8fcaf95"

# ------------------ HELPERS ------------------ #

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def clamp(x, low, high):
    return max(low, min(high, x))

def american_to_decimal(odds):
    if odds is None:
        return 2.0
    return 1 + (100 / abs(odds)) if odds < 0 else 1 + (odds / 100)

def calculate_ev(prob, odds):
    return (prob * odds) - 1

def normalize(name):
    return (name or "").lower().replace(" ", "")

# ------------------ DATA ------------------ #

def get_schedule():
    url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1"
    return requests.get(url).json()

def get_odds():
    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/?apiKey={API_KEY}&regions=au&markets=h2h"
    try:
        return requests.get(url).json()
    except:
        return []

def get_team_stats():
    url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    data = requests.get(url).json()

    stats = {}

    for t in data.get("teams", []):
        stats[t["name"]] = {
            "runs": 4.5,   # fallback (MLB API doesn't reliably give clean team offense here)
            "bullpen": 4.2
        }

    return stats

def get_pitcher_era(name):
    if not name:
        return 4.5

    try:
        search = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/search?names={name}"
        ).json()

        people = search.get("people", [])
        if not people:
            return 4.5

        pid = people[0]["id"]

        stats = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=season"
        ).json()

        splits = stats.get("stats", [{}])[0].get("splits", [])
        if not splits:
            return 4.5

        return float(splits[0]["stat"].get("era", 4.5))

    except:
        return 4.5

# ------------------ ODDS MATCHING (FIXED) ------------------ #

def match_odds(game, odds_data):

    home = normalize(game["teams"]["home"]["team"]["name"])
    away = normalize(game["teams"]["away"]["team"]["name"])

    for o in odds_data:

        if not o.get("home_team") or not o.get("away_team"):
            continue

        o_home = normalize(o["home_team"])
        o_away = normalize(o["away_team"])

        if home == o_home and away == o_away:
            return o

    return None

# ------------------ MODEL ------------------ #

def model(home_runs, away_runs, home_era, away_era):

    offense = (home_runs - away_runs) / 2
    pitching = ((10 - home_era) - (10 - away_era)) / 3

    edge = (
        0.5 * offense +
        0.4 * pitching +
        0.1 * 0.2
    )

    prob = sigmoid(edge)
    prob = clamp(prob, 0.05, 0.75)

    spread = clamp(edge * 2.4, -3.5, 3.5)
    total = clamp(8.5 + offense * 1.4, 6.5, 11.5)

    return prob, spread, total

# ------------------ MAIN ------------------ #

st.title("⚾ MLB Betting Engine V14 (Bulletproof)")

schedule = get_schedule()
odds_data = get_odds()
team_stats = get_team_stats()

st.write("Games loaded:", len(schedule.get("dates", [])))
st.write("Odds loaded:", len(odds_data))

results = []

for day in schedule.get("dates", []):

    for game in day.get("games", []):

        home = game["teams"]["home"]["team"]["name"]
        away = game["teams"]["away"]["team"]["name"]

        odds = match_odds(game, odds_data)
        if not odds:
            continue

        home_pitcher = game["teams"]["home"].get("probablePitcher", {}).get("fullName")
        away_pitcher = game["teams"]["away"].get("probablePitcher", {}).get("fullName")

        home_era = get_pitcher_era(home_pitcher)
        away_era = get_pitcher_era(away_pitcher)

        home_runs = team_stats.get(home, {}).get("runs", 4.5)
        away_runs = team_stats.get(away, {}).get("runs", 4.5)

        prob, spread, total = model(home_runs, away_runs, home_era, away_era)

        try:
            bookmakers = odds.get("bookmakers", [])
            if not bookmakers:
                continue

            markets = bookmakers[0].get("markets", [])
            h2h = next((m for m in markets if m["key"] == "h2h"), None)
            if not h2h:
                continue

            home_price = next((x["price"] for x in h2h["outcomes"] if normalize(x["name"]) == normalize(home)), None)
            away_price = next((x["price"] for x in h2h["outcomes"] if normalize(x["name"]) == normalize(away)), None)

            if home_price is None or away_price is None:
                continue

        except:
            continue

        home_odds = american_to_decimal(home_price)
        away_odds = american_to_decimal(away_price)

        home_ev = calculate_ev(prob, home_odds)
        away_ev = calculate_ev(1 - prob, away_odds)

        best_team = home if home_ev > away_ev else away
        best_ev = max(home_ev, away_ev)

        if best_ev < 0.03:
            continue

        results.append({
            "Game": f"{away} @ {home}",
            "Best Bet": best_team,
            "EV %": round(best_ev * 100, 2),
            "Win %": round(prob * 100, 2),
            "Spread": round(spread, 2),
            "Total": round(total, 2)
        })

# ------------------ OUTPUT ------------------ #

df = pd.DataFrame(results)

if df.empty:
    st.warning("No valid matches today (either odds missing or API mismatch).")
else:
    df = df.sort_values("EV %", ascending=False)
    st.dataframe(df, use_container_width=True)
