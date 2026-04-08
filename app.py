import numpy as np
import pandas as pd
import requests
from datetime import datetime
import os

# ==============================
# CONFIG
# ==============================

ODDS_API_KEY = "0d678e13097a84442df1e953f8fcaf95"  # get from the-odds-api.com
BETS_FILE = "bets.csv"

# ==============================
# UTILS
# ==============================

def logistic(x):
    return 1 / (1 + np.exp(-3.8 * x))

def implied_prob(odds):
    return 1 / odds

# ==============================
# TRACKER (PERSISTENT)
# ==============================

def load_bets():
    if os.path.exists(BETS_FILE):
        return pd.read_csv(BETS_FILE)
    return pd.DataFrame(columns=["Game","Bet","Odds","Stake","Result"])

def save_bet(row):
    df = load_bets()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(BETS_FILE, index=False)

# ==============================
# REAL MLB SCHEDULE + PITCHERS
# ==============================

def get_today_games():
    today = datetime.utcnow().strftime("%Y-%m-%d")

    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher"
    data = requests.get(url).json()

    games = []

    for d in data.get("dates", []):
        for g in d["games"]:
            games.append({
                "home": g["teams"]["home"]["team"]["name"],
                "away": g["teams"]["away"]["team"]["name"],
                "home_id": g["teams"]["home"]["team"]["id"],
                "away_id": g["teams"]["away"]["team"]["id"],
                "home_pitcher": g["teams"]["home"].get("probablePitcher", {}).get("id"),
                "away_pitcher": g["teams"]["away"].get("probablePitcher", {}).get("id")
            })

    return games

# ==============================
# REAL PITCHER STATS (MLB API)
# ==============================

def get_pitcher_stats(pitcher_id):

    if pitcher_id is None:
        return default_pitcher()

    url = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats?stats=season&group=pitching"
    data = requests.get(url).json()

    try:
        stat = data["stats"][0]["splits"][0]["stat"]

        strikeouts = float(stat.get("strikeOuts", 0))
        walks = float(stat.get("baseOnBalls", 1))

        return {
            "xFIP": float(stat.get("era", 4.20)),   # proxy
            "xERA": float(stat.get("era", 4.20)),
            "K_BB": strikeouts / max(walks,1),
            "SIERA": float(stat.get("era", 4.20)),
            "barrel": 8.0,      # not in MLB API
            "hard_hit": 35.0,   # not in MLB API
            "fatigue": 0.5
        }

    except:
        return default_pitcher()

def default_pitcher():
    return {
        "xFIP": 4.20,
        "xERA": 4.20,
        "K_BB": 2.0,
        "SIERA": 4.20,
        "barrel": 8.0,
        "hard_hit": 35.0,
        "fatigue": 0.5
    }

# ==============================
# REAL TEAM OFFENSE (MLB API)
# ==============================

def get_team_offense(team_id):

    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=season"
    data = requests.get(url).json()

    try:
        stat = data["stats"][0]["splits"][0]["stat"]

        return {
            "wRC_split": float(stat.get("runs", 700)) / 10,
            "wRC14": float(stat.get("runs", 700)) / 10,
            "ISO": float(stat.get("slugging", 0.400)),
            "OBP": float(stat.get("obp", 0.320)),
            "K_rate": float(stat.get("strikeOuts", 1000)) / 50
        }

    except:
        return {
            "wRC_split": 100,
            "wRC14": 100,
            "ISO": 0.170,
            "OBP": 0.320,
            "K_rate": 22
        }

# ==============================
# BUILD TEAM OBJECT
# ==============================

def build_team(team_id, pitcher_id, is_home):

    return {
        "pitcher": get_pitcher_stats(pitcher_id),

        "bullpen": {
            "xFIP14": 4.20,
            "xFIP": 4.20,
            "fatigue": 0.5,
            "leverage": 0.5
        },

        "offense": get_team_offense(team_id),

        "defense": {
            "DRS": 0,
            "framing": 0
        },

        "env": {
            "park": 1.0,
            "wind": 0.0,
            "temp": 1.0,
            "humidity": 1.0
        },

        "situational": {
            "home": 1 if is_home else 0,
            "rest": 0.5,
            "travel": 0.5,
            "lineup": 1.0
        },

        "market": {
            "sharp": 0.5,
            "public": 0.5
        }
    }

# ==============================
# ODDS (REAL)
# ==============================

def get_odds():

    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/?apiKey={ODDS_API_KEY}&regions=us&markets=h2h"
    data = requests.get(url).json()

    odds_map = {}

    for game in data:
        home = game["home_team"]

        for book in game["bookmakers"]:
            for market in book["markets"]:
                if market["key"] == "h2h":
                    for outcome in market["outcomes"]:
                        if outcome["name"] == home:
                            odds_map[home] = outcome["price"]

    return odds_map

# ==============================
# MODEL
# ==============================

class MLBModel:

    def pitcher_score(self, p):
        return (
            0.28 * (-p["xFIP"]) +
            0.22 * (-p["xERA"]) +
            0.18 * p["K_BB"] +
            0.12 * (-p["SIERA"]) +
            0.10 * (-p["barrel"]) +
            0.05 * (-p["hard_hit"]) +
            0.05 * p["fatigue"]
        )

    def bullpen_score(self, b):
        return (
            0.40 * (-b["xFIP14"]) +
            0.25 * (-b["xFIP"]) +
            0.20 * b["fatigue"] +
            0.15 * b["leverage"]
        )

    def offense_score(self, o):
        return (
            0.35 * o["wRC_split"] +
            0.25 * o["wRC14"] +
            0.15 * o["ISO"] +
            0.15 * o["OBP"] +
            0.10 * (-o["K_rate"])
        )

    def defense_score(self, d):
        return d["DRS"] + d["framing"]

    def env_score(self, e):
        return e["park"] + e["wind"] + e["temp"] + e["humidity"]

    def situational_score(self, s):
        return s["home"] + s["rest"] - s["travel"] + s["lineup"]

    def market_score(self, m):
        return (0.6 * m["sharp"]) - (0.4 * m["public"])

    def team_rating(self, team):
        return (
            0.32 * self.pitcher_score(team["pitcher"]) +
            0.18 * self.bullpen_score(team["bullpen"]) +
            0.20 * self.offense_score(team["offense"]) +
            0.05 * self.defense_score(team["defense"]) +
            0.08 * self.env_score(team["env"]) +
            0.07 * self.situational_score(team["situational"]) +
            0.10 * self.market_score(team["market"])
        )

    def predict(self, home, away, odds_home):

        r_home = self.team_rating(home)
        r_away = self.team_rating(away)

        diff = r_home - r_away
        prob = logistic(diff)

        implied = implied_prob(odds_home)
        edge = prob - implied

        return prob, edge

# ==============================
# MAIN EXECUTION
# ==============================

def run():

    model = MLBModel()

    print("Fetching games...")
    games = get_today_games()

    print("Fetching odds...")
    odds_map = get_odds()

    results = []

    for g in games:

        home = build_team(g["home_id"], g["home_pitcher"], True)
        away = build_team(g["away_id"], g["away_pitcher"], False)

        odds = odds_map.get(g["home"], 1.90)

        prob, edge = model.predict(home, away, odds)

        bet = None
        if edge > 0.06:
            bet = "HOME ML"
        elif edge < -0.06:
            bet = "AWAY ML"

        results.append({
            "Game": f'{g["away"]} @ {g["home"]}',
            "Win Prob %": round(prob * 100, 1),
            "Edge %": round(edge * 100, 1),
            "Odds": odds,
            "Bet": bet
        })

    df = pd.DataFrame(results)

    print("\n📊 ALL GAMES")
    print(df)

    value = df[df["Edge %"].abs() > 6]

    print("\n🔥 VALUE BETS")
    print(value)

    return df

# ==============================
# RUN
# ==============================

if __name__ == "__main__":
    run()
