import streamlit as st
import requests
import pandas as pd
import math
from datetime import datetime

st.set_page_config(layout="wide")

# =========================
# HEADER
# =========================
today = datetime.now().strftime("%A %d %B %Y")
st.title("⚾ MLB Betting Engine V8 (Fixed Pitcher ID Model)")
st.subheader(f"📅 Slate: {today}")

# =========================
# SESSION STATE
# =========================
if "bets" not in st.session_state:
    st.session_state.bets = []

# =========================
# MLB SCHEDULE (WITH PITCHER IDS)
# =========================
def get_mlb_schedule():

    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        "?sportId=1"
        "&date=2026-03-31"
        "&hydrate=probablePitcher,teams"
    )

    data = requests.get(url).json()
    games = []

    for d in data.get("dates", []):
        for g in d.get("games", []):

            home_team = g["teams"]["home"]["team"]["name"]
            away_team = g["teams"]["away"]["team"]["name"]

            home_pitcher = g["teams"]["home"].get("probablePitcher")
            away_pitcher = g["teams"]["away"].get("probablePitcher")

            home_pid = home_pitcher["id"] if home_pitcher else None
            away_pid = away_pitcher["id"] if away_pitcher else None

            home_pname = home_pitcher["fullName"] if home_pitcher else "TBD"
            away_pname = away_pitcher["fullName"] if away_pitcher else "TBD"

            games.append({
                "home": home_team,
                "away": away_team,
                "home_pid": home_pid,
                "away_pid": away_pid,
                "home_pname": home_pname,
                "away_pname": away_pname
            })

    return games

games = get_mlb_schedule()

# =========================
# TEAM STRENGTH (expanded variance)
# =========================
def team_strength(team):

    base = {
        "Dodgers": 0.16, "Yankees": 0.13, "Braves": 0.15, "Astros": 0.11,
        "Phillies": 0.09, "Orioles": 0.10, "Rangers": 0.08,
        "Mets": 0.04, "Mariners": 0.05, "Guardians": 0.03,
        "Red Sox": 0.03, "Cubs": 0.04, "Padres": 0.06
    }

    return base.get(team, 0.0)

# =========================
# PITCHER STATS (BY ID — FIXED)
# =========================
PITCHER_CACHE = {}

def get_pitcher_stats(pid):

    if pid in PITCHER_CACHE:
        return PITCHER_CACHE[pid]

    try:
        url = f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"

        data = requests.get(url, params={
            "stats": "season",
            "group": "pitching"
        }).json()

        s = data["stats"][0]["splits"][0]["stat"]

        stats = {
            "era": float(s.get("era", 4.5)),
            "whip": float(s.get("whip", 1.3)),
            "k9": float(s.get("strikeoutsPer9Inn", 8.0)),
            "bb9": float(s.get("baseOnBallsPer9Inn", 3.0)),
            "ip": float(s.get("inningsPitched", 100))
        }

    except:
        stats = None

    PITCHER_CACHE[pid] = stats
    return stats

# =========================
# PITCHER RATING
# =========================
def pitcher_rating(stats):

    if not stats:
        return 0

    return (
        (4.5 - stats["era"]) * 0.45 +
        (1.3 - stats["whip"]) * 0.35 +
        (stats["k9"] - 8) * 0.06 -
        (stats["bb9"] - 3) * 0.07 +
        (stats["ip"] / 200) * 0.2
    )

# =========================
# WIN PROBABILITY
# =========================
def win_prob(home, away):

    h_pitch = pitcher_rating(get_pitcher_stats(home["home_pid"]))
    a_pitch = pitcher_rating(get_pitcher_stats(away["away_pid"]))

    h = team_strength(home["home"]) + h_pitch + 0.05
    a = team_strength(away["away"]) + a_pitch

    diff = h - a

    return 1 / (1 + math.exp(-diff * 6))

# =========================
# RUN MODEL
# =========================
def expected_runs(team, pid):

    p = pitcher_rating(get_pitcher_stats(pid))

    base = 4.3 + team_strength(team)

    return max(2.0, min(7.8, base - p))

def totals_model(home, away):

    hr = expected_runs(home["home"], away["away_pid"])
    ar = expected_runs(away["away"], home["home_pid"])

    return round(hr + ar, 2), round(hr, 2), round(ar, 2)

# =========================
# EDGE
# =========================
def ml_edge(p):
    return round((p - 0.5) * 100, 2)

def total_edge(t):
    return round((t - 8.5) * 5, 2)

def grade(e):
    if e <= 0:
        return "NO BET"
    if e >= 5:
        return "STRONG BET"
    if e >= 2:
        return "LEAN"
    return "NO BET"

# =========================
# PICK
# =========================
def pick(game, p):

    return game["home"] if p > 0.5 else game["away"]

# =========================
# UI
# =========================
st.header("📊 MLB Slate")

for g in games:

    st.markdown("---")
    st.subheader(f"{g['away']} @ {g['home']}")

    col1, col2 = st.columns(2)

    p = win_prob(g, g)

    total, hr, ar = totals_model(g, g)

    ml_e = ml_edge(p)
    t_e = total_edge(total)

    bet_pick = pick(g, p)

    with col1:
        st.write("🏟️ Pitchers")
        st.write(f"Away: {g['away_pname']}")
        st.write(f"Home: {g['home_pname']}")

        st.write("📈 Moneyline")
        st.write(f"Win Prob: {round(p*100,2)}%")
        st.write(f"👉 PICK: {bet_pick}")
        st.write(f"Edge: {ml_e}% {grade(ml_e)}")

    with col2:
        st.write("⚾ Totals")
        st.write(f"Projected: {total}")
        st.write(f"{g['home']}: {hr}")
        st.write(f"{g['away']}: {ar}")
        st.write(f"Edge: {t_e}% {grade(t_e)}")

    # =========================
    # BET TRACKER
    # =========================
    if st.button(f"➕ Add Bet {g['away']} @ {g['home']}", key=f"{g['away']}_{g['home']}"):

        st.session_state.bets.append({
            "game": f"{g['away']} @ {g['home']}",
            "pick": bet_pick,
            "ml_prob": round(p, 3),
            "ml_edge": ml_e,
            "total_edge": t_e,
            "status": "open"
        })

        st.success("Bet added!")

# =========================
# TRACKER
# =========================
st.header("📒 Bet Tracker")

if st.session_state.bets:
    st.dataframe(pd.DataFrame(st.session_state.bets))
else:
    st.info("No bets yet")
