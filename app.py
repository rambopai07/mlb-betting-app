import math

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def american_to_decimal(odds):
    if odds > 0:
        return 1 + (odds / 100)
    else:
        return 1 + (100 / abs(odds))

def calculate_ev(prob, odds_decimal):
    return (prob * odds_decimal) - 1

def clamp(value, min_val, max_val):
    return max(min_val, min(max_val, value))


# --- MODEL CORE ---
edge_score = (
    0.25 * offense_diff +
    0.25 * starting_pitcher_diff +
    0.15 * bullpen_diff +
    0.15 * team_form_diff +
    0.10 * park_factor +
    0.10 * home_advantage
)

# Convert to probability
win_prob = sigmoid(edge_score)

# Clamp probability
win_prob = clamp(win_prob, 0.05, 0.80)

# Convert odds
decimal_odds = american_to_decimal(market_odds)

# Calculate EV
ev = calculate_ev(win_prob, decimal_odds)

# Cap EV
ev = clamp(ev, -0.50, 0.25)

# Spread & totals
predicted_spread = clamp(edge_score * 3, -4.5, 4.5)
predicted_total = clamp(base_total + (offense_diff * 2), 6, 11)
