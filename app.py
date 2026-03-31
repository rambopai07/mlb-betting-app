import streamlit as st
import requests
import math
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide")

st.title("⚾ MLB Betting Engine V11.1 (Full Model + Tracker)")

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
# OFFENSE (proxy but stable)
# =========================
def offense(team):
    base = {
        "Dodgers": 0.18, "Braves": 0.17, "Yankees": 0.15,
        "Astros": 0.14, "Phillies": 0.13, "Orioles": 0.13,
        "Mets": 0.09, "Mariners": 0.10, "Guardians": 0.08,
        "Red Sox": 0.11, "Cubs": 0.10
    }
    return base.get(team, 0.10)

# =========================
# DEFENSE
# =========================
def defense(team):
    base = {
        "Dodgers": 0.12, "Braves": 0.11, "Yankees": 0.10,
        "Astros": 0.11, "Phillies": 0.10, "Orioles": 0.11
    }
    return base.get(team, 0.08)

# =========================
# BULLPEN
# =========================
def bullpen(team):
    base = {
        "Dodgers": 0.08, "Braves": 0.07, "Yankees": 0.06,
        "Astros": 0.06, "Phillies": 0.05, "Orioles": 0.06
    }
    return base.get(team, 0.04)

# =========================
# PARK FACTOR
# =========================
def park_factor(team):
    hitter = ["Yankees", "Red Sox", "Cubs", "Rangers"]
    pitcher = ["Dodgers", "Mets", "Mariners"]

    if team in hitter:
        return 0.02
    if team in pitcher:
        return -0.02
    return 0

# =========================
# PITCHER MODEL (REAL MLB API)
# =========================
def pitcher_rating(p):

    if not p:
        return 0

    try:
        pid = p.get("id")

        url = f"https://statsapi.mlb.com/api/v1/people/{pid}/stats"

        data = requests.get(url, params={
            "stats": "season",
            "group": "pitching"
        }).json()

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
# TEAM STRENGTH (FULL MODEL)
# =========================
def team_strength(team, pitcher, is_home):

    val = (
        offense(team) +
        defense(team) +
        bullpen(team) +
        pitcher_rating(pitcher) +
        park_factor(team)
    )

    if is_home:
        val += 0.03

    return val

# =========================
# WIN PROBABILITY
# =========================
def win_prob(home, away, hp, ap):

    h = team_strength(home, hp, True)
    a = team_strength(away, ap, False)

    diff = h - a

    return 1 / (1 + math.exp(-diff * 6))

# =========================
# RUN MODEL (TOTALS)
# =========================
def expected_runs(team, pitcher):

    base = 4.3 + offense(team) - pitcher_rating(pitcher) + park_factor(team)

    return max(2.0, min(8.5, base))

# =========================
# ODDS / EV
# =========================
def american_to_prob(o):
    if o < 0:
        return (-o) / (-o + 100)
    return 100 / (o + 100)

def ev(model_p, odds):
    return (model_p - american_to_prob(odds)) * 100

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

    # =====================
    # CORE MODEL
    # =====================
    p_home = win_prob(home, away, hp, ap)

    home_runs = expected_runs(home, ap)
    away_runs = expected_runs(away, hp)

    total = home_runs + away_runs
    spread = home_runs - away_runs

    # =====================
    # MONEYLINE
    # =====================
    ev_ml = ev(p_home, -110)
    ml_pick = home if p_home > 0.5 else away

    # =====================
    # TOTALS
    # =====================
    ev_tot = (total - 8.5) * 7
    tot_pick = "OVER" if total > 8.5 else "UNDER"

    # =====================
    # SPREAD
    # =====================
    ev_spread = spread * 6
    spread_pick = home if spread > 0 else away

    st.markdown("---")
    st.subheader(f"{away} @ {home}")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.write("🏟️ Pitchers")
        st.write(f"Away: {ap.get('fullName','TBD')}")
        st.write(f"Home: {hp.get('fullName','TBD')}")

    with c2:
        st.write("📈 MONEYLINE")
        st.write(f"Pick: {ml_pick}")
        st.write(f"EV: {round(ev_ml,2)}% {grade(ev_ml)}")

        st.write("⚾ TOTALS")
        st.write(f"Pick: {tot_pick}")
        st.write(f"EV: {round(ev_tot,2)}% {grade(ev_tot)}")

        st.write("📊 SPREAD")
        st.write(f"Pick: {spread_pick}")
        st.write(f"EV: {round(ev_spread,2)}% {grade(ev_spread)}")

    with c3:
        st.write("📊 Model Outputs")
        st.write(f"Win Prob: {round(p_home*100,2)}%")
        st.write(f"Total: {round(total,2)}")
        st.write(f"Spread: {round(spread,2)}")

    # =========================
    # ADD BETS (ALL MARKETS)
    # =========================
    if st.button(f"➕ Add Bets {home}", key=f"{home}_{away}"):

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
            "type": "TOTALS",
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
# TRACKER (FULL EDITABLE)
# =========================
st.header("📒 Bet Tracker")

if len(st.session_state.bets) > 0:

    df = pd.DataFrame(st.session_state.bets)

    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True
    )

    st.session_state.bets = edited.to_dict("records")

    for i in range(len(st.session_state.bets)):

        if st.button(f"🗑 Delete Bet {i}", key=f"del_{i}"):

            st.session_state.bets.pop(i)
            st.rerun()

else:
    st.info("No bets yet")
