import streamlit as st
import requests
import math
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide")

st.title("⚾ MLB Betting Engine V11.2 (Scaled Model Fix)")
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

# =========================
# TEAM FACTORS
# =========================
def offense(team):
    base = {
        "Dodgers": 0.18, "Braves": 0.17, "Yankees": 0.15,
        "Astros": 0.14, "Phillies": 0.13, "Orioles": 0.13,
        "Mets": 0.09, "Mariners": 0.10, "Guardians": 0.08
    }
    return base.get(team, 0.10)

def defense(team):
    return 0.10

def bullpen(team):
    return 0.06

def park_factor(team):
    hitter = ["Yankees", "Red Sox", "Cubs"]
    pitcher = ["Dodgers", "Mariners"]

    if team in hitter:
        return 0.02
    if team in pitcher:
        return -0.02
    return 0

# =========================
# PITCHER MODEL
# =========================
def pitcher_rating(p):

    if not p:
        return 0

    try:
        pid = p.get("id")

        url = f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"
        data = requests.get(url, params={"stats": "season", "group": "pitching"}).json()

        s = data["stats"][0]["splits"][0]["stat"]

        era = float(s.get("era", 4.3))
        whip = float(s.get("whip", 1.25))
        k9 = float(s.get("strikeoutsPer9Inn", 8.5))
        bb9 = float(s.get("baseOnBallsPer9Inn", 3.0))
        ip = float(s.get("inningsPitched", 120))

    except:
        era, whip, k9, bb9, ip = 4.3, 1.25, 8.5, 3.0, 120

    return (
        (4.5 - era) * 0.5 +
        (1.3 - whip) * 0.35 +
        (k9 - 8) * 0.06 -
        (bb9 - 3) * 0.07 +
        (ip / 200) * 0.2
    )

# =========================
# TEAM STRENGTH (FIXED SCALE)
# =========================
def team_strength(team, pitcher, is_home):

    off = offense(team) * 100
    defn = defense(team) * 60
    bull = bullpen(team) * 40
    park = park_factor(team) * 100
    pitch = pitcher_rating(pitcher) * 120

    home = 2.5 if is_home else 0

    return off - defn - bull + pitch + park + home

# =========================
# WIN PROBABILITY (FIXED)
# =========================
def win_prob(home, away, hp, ap):

    h = team_strength(home, hp, True)
    a = team_strength(away, ap, False)

    diff = h - a

    return 1 / (1 + math.exp(-diff / 18))

# =========================
# RUN MODEL (FIXED)
# =========================
def expected_runs(team, pitcher):

    base_runs = 4.3

    off = offense(team) * 5
    pitch = pitcher_rating(pitcher) * 6

    return max(2.0, min(8.5, base_runs + off - pitch + (park_factor(team) * 2)))

# =========================
# EV + GRADING
# =========================
def grade(e):
    if e >= 5:
        return "🟢 STRONG BET"
    if e >= 2:
        return "🟡 LEAN"
    return "🔴 NO BET"

# =========================
# SLATE
# =========================
st.header("📊 Full MLB Slate")

games = get_games()

for g in games:

    home = g["home"]
    away = g["away"]

    hp = g["home_pitcher"]
    ap = g["away_pitcher"]

    # MODEL
    p_home = win_prob(home, away, hp, ap)

    home_runs = expected_runs(home, ap)
    away_runs = expected_runs(away, hp)

    total = home_runs + away_runs
    spread = home_runs - away_runs

    # ML
    ev_ml = (p_home - 0.52) * 100
    ml_pick = home if p_home > 0.5 else away

    # TOTALS
    ev_tot = (total - 8.5) * 7
    tot_pick = "OVER" if total > 8.5 else "UNDER"

    # SPREAD
    ev_spread = spread * 6
    spread_pick = home if spread > 0 else away

    st.markdown("---")
    st.subheader(f"{away} @ {home}")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.write("Pitchers")
        st.write(f"Away: {ap.get('fullName','TBD')}")
        st.write(f"Home: {hp.get('fullName','TBD')}")

    with c2:
        st.write("Moneyline")
        st.write(f"{ml_pick} | EV: {round(ev_ml,2)}% {grade(ev_ml)}")

        st.write("Totals")
        st.write(f"{tot_pick} | EV: {round(ev_tot,2)}% {grade(ev_tot)}")

        st.write("Spread")
        st.write(f"{spread_pick} | EV: {round(ev_spread,2)}% {grade(ev_spread)}")

    with c3:
        st.write("Model")
        st.write(f"Win %: {round(p_home*100,2)}")
        st.write(f"Total: {round(total,2)}")
        st.write(f"Spread: {round(spread,2)}")

    # ADD BETS
    if st.button(f"Add Bets {home}", key=f"{home}_{away}"):

        st.session_state.bets.append({
            "game": f"{away} @ {home}",
            "type": "ML",
            "pick": ml_pick,
            "odds": -110,
            "stake": 10,
            "ev": round(ev_ml,2),
            "result": "Pending"
        })

        st.session_state.bets.append({
            "game": f"{away} @ {home}",
            "type": "TOTAL",
            "pick": tot_pick,
            "odds": -110,
            "stake": 10,
            "ev": round(ev_tot,2),
            "result": "Pending"
        })

        st.session_state.bets.append({
            "game": f"{away} @ {home}",
            "type": "SPREAD",
            "pick": spread_pick,
            "odds": -110,
            "stake": 10,
            "ev": round(ev_spread,2),
            "result": "Pending"
        })

# =========================
# TRACKER (EDITABLE)
# =========================
st.header("📒 Bet Tracker")

if len(st.session_state.bets) > 0:

    df = pd.DataFrame(st.session_state.bets)

    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)

    st.session_state.bets = edited.to_dict("records")

    for i in range(len(st.session_state.bets)):
        if st.button(f"Delete {i}", key=f"del_{i}"):
            st.session_state.bets.pop(i)
            st.rerun()

else:
    st.info("No bets yet")
