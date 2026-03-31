import streamlit as st
import requests
import math
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide")

st.title("⚾ MLB Betting Engine V11 (Real Model)")

st.subheader(datetime.now().strftime("%A %d %B %Y"))

# =========================
# SESSION STATE
# =========================
if "bets" not in st.session_state:
    st.session_state.bets = []

# =========================
# MLB SCHEDULE
# =========================
def get_games():

    url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=probablePitcher,teams"

    data = requests.get(url).json()

    games = []

    for d in data.get("dates", []):
        for g in d.get("games", []):

            games.append({
                "home": g["teams"]["home"]["team"]["name"],
                "away": g["teams"]["away"]["team"]["name"],
                "home_pitcher": g["teams"]["home"].get("probablePitcher", {}),
                "away_pitcher": g["teams"]["away"].get("probablePitcher", {})
            })

    return games

games = get_games()

# =========================
# TEAM OFFENSE (proxy)
# =========================
def offense(team):

    base = {
        "Dodgers": 0.18, "Braves": 0.17, "Yankees": 0.15,
        "Astros": 0.14, "Phillies": 0.13, "Orioles": 0.13,
        "Mets": 0.09, "Mariners": 0.10, "Guardians": 0.08
    }

    return base.get(team, 0.10)

# =========================
# DEFENSE
# =========================
def defense(team):

    base = {
        "Dodgers": 0.12, "Braves": 0.11, "Yankees": 0.10,
        "Astros": 0.11, "Phillies": 0.10
    }

    return base.get(team, 0.08)

# =========================
# PARK FACTOR
# =========================
def park_factor(team):

    hitter_parks = ["Yankees", "Red Sox", "Cubs", "Rangers"]
    pitcher_parks = ["Dodgers", "Mets", "Mariners"]

    if team in hitter_parks:
        return 0.02
    if team in pitcher_parks:
        return -0.02

    return 0

# =========================
# PITCHER MODEL
# =========================
def pitcher_rating(p):

    if not p:
        return 0

    era = 4.3
    whip = 1.25
    k9 = 8.5
    bb9 = 3.0
    ip = 120

    try:
        pid = p.get("id")

        url = f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"
        data = requests.get(url, params={
            "stats": "season",
            "group": "pitching"
        }).json()

        s = data["stats"][0]["splits"][0]["stat"]

        era = float(s.get("era", era))
        whip = float(s.get("whip", whip))
        k9 = float(s.get("strikeoutsPer9Inn", k9))
        bb9 = float(s.get("baseOnBallsPer9Inn", bb9))
        ip = float(s.get("inningsPitched", ip))

    except:
        pass

    return (
        (4.5 - era) * 0.5 +
        (1.3 - whip) * 0.35 +
        (k9 - 8) * 0.06 -
        (bb9 - 3) * 0.07 +
        (ip / 200) * 0.2
    )

# =========================
# BULLPEN (SIMPLIFIED)
# =========================
def bullpen(team):

    base = {
        "Dodgers": 0.08, "Braves": 0.07, "Yankees": 0.06,
        "Astros": 0.06, "Phillies": 0.05
    }

    return base.get(team, 0.03)

# =========================
# WEATHER IMPACT
# =========================
def weather_adjustment():

    # simplified global adjustment (can later API upgrade)
    wind = 10
    temp = 20

    return (wind / 20) + ((temp - 20) / 50)

# =========================
# TEAM STRENGTH MODEL
# =========================
def team_strength(team, pitcher, is_home):

    value = (
        offense(team) +
        defense(team) +
        bullpen(team) +
        pitcher_rating(pitcher) +
        park_factor(team)
    )

    if is_home:
        value += 0.03

    return value

# =========================
# WIN PROB
# =========================
def win_prob(home, away, hp, ap):

    h = team_strength(home, hp, True)
    a = team_strength(away, ap, False)

    diff = h - a

    return 1 / (1 + math.exp(-diff * 6))

# =========================
# TOTALS MODEL
# =========================
def expected_runs(team, pitcher):

    base = 4.3 + offense(team) - pitcher_rating(pitcher) + park_factor(team)

    return max(2.0, min(8.5, base))

# =========================
# EV ENGINE
# =========================
def american_to_prob(o):

    if o < 0:
        return (-o) / (-o + 100)
    return 100 / (o + 100)

def ev(model_p, odds):

    return (model_p - american_to_prob(odds)) * 100

def kelly(p, odds):

    b = odds / 100 if odds > 0 else 100 / abs(odds)

    return max(0, (p * (b + 1) - 1) / b)

def grade(e):

    if e >= 5:
        return "STRONG BET"
    if e >= 2:
        return "LEAN"
    return "NO BET"

# =========================
# SLATE
# =========================
st.header("📊 Full Slate")

games = get_games()

for g in games:

    home = g["home"]
    away = g["away"]

    hp = g["home_pitcher"]
    ap = g["away_pitcher"]

    p_home = win_prob(home, away, hp, ap)

    ev_ml = ev(p_home, -110)

    pick = home if p_home > 0.5 else away

    home_runs = expected_runs(home, ap)
    away_runs = expected_runs(away, hp)

    total = home_runs + away_runs

    st.markdown("---")
    st.subheader(f"{away} @ {home}")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.write("🏟️ Pitchers")
        st.write(f"Away: {ap.get('fullName','TBD')}")
        st.write(f"Home: {hp.get('fullName','TBD')}")

    with c2:
        st.write("📈 Moneyline")
        st.write(f"Model: {round(p_home*100,2)}%")
        st.write(f"Pick: {pick}")
        st.write(f"EV: {round(ev_ml,2)}% {grade(ev_ml)}")

    with c3:
        st.write("⚾ Totals")
        st.write(f"Projected: {round(total,2)}")

    # =========================
    # TRACKER
    # =========================
    if st.button(f"➕ Add Bet {home}", key=f"{home}_{away}"):

        st.session_state.bets.append({
            "game": f"{away} @ {home}",
            "pick": pick,
            "odds": -110,
            "stake": 10,
            "ev": round(ev_ml,2),
            "type": "ML",
            "result": "Pending"
        })

# =========================
# TRACKER
# =========================
st.header("📒 Tracker")

st.dataframe(pd.DataFrame(st.session_state.bets))
