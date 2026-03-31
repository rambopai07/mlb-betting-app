import streamlit as st
import requests
import pandas as pd
import math

st.set_page_config(page_title="MLB Betting Engine V15", layout="wide")

API_KEY = "0d678e13097a84442df1e953f8fcaf95"

# ------------------ TEAM MAPPING (CRITICAL FIX) ------------------ #

TEAM_ALIASES = {
    "arizona diamondbacks": ["diamondbacks", "dbacks", "arizona"],
    "atlanta braves": ["braves", "atlanta"],
    "baltimore orioles": ["orioles", "baltimore"],
    "boston red sox": ["red sox", "boston"],
    "chicago cubs": ["cubs", "chicago cubs"],
    "chicago white sox": ["white sox", "whitesox"],
    "cincinnati reds": ["reds", "cincinnati"],
    "cleveland guardians": ["guardians", "cleveland indians", "cleveland"],
    "colorado rockies": ["rockies", "colorado"],
    "detroit tigers": ["tigers", "detroit"],
    "houston astros": ["astros", "houston"],
    "kansas city royals": ["royals", "kansas city"],
    "los angeles angels": ["angels", "la angels", "anaheim"],
    "los angeles dodgers": ["dodgers", "la dodgers"],
    "miami marlins": ["marlins", "miami"],
    "milwaukee brewers": ["brewers", "milwaukee"],
    "minnesota twins": ["twins", "minnesota"],
    "new york mets": ["mets", "ny mets"],
    "new york yankees": ["yankees", "ny yankees"],
    "oakland athletics": ["athletics", "a's", "oakland"],
    "philadelphia phillies": ["phillies", "philly"],
    "pittsburgh pirates": ["pirates", "pittsburgh"],
    "san diego padres": ["padres", "san diego"],
    "san francisco giants": ["giants", "sf giants", "san francisco"],
    "seattle mariners": ["mariners", "seattle"],
    "st louis cardinals": ["cardinals", "stl", "st louis"],
    "tampa bay rays": ["rays", "tampa bay"],
    "texas rangers": ["rangers", "texas"],
    "toronto blue jays": ["blue jays", "toronto"],
    "washington nationals": ["nationals", "nats", "washington"]
}

# ------------------ HELPERS ------------------ #

def normalize(name):
    return "".join(c for c in (name or "").lower() if c.isalnum())

def team_key(name):
    n = normalize(name)
    for full, aliases in TEAM_ALIASES.items():
        if n == normalize(full):
            return full
        for a in aliases:
            if n == normalize(a):
                return full
    return n

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

# ------------------ DATA ------------------ #

def get_schedule():
    return requests.get("https://statsapi.mlb.com/api/v1/schedule?sportId=1").json()

def get_odds():
    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/?apiKey={API_KEY}&regions=au&markets=h2h"
    try:
        return requests.get(url).json()
    except:
        return []

def get_team_stats():
    data = requests.get("https://statsapi.mlb.com/api/v1/teams?sportId=1").json()

    stats = {}
    for t in data.get("teams", []):
        stats[t["name"]] = {
            "runs": 4.5,
            "bullpen": 4.2
        }
    return stats

def get_pitcher_era(name):
    if not name:
        return 4.5

    try:
        r = requests.get(f"https://statsapi.mlb.com/api/v1/people/search?names={name}").json()
        people = r.get("people", [])
        if not people:
            return 4.5

        pid = people[0]["id"]

        s = requests.get(f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=season").json()
        splits = s.get("stats", [{}])[0].get("splits", [])
        if not splits:
            return 4.5

        return float(splits[0]["stat"].get("era", 4.5))

    except:
        return 4.5

# ------------------ ODDS MATCHING (FIXED PRO VERSION) ------------------ #

def match_odds(game, odds_data):

    home = team_key(game["teams"]["home"]["team"]["name"])
    away = team_key(game["teams"]["away"]["team"]["name"])

    for o in odds_data:

        o_home = team_key(o.get("home_team"))
        o_away = team_key(o.get("away_team"))

        # 🔥 strict alias match first
        if home == o_home and away == o_away:
            return o

        # 🔥 fallback fuzzy containment
        if home in o_home and away in o_away:
            return o

        if o_home in home and o_away in away:
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

st.title("⚾ MLB Betting Engine V15 (Pro Team Mapping)")

schedule = get_schedule()
odds_data = get_odds()
team_stats = get_team_stats()

st.write("Games:", len(schedule.get("dates", [])))
st.write("Odds:", len(odds_data))

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
            books = odds.get("bookmakers", [])
            if not books:
                continue

            markets = books[0].get("markets", [])
            h2h = next((m for m in markets if m["key"] == "h2h"), None)
            if not h2h:
                continue

            home_price = next((x["price"] for x in h2h["outcomes"] if team_key(x["name"]) == team_key(home)), None)
            away_price = next((x["price"] for x in h2h["outcomes"] if team_key(x["name"]) == team_key(away)), None)

            if home_price is None or away_price is None:
                continue

        except:
            continue

        home_odds = american_to_decimal(home_price)
        away_odds = american_to_decimal(away_price)

        home_ev = calculate_ev(prob, home_odds)
        away_ev = calculate_ev(1 - prob, away_odds)

        best = home if home_ev > away_ev else away
        best_ev = max(home_ev, away_ev)

        if best_ev < 0.03:
            continue

        results.append({
            "Game": f"{away} @ {home}",
            "Best Bet": best,
            "EV %": round(best_ev * 100, 2),
            "Win %": round(prob * 100, 2),
            "Spread": round(spread, 2),
            "Total": round(total, 2)
        })

df = pd.DataFrame(results)

if df.empty:
    st.warning("No matches found — check odds provider coverage or API timing.")
else:
    df = df.sort_values("EV %", ascending=False)
    st.dataframe(df, use_container_width=True)
