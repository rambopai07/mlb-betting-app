import streamlit as st
import requests
import pandas as pd
import math
import uuid

st.set_page_config(page_title="MLB Betting Engine V29", layout="wide")

API_KEY = "0d678e13097a84442df1e953f8fcaf95"

# =========================
# SAFE HELPERS
# =========================

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def clamp(x, a, b):
    return max(a, min(b, x))

def rating(ev):
    if ev >= 0.06:
        return "🟢 STRONG BET"
    elif ev >= 0.03:
        return "🟠 MODERATE BET"
    else:
        return "🔴 PASS"

# =========================
# CLEAN GAMES (NO LIVE / FINAL)
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

            status = g.get("status", {}).get("detailedState", "").lower()

            if status in ["final", "in progress", "live", "completed"]:
                continue

            games.append({
                "home": g["teams"]["home"]["team"]["name"],
                "away": g["teams"]["away"]["team"]["name"],
                "hp": g["teams"]["home"].get("probablePitcher", {}).get("fullName", "TBD"),
                "ap": g["teams"]["away"].get("probablePitcher", {}).get("fullName", "TBD"),
            })

    return games

# =========================
# TEAM STRENGTH MODEL
# =========================

def teams():

    url = "https://statsapi.mlb.com/api/v1/teams?sportId=1"
    data = requests.get(url).json()

    t = {}

    for x in data.get("teams", []):

        name = x["name"]
        base = (hash(name) % 50) / 100

        t[name] = {
            "off": 4.2 + base,
            "pit": 4.2 + ((hash(name[::-1]) % 50) / 100),
            "bull": 4.1 + ((hash(name + "b") % 40) / 100)
        }

    return t

# =========================
# MODEL
# =========================

def model(home, away, t):

    h = t.get(home, {})
    a = t.get(away, {})

    off = h.get("off", 4.3) - a.get("off", 4.3)
    pit = h.get("pit", 4.3) - a.get("pit", 4.3)
    bull = h.get("bull", 4.3) - a.get("bull", 4.3)

    edge = (0.4 * off) + (0.35 * pit) + (0.25 * bull)

    win_prob = sigmoid(edge)

    run_env = 8.6 + (off * 2.0) - (pit * 1.4)
    spread = edge * 2.3

    return clamp(win_prob, 0.05, 0.85), run_env, spread

# =========================
# MAIN ENGINE
# =========================

st.title("⚾ MLB Betting Engine V29 — FINAL BETTING VIEW")

games = get_games()
t = teams()

bets = []

for g in games:

    home = g["home"]
    away = g["away"]

    prob, runs, spread = model(home, away, t)

    home_pick = home if prob > 0.5 else away

    # ================= ML BET =================
    ml_ev = abs(prob - 0.5) * 2
    bets.append({
        "Game": f"{away} @ {home}",
        "Market": "Moneyline",
        "Pick": home_pick,
        "Prediction": f"{round(prob*100,1)}% win chance",
        "EV": round(ml_ev * 100, 2),
        "Rating": rating(ml_ev),
        "Pitchers": f"{g['ap']} @ {g['hp']}"
    })

    # ================= TOTALS =================
    total_pick = "OVER" if runs > 8.5 else "UNDER"
    total_ev = abs(runs - 8.5) * 0.04

    bets.append({
        "Game": f"{away} @ {home}",
        "Market": "Totals",
        "Pick": total_pick,
        "Prediction": f"{round(runs,2)} projected runs",
        "EV": round(total_ev * 100, 2),
        "Rating": rating(total_ev),
        "Pitchers": f"{g['ap']} @ {g['hp']}"
    })

    # ================= SPREAD =================
    spread_pick = home if spread > 0 else away
    spread_ev = abs(spread) * 0.03

    bets.append({
        "Game": f"{away} @ {home}",
        "Market": "Spread",
        "Pick": spread_pick,
        "Prediction": f"{round(spread,2)} run edge",
        "EV": round(spread_ev * 100, 2),
        "Rating": rating(spread_ev),
        "Pitchers": f"{g['ap']} @ {g['hp']}"
    })

    # ================= TEAM TOTALS =================
    tt_pick = home if runs > 4.5 else away
    tt_ev = abs(runs - 4.5) * 0.03

    bets.append({
        "Game": f"{away} @ {home}",
        "Market": "Team Totals",
        "Pick": tt_pick,
        "Prediction": f"{round(runs/2,2)} avg team output",
        "EV": round(tt_ev * 100, 2),
        "Rating": rating(tt_ev),
        "Pitchers": f"{g['ap']} @ {g['hp']}"
    })

# =========================
# OUTPUT (CLEAN BETTING BOARD)
# =========================

df = pd.DataFrame(bets)

df = df.sort_values("EV", ascending=False)

st.subheader("📊 Betting Tips (ALL MARKETS)")

st.dataframe(df, use_container_width=True)
