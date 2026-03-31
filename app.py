import streamlit as st
import requests
import pandas as pd
import math

st.set_page_config(page_title="MLB Betting Engine V13 Stable", layout="wide")

API_KEY = "0d678e13097a84442df1e953f8fcaf95"

# ------------------ HELPERS ------------------ #

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def american_to_decimal(odds):
    if odds is None:
        return 2.0
    if odds > 0:
        return 1 + (odds / 100)
    else:
        return 1 + (100 / abs(odds))

def clamp(x, low, high):
    return max(low, min(high, x))

def calculate_ev(prob, odds):
    return (prob * odds) - 1

# ------------------ MLB DATA ------------------ #

def get_schedule():
    url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1"
    return requests.get(url).json()

# ------------------ SAFE TEAM STATS (FIXED) ------------------ #

def get_team_stats():
    url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    data = requests.get(url).json()

    stats = {}

    for team in data.get("teams", []):
        name = team.get("name")

        # default fallback
        stats[name] = {
            "runs": 4.5,
            "bullpen": 4.2
        }

    return stats

# ------------------ PITCHER ERA (SAFE) ------------------ #

def get_pitcher_era(name):
    if not name:
        return 4.5

    try:
        url = f"https://statsapi.mlb.com/api/v1/people/search?names={name}"
        data = requests.get(url).json()

        people = data.get("people", [])
        if not people:
            return 4.5

        player_id = people[0]["id"]

        stats_url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season"
        stats = requests.get(stats_url).json()

        splits = stats.get("stats", [{}])[0].get("splits", [])
        if not splits:
            return 4.5

        era = splits[0]["stat"].get("era", 4.5)
        return float(era)

    except:
        return 4.5

# ------------------ ODDS ------------------ #

def get_odds():
    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/?apiKey={API_KEY}&regions=au&markets=h2h"
    try:
        return requests.get(url).json()
    except:
        return []

def match_odds(game, odds_data):
    home = game["teams"]["home"]["team"]["name"]
    away = game["teams"]["away"]["team"]["name"]

    for o in odds_data:
        if home in o.get("home_team", ""):
            return o
    return None

# ------------------ MODEL ------------------ #

def run_model(home_runs, away_runs, home_era, away_era):

    offense_diff = (home_runs - away_runs) / 2
    pitcher_diff = ((10 - home_era) - (10 - away_era)) / 3

    home_adv = 0.15

    edge = (
        0.5 * offense_diff +
        0.4 * pitcher_diff +
        0.1 * home_adv
    )

    prob = sigmoid(edge)
    prob = clamp(prob, 0.05, 0.75)

    spread = clamp(edge * 2.5, -3.5, 3.5)
    total = clamp(8.5 + offense_diff * 1.5, 6.5, 11)

    return prob, spread, total

# ------------------ MAIN APP ------------------ #

st.title("⚾ MLB Betting Engine V13 (Stable)")

schedule = get_schedule()
odds_data = get_odds()
team_stats = get_team_stats()

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

        prob, spread, total = run_model(home_runs, away_runs, home_era, away_era)

        try:
            markets = odds.get("bookmakers", [])[0].get("markets", [])
            h2h = next((m for m in markets if m["key"] == "h2h"), None)

            if not h2h:
                continue

            home_price = next((o["price"] for o in h2h["outcomes"] if o["name"] == home), None)
            away_price = next((o["price"] for o in h2h["outcomes"] if o["name"] == away), None)

            if home_price is None or away_price is None:
                continue

        except:
            continue

        home_odds = american_to_decimal(home_price)
        away_odds = american_to_decimal(away_price)

        home_ev = calculate_ev(prob, home_odds)
        away_ev = calculate_ev(1 - prob, away_odds)

        home_ev = clamp(home_ev, -0.3, 0.2)
        away_ev = clamp(away_ev, -0.3, 0.2)

        best_team = home if home_ev > away_ev else away
        best_ev = max(home_ev, away_ev)

        if best_ev < 0.03:
            continue

        results.append({
            "Game": f"{away} @ {home}",
            "Best Bet": best_team,
            "EV %": round(best_ev * 100, 2),
            "Win Prob %": round(prob * 100, 2),
            "Spread": round(spread, 2),
            "Total": round(total, 2)
        })

# ------------------ OUTPUT ------------------ #

df = pd.DataFrame(results)

if not df.empty:
    df = df.sort_values("EV %", ascending=False)
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No valid games or odds found today.")
