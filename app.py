import streamlit as st
import requests
import pandas as pd
import math

st.set_page_config(page_title="MLB Betting Engine V13", layout="wide")

API_KEY = "0d678e13097a84442df1e953f8fcaf95"

# ------------------ HELPERS ------------------ #

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def american_to_decimal(odds):
    if odds > 0:
        return 1 + (odds / 100)
    else:
        return 1 + (100 / abs(odds))

def calculate_ev(prob, odds):
    return (prob * odds) - 1

def clamp(x, low, high):
    return max(low, min(high, x))

# ------------------ FETCH DATA ------------------ #

def get_schedule():
    url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1"
    return requests.get(url).json()

def get_team_stats():
    url = "https://statsapi.mlb.com/api/v1/teams/stats?sportId=1"
    data = requests.get(url).json()
    
    stats = {}
    
    for team in data["stats"][0]["splits"]:
        name = team["team"]["name"]
        runs = float(team["stat"].get("runsPerGame", 4.5))
        
        stats[name] = {
            "runs": runs,
            "bullpen": 4.2  # fallback (MLB API weak here)
        }
    
    return stats

def get_pitcher_era(name):
    if not name:
        return 4.20
    
    try:
        search = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/search?names={name}"
        ).json()
        
        player_id = search["people"][0]["id"]
        
        stats = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=season"
        ).json()
        
        era = stats["stats"][0]["splits"][0]["stat"].get("era", 4.20)
        return float(era)
    
    except:
        return 4.20

def get_odds():
    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/?apiKey={API_KEY}&regions=au&markets=h2h,spreads,totals"
    return requests.get(url).json()

# ------------------ MODEL ------------------ #

def run_model(home, away, stats, hp_era, ap_era):
    
    offense_diff = (stats[home]["runs"] - stats[away]["runs"]) / 2
    
    pitcher_diff = ((10 - hp_era) - (10 - ap_era)) / 3
    
    bullpen_diff = 0  # placeholder until better source
    
    home_adv = 0.25
    
    edge = (
        0.4 * offense_diff +
        0.4 * pitcher_diff +
        0.2 * home_adv
    )
    
    prob = sigmoid(edge)
    prob = clamp(prob, 0.05, 0.75)
    
    spread = clamp(edge * 2.5, -3.5, 3.5)
    total = clamp(8.5 + offense_diff * 1.5, 6.5, 11)
    
    return prob, spread, total

# ------------------ MATCH ODDS ------------------ #

def match_odds(game, odds):
    for o in odds:
        if game["teams"]["home"]["team"]["name"] in o["home_team"]:
            return o
    return None

# ------------------ MAIN ------------------ #

st.title("⚾ MLB Betting Engine V13 ELITE")

schedule = get_schedule()
team_stats = get_team_stats()
odds_data = get_odds()

results = []

for date in schedule["dates"]:
    for game in date["games"]:
        
        home = game["teams"]["home"]["team"]["name"]
        away = game["teams"]["away"]["team"]["name"]
        
        odds = match_odds(game, odds_data)
        if not odds:
            continue
        
        hp = game["teams"]["home"].get("probablePitcher", {}).get("fullName")
        ap = game["teams"]["away"].get("probablePitcher", {}).get("fullName")
        
        hp_era = get_pitcher_era(hp)
        ap_era = get_pitcher_era(ap)
        
        prob, spread, total = run_model(home, away, team_stats, hp_era, ap_era)
        
        try:
            market = odds["bookmakers"][0]["markets"]
            h2h = [m for m in market if m["key"] == "h2h"][0]
            
            home_price = [o for o in h2h["outcomes"] if o["name"] == home][0]["price"]
            away_price = [o for o in h2h["outcomes"] if o["name"] == away][0]["price"]
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
            continue  # filter weak bets
        
        results.append({
            "Game": f"{away} @ {home}",
            "Best Bet": best_team,
            "EV %": round(best_ev * 100, 2),
            "Win Prob %": round(prob * 100, 2),
            "Proj Spread": round(spread, 2),
            "Proj Total": round(total, 2)
        })

df = pd.DataFrame(results)

if not df.empty:
    df = df.sort_values(by="EV %", ascending=False)
    st.dataframe(df, use_container_width=True)
else:
    st.write("No strong bets today")
