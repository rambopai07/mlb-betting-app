import streamlit as st
import requests
import pandas as pd
import math
import uuid
from datetime import datetime, timedelta

st.set_page_config(page_title="MLB Engine V42 PRO", layout="wide")

ODDS_API_KEY = "0d678e13097a84442df1e953f8fcaf95"

# =========================
# SAFE HELPERS
# =========================
def sigmoid(x): return 1/(1+math.exp(-x))

def safe(d, path, default=None):
    try:
        for p in path:
            d = d[p]
        return d
    except:
        return default

# =========================
# DATE (US FIX FROM AUS)
# =========================
def get_us_date():
    return (datetime.utcnow() - timedelta(hours=6)).strftime("%Y-%m-%d")

# =========================
# CALIBRATION (CRITICAL FIX)
# =========================
def calibrate(p):
    return 0.5 + (p - 0.5) * 1.75

# =========================
# EV (REAL MATHEMATICAL)
# =========================
def ev(prob, odds):
    if not odds:
        return 0
    p = calibrate(prob)
    return (p * odds) - 1

# =========================
# RATING SYSTEM FIXED
# =========================
def rating(ev):
    if ev > 0.08:
        return "🟢 STRONG"
    elif ev > 0.03:
        return "🟠 MEDIUM"
    return "🔴 PASS"

# =========================
# KELLY CRITERION
# =========================
def kelly(prob, odds):
    if not odds:
        return 0
    p = calibrate(prob)
    b = odds - 1
    q = 1 - p
    return max(0, (b*p - q)/b)

# =========================
# GAMES
# =========================
def get_games():
    r = requests.get(
        "https://statsapi.mlb.com/api/v1/schedule",
        params={"sportId":1,"date":get_us_date(),"hydrate":"probablePitcher"}
    ).json()

    games = []

    for d in r.get("dates",[]):
        for g in d.get("games",[]):

            status = safe(g,["status","detailedState"],"").lower()
            if status in ["final","completed","in progress","live"]:
                continue

            games.append({
                "home": g["teams"]["home"]["team"]["name"],
                "away": g["teams"]["away"]["team"]["name"],
                "hp": safe(g,["teams","home","probablePitcher","fullName"],"TBD"),
                "ap": safe(g,["teams","away","probablePitcher","fullName"],"TBD"),
            })

    return games

# =========================
# SIMPLE BUT STABLE MODEL
# =========================
def model(home, away, p_diff):

    edge = (home["off"] - away["off"]) + (home["bull"] - away["bull"]) + p_diff

    prob = sigmoid(edge)

    total = 8.9 + (home["off"] - away["off"]) * 1.1 - p_diff * 0.8

    home_runs = total/2 + edge*0.4
    away_runs = total - home_runs

    return prob, total, home_runs, away_runs

# =========================
# TEAM STRENGTH
# =========================
def team(name):
    return {
        "off": 4.3 + (hash(name) % 20)/100,
        "bull": 4.2 + (hash(name[::-1]) % 20)/100
    }

def pitcher_score(name):
    if name == "TBD":
        return 0
    return (hash(name) % 100)/100 - 0.5

# =========================
# ODDS
# =========================
def get_odds():
    r = requests.get(
        "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/",
        params={
            "apiKey":ODDS_API_KEY,
            "regions":"us,au",
            "markets":"h2h,totals",
            "oddsFormat":"decimal"
        }
    )
    return r.json() if r.status_code==200 else []

def match(game, odds):
    for o in odds:
        if game["home"] in o.get("home_team","") and game["away"] in o.get("away_team",""):
            return o
    return None

def extract_ml(o, home, away):
    try:
        for b in o["bookmakers"]:
            for m in b["markets"]:
                if m["key"] == "h2h":
                    h = next(x["price"] for x in m["outcomes"] if x["name"] == home)
                    a = next(x["price"] for x in m["outcomes"] if x["name"] == away)
                    return h,a
    except:
        pass
    return None,None

# =========================
# TOTAL EV (FIXED)
# =========================
def total_ev(model_total, market_total):
    if not market_total:
        return 0
    return (model_total - market_total) * 0.15

# =========================
# TRACKER
# =========================
def init():
    if "tracker" not in st.session_state:
        st.session_state.tracker=[]

def add():
    st.session_state.tracker.append({
        "id":str(uuid.uuid4()),
        "Date":datetime.now().strftime("%Y-%m-%d"),
        "Match":"",
        "Market":"",
        "Selection":"",
        "Bookmaker":"",
        "Odds":0.0,
        "Stake":0.0,
        "Status":"PENDING",
        "P/L":0.0
    })

def delete(i):
    st.session_state.tracker=[x for x in st.session_state.tracker if x["id"]!=i]

# =========================
# APP
# =========================
st.title("⚾ MLB Engine V42 PRO")

init()

games = get_games()
odds = get_odds()

rows = []

for g in games:

    ht = team(g["home"])
    at = team(g["away"])

    p_diff = pitcher_score(g["hp"]) - pitcher_score(g["ap"])

    prob,total,hr,ar = model(ht,at,p_diff)

    o = match(g,odds)

    home_odds, away_odds = (None,None)
    market_total = None

    if o:
        home_odds, away_odds = extract_ml(o,g["home"],g["away"])

        try:
            for b in o["bookmakers"]:
                for m in b["markets"]:
                    if m["key"] == "totals":
                        market_total = m["outcomes"][0]["point"]
        except:
            pass

    home_ev = ev(prob,home_odds)
    away_ev = ev(1-prob,away_odds)

    tot_ev = total_ev(total,market_total)

    rows.append({
        "Game": f"{g['away']} @ {g['home']}",
        "Pitchers": f"{g['ap']} vs {g['hp']}",

        "Win %": round(prob*100,1),

        "ML Pick": g["home"] if prob>0.5 else g["away"],

        "Home EV": round(home_ev*100,2),
        "Away EV": round(away_ev*100,2),

        "Total": round(total,2),
        "Market Total": market_total,
        "Total EV": round(tot_ev,2),

        "Home Runs": round(hr,2),
        "Away Runs": round(ar,2),

        "Rating": rating(abs(home_ev))
    })

df = pd.DataFrame(rows)

st.subheader("📊 Predictions")
st.dataframe(df, use_container_width=True)

# =========================
# TRACKER (RESTORED FULL)
# =========================
st.subheader("🪵 Tracker")

if st.button("➕ Add Bet"):
    add()

cols = st.columns(9)
cols[0].write("Date")
cols[1].write("Match")
cols[2].write("Market")
cols[3].write("Selection")
cols[4].write("Book")
cols[5].write("Odds")
cols[6].write("Stake")
cols[7].write("Status")
cols[8].write("P/L")

for b in st.session_state.tracker:

    c = st.columns(10)

    b["Date"] = c[0].text_input("", b["Date"], key=b["id"]+"_d")
    b["Match"] = c[1].text_input("", b["Match"], key=b["id"]+"_m")
    b["Market"] = c[2].text_input("", b["Market"], key=b["id"]+"_mk")
    b["Selection"] = c[3].text_input("", b["Selection"], key=b["id"]+"_s")
    b["Bookmaker"] = c[4].text_input("", b["Bookmaker"], key=b["id"]+"_b")
    b["Odds"] = c[5].number_input("", value=float(b["Odds"]), key=b["id"]+"_o")
    b["Stake"] = c[6].number_input("", value=float(b["Stake"]), key=b["id"]+"_st")

    b["Status"] = c[7].selectbox("", ["PENDING","WIN","LOSS","PUSH"], key=b["id"]+"_r")

    if b["Status"] == "WIN":
        b["P/L"] = round((b["Odds"]-1)*b["Stake"],2)
    elif b["Status"] == "LOSS":
        b["P/L"] = -b["Stake"]
    else:
        b["P/L"] = 0

    c[8].write(b["P/L"])

    if c[9].button("❌", key=b["id"]):
        delete(b["id"])
        st.rerun()
