import streamlit as st
import requests
import pandas as pd
import math
import uuid
from datetime import datetime, timedelta

st.set_page_config(page_title="MLB Betting Engine V38", layout="wide")

ODDS_API_KEY = "0d678e13097a84442df1e953f8fcaf95"

LEAGUE_ERA = 4.35
LEAGUE_K9 = 8.7
LEAGUE_WHIP = 1.30

# =========================
# HELPERS
# =========================
def sigmoid(x): return 1/(1+math.exp(-x))
def clamp(x,a,b): return max(a,min(b,x))

def safe(d,path,default=None):
    try:
        for p in path: d=d[p]
        return d
    except: return default

# =========================
# DATE FIX
# =========================
def get_us_date():
    return (datetime.utcnow()-timedelta(hours=6)).strftime("%Y-%m-%d")

# =========================
# GAMES
# =========================
def get_games():
    r = requests.get(
        "https://statsapi.mlb.com/api/v1/schedule",
        params={"sportId":1,"date":get_us_date(),"hydrate":"probablePitcher"}
    ).json()

    games=[]
    for d in r.get("dates",[]):
        for g in d.get("games",[]):

            status = safe(g,["status","detailedState"],"").lower()
            if status in ["final","in progress","live","completed"]:
                continue

            games.append({
                "home": g["teams"]["home"]["team"]["name"],
                "away": g["teams"]["away"]["team"]["name"],
                "hp_id": safe(g,["teams","home","probablePitcher","id"]),
                "ap_id": safe(g,["teams","away","probablePitcher","id"]),
                "hp_name": safe(g,["teams","home","probablePitcher","fullName"],"TBD"),
                "ap_name": safe(g,["teams","away","probablePitcher","fullName"],"TBD"),
            })
    return games

# =========================
# PITCHERS
# =========================
def get_pitcher_stats(pid):
    if not pid:
        return {"era":LEAGUE_ERA,"whip":LEAGUE_WHIP,"k9":LEAGUE_K9}

    r = requests.get(
        f"https://statsapi.mlb.com/api/v1/people/{pid}/stats",
        params={"stats":"season"}
    ).json()

    stat = safe(r,["stats",0,"splits",0,"stat"],{})

    return {
        "era": float(stat.get("era",LEAGUE_ERA) or LEAGUE_ERA),
        "whip": float(stat.get("whip",LEAGUE_WHIP) or LEAGUE_WHIP),
        "k9": float(stat.get("strikeoutsPer9Inn",LEAGUE_K9) or LEAGUE_K9)
    }

def pitcher_score(p):
    return ((LEAGUE_ERA-p["era"])*0.5 +
            (p["k9"]-LEAGUE_K9)*0.3 +
            (LEAGUE_WHIP-p["whip"])*0.2)

# =========================
# TEAMS
# =========================
def get_teams():
    data = requests.get("https://statsapi.mlb.com/api/v1/teams?sportId=1").json()
    teams={}
    for t in data.get("teams",[]):
        teams[t["name"]] = {
            "off":4.3+(hash(t["name"])%30)/100,
            "bull":4.2+(hash(t["name"][::-1])%25)/100
        }
    return teams

# =========================
# ODDS FIXED
# =========================
def get_odds():
    r = requests.get(
        "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/",
        params={
            "apiKey":ODDS_API_KEY,
            "regions":"us,au",
            "markets":"h2h,totals,spreads",
            "oddsFormat":"decimal"
        }
    )
    return r.json() if r.status_code==200 else []

def extract_ml_odds(odds_match, home, away):
    try:
        outcomes = odds_match["bookmakers"][0]["markets"][0]["outcomes"]
        home_odds = next(o["price"] for o in outcomes if o["name"] == home)
        away_odds = next(o["price"] for o in outcomes if o["name"] == away)
        return home_odds, away_odds
    except:
        return None, None

def extract_total_spread(odds_match):
    try:
        markets = odds_match["bookmakers"][0]["markets"]
        total = next(m for m in markets if m["key"]=="totals")
        spread = next(m for m in markets if m["key"]=="spreads")
        return total["outcomes"][0]["point"], spread["outcomes"][0]["point"]
    except:
        return None, None

def match_odds(game, odds):
    for o in odds:
        if game["home"] in o.get("home_team","") and game["away"] in o.get("away_team",""):
            return o
    return None

# =========================
# MODEL FIXED
# =========================
def model(ht,at,p_diff):

    off = ht["off"]-at["off"]
    bull = ht["bull"]-at["bull"]

    edge = (0.30*off + 0.25*p_diff + 0.20*bull + 0.25*0.15)

    prob = sigmoid(edge)
    total = 8.6 + (off*2.2) - (p_diff*1.3)

    home_runs = (total/2)+(edge*0.6)
    away_runs = total-home_runs

    home_runs = clamp(home_runs,3.0,7.0)
    away_runs = clamp(away_runs,3.0,7.0)

    spread = edge*2.0

    return prob,total,spread,home_runs,away_runs

def implied_prob(o): return 1/o if o else 0
def calc_ev(p,o): return p - implied_prob(o) if o else 0

# =========================
# TRACKER FIXED
# =========================
def init_tracker():
    if "tracker" not in st.session_state:
        st.session_state.tracker=[]

def add_blank_bet():
    st.session_state.tracker.append({
        "id":str(uuid.uuid4()),
        "Date":datetime.now().strftime("%Y-%m-%d"),
        "Match":"","Market":"","Selection":"",
        "Bookmaker":"","Odds":0.0,"Stake":0.0,
        "Status":"PENDING","P/L":0.0
    })

def delete_bet(bid):
    st.session_state.tracker=[b for b in st.session_state.tracker if b["id"]!=bid]

# =========================
# APP
# =========================
st.title("⚾ MLB Betting Engine V38 (STABLE)")

init_tracker()

games = get_games()
teams = get_teams()
odds = get_odds()

rows=[]

for g in games:

    hp = get_pitcher_stats(g["hp_id"])
    ap = get_pitcher_stats(g["ap_id"])

    p_diff = pitcher_score(hp)-pitcher_score(ap)

    ht = teams.get(g["home"],{"off":4.3,"bull":4.2})
    at = teams.get(g["away"],{"off":4.3,"bull":4.2})

    prob,total,spread,home_tt,away_tt = model(ht,at,p_diff)

    odds_match = match_odds(g,odds)

    home_odds, away_odds = extract_ml_odds(odds_match,g["home"],g["away"]) if odds_match else (None,None)

    ev_home = calc_ev(prob, home_odds)
    ev_away = calc_ev(1-prob, away_odds)

    rows.append({
        "Game":f"{g['away']} @ {g['home']}",
        "Pitchers":f"{g['ap_name']} vs {g['hp_name']}",
        "Win %":round(prob*100,1),
        "Home EV %":round(ev_home*100,2) if ev_home else None,
        "Away EV %":round(ev_away*100,2) if ev_away else None,
        "Home TT":round(home_tt,2),
        "Away TT":round(away_tt,2)
    })

df=pd.DataFrame(rows)

st.subheader("📊 Betting Board")
st.dataframe(df,use_container_width=True)

# =========================
# TRACKER UI
# =========================
st.subheader("🪵 Bet Tracker")

header = st.columns(10)
header[0].write("Date")
header[1].write("Match")
header[2].write("Market")
header[3].write("Selection")
header[4].write("Book")
header[5].write("Odds")
header[6].write("Stake")
header[7].write("Status")
header[8].write("P/L")

if st.button("➕ Add Bet"):
    add_blank_bet()

for b in st.session_state.tracker:

    cols = st.columns(10)

    b["Date"] = cols[0].text_input("",b["Date"],key=f"d_{b['id']}")
    b["Match"] = cols[1].text_input("",b["Match"],key=f"m_{b['id']}")
    b["Market"] = cols[2].text_input("",b["Market"],key=f"mk_{b['id']}")
    b["Selection"] = cols[3].text_input("",b["Selection"],key=f"s_{b['id']}")
    b["Bookmaker"] = cols[4].text_input("",b["Bookmaker"],key=f"bk_{b['id']}")
    b["Odds"] = cols[5].number_input("",value=float(b["Odds"]),key=f"o_{b['id']}")
    b["Stake"] = cols[6].number_input("",value=float(b["Stake"]),key=f"st_{b['id']}")

    b["Status"] = cols[7].selectbox("",["PENDING","WIN","LOSS","PUSH"],key=f"res_{b['id']}")

    if b["Status"]=="WIN":
        b["P/L"] = round((b["Odds"]-1)*b["Stake"],2)
    elif b["Status"]=="LOSS":
        b["P/L"] = -b["Stake"]
    else:
        b["P/L"] = 0.0

    cols[8].write(f"${b['P/L']}")

    if cols[9].button("❌",key=f"del_{b['id']}"):
        delete_bet(b["id"])
        st.rerun()
