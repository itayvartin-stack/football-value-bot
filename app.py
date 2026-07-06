import os
import math
from datetime import datetime

import requests
from flask import Flask, render_template_string

app = Flask(__name__)

API_KEY = os.environ.get("API_FOOTBALL_KEY", "")
BASE_URL = "https://v3.football.api-sports.io"


def clamp(value, min_value=1, max_value=99):
    return max(min_value, min(max_value, value))


def api_get(path, params=None):
    if not API_KEY:
        return {"error": "missing_api_key", "response": []}
    headers = {"x-apisports-key": API_KEY}
    try:
        r = requests.get(f"{BASE_URL}{path}", headers=headers, params=params or {}, timeout=12)
        if r.status_code != 200:
            return {"error": f"api_status_{r.status_code}", "response": []}
        return r.json()
    except Exception as e:
        return {"error": str(e), "response": []}


def fixture_stats(fixture_id):
    data = api_get("/fixtures/statistics", {"fixture": fixture_id})
    return data.get("response", []) or []


def get_stat(team_stats, name):
    for item in team_stats:
        if str(item.get("type", "")).lower() == name.lower():
            val = item.get("value")
            if val is None:
                return 0
            if isinstance(val, str) and "%" in val:
                val = val.replace("%", "")
            try:
                return float(val)
            except Exception:
                return 0
    return 0


def analyze_game(game):
    fixture = game.get("fixture", {})
    teams = game.get("teams", {})
    goals = game.get("goals", {})
    league = game.get("league", {})
    status = fixture.get("status", {})
    minute = status.get("elapsed") or 0
    fixture_id = fixture.get("id")

    home = teams.get("home", {}).get("name", "Home")
    away = teams.get("away", {}).get("name", "Away")
    home_goals = goals.get("home") or 0
    away_goals = goals.get("away") or 0

    stats = fixture_stats(fixture_id) if fixture_id else []
    home_stats = stats[0].get("statistics", []) if len(stats) > 0 else []
    away_stats = stats[1].get("statistics", []) if len(stats) > 1 else []

    shots_on = get_stat(home_stats, "Shots on Goal") + get_stat(away_stats, "Shots on Goal")
    shots_total = get_stat(home_stats, "Total Shots") + get_stat(away_stats, "Total Shots")
    corners = get_stat(home_stats, "Corner Kicks") + get_stat(away_stats, "Corner Kicks")
    possession_home = get_stat(home_stats, "Ball Possession")
    possession_away = get_stat(away_stats, "Ball Possession")
    red_cards = get_stat(home_stats, "Red Cards") + get_stat(away_stats, "Red Cards")

    remaining_half = max(0, 45 - minute) if minute <= 45 else 0
    remaining_game = max(0, 90 - minute)

    attack_score = shots_on * 10 + shots_total * 2.2 + corners * 3.5
    if red_cards:
        attack_score += 5

    goal_half = clamp(8 + attack_score * (remaining_half / 45)) if remaining_half else 3
    goal_game = clamp(12 + attack_score * (remaining_game / 60)) if remaining_game else 2

    home_pressure = get_stat(home_stats, "Shots on Goal") * 11 + get_stat(home_stats, "Total Shots") * 2 + get_stat(home_stats, "Corner Kicks") * 3 + possession_home * 0.15 + home_goals * 12
    away_pressure = get_stat(away_stats, "Shots on Goal") * 11 + get_stat(away_stats, "Total Shots") * 2 + get_stat(away_stats, "Corner Kicks") * 3 + possession_away * 0.15 + away_goals * 12
    total_pressure = max(1, home_pressure + away_pressure)

    home_win = clamp((home_pressure / total_pressure) * 70 + (home_goals - away_goals) * 10)
    away_win = clamp((away_pressure / total_pressure) * 70 + (away_goals - home_goals) * 10)
    draw = clamp(100 - abs(home_win - away_win) - abs(home_goals - away_goals) * 15, 5, 60)

    corners_over = clamp(15 + corners * 8 + (shots_total * 0.8))

    if goal_half >= 70 or goal_game >= 82:
        signal = "🔥 חם"
    elif goal_half >= 50 or goal_game >= 65:
        signal = "🟡 לעקוב"
    else:
        signal = "⚪ רגוע"

    explanation = f"המודל מחשב לפי {int(shots_total)} בעיטות, {int(shots_on)} למסגרת, {int(corners)} קרנות, דקה {minute} ותוצאה {home_goals}-{away_goals}."

    return {
        "league": league.get("name", ""),
        "country": league.get("country", ""),
        "home": home,
        "away": away,
        "minute": minute,
        "score": f"{home_goals}-{away_goals}",
        "shots_total": int(shots_total),
        "shots_on": int(shots_on),
        "corners": int(corners),
        "goal_half": round(goal_half),
        "goal_game": round(goal_game),
        "home_win": round(home_win),
        "draw": round(draw),
        "away_win": round(away_win),
        "corners_over": round(corners_over),
        "signal": signal,
        "explanation": explanation,
    }


def get_live_games():
    data = api_get("/fixtures", {"live": "all"})
    games = data.get("response", []) or []
    analyzed = []
    for game in games[:25]:
        analyzed.append(analyze_game(game))
    analyzed.sort(key=lambda x: (x["goal_game"], x["goal_half"]), reverse=True)
    return analyzed, data.get("error")


HTML = """
<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="45">
  <title>Football Value Bot</title>
  <style>
    body{margin:0;background:#07111f;color:#e5eefb;font-family:Arial,Helvetica,sans-serif}
    .wrap{max-width:980px;margin:auto;padding:24px 14px}
    h1{color:#22c55e;text-align:center;font-size:34px;margin:18px 0 8px}
    .sub{text-align:center;color:#a9b4c7;font-size:16px;margin-bottom:22px;line-height:1.5}
    .top{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:18px}
    .stat{background:#111c2f;border:1px solid #24324b;border-radius:14px;padding:14px;text-align:center}
    .stat b{display:block;color:#22c55e;font-size:24px}
    .card{background:#101827;border:1px solid #26344d;border-radius:18px;padding:16px;margin:14px 0;box-shadow:0 8px 20px rgba(0,0,0,.25)}
    .teams{font-size:20px;font-weight:700;margin-bottom:6px;color:#fff}
    .meta{color:#a9b4c7;font-size:14px;margin-bottom:12px}
    .signal{display:inline-block;background:#172a45;border:1px solid #2f4770;border-radius:999px;padding:7px 12px;margin-bottom:12px}
    .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
    .box{background:#0b1322;border:1px solid #21304a;border-radius:12px;padding:12px}
    .label{color:#a9b4c7;font-size:13px}.val{font-size:24px;font-weight:800;color:#38bdf8;margin-top:4px}
    .good{color:#22c55e}.warn{color:#facc15}.bad{color:#f87171}
    .exp{margin-top:12px;color:#cbd5e1;line-height:1.5;font-size:14px}
    .empty{background:#101827;border:1px solid #26344d;border-radius:18px;padding:26px;text-align:center;color:#cbd5e1;font-size:20px;margin-top:20px}
    .footer{text-align:center;color:#64748b;margin-top:28px;font-size:13px}
    @media(max-width:650px){.top{grid-template-columns:1fr}.grid{grid-template-columns:1fr}h1{font-size:30px}.teams{font-size:18px}}
  </style>
</head>
<body>
<div class="wrap">
  <h1>Football Value Bot ⚽</h1>
  <div class="sub">גרסת Single File V2 · נתוני לייב מ־API-Football · ניתוח הסתברויות בסיסי בלבד, לא הבטחת רווח.</div>
  <div class="top">
    <div class="stat"><b>{{ games|length }}</b>משחקים בלייב</div>
    <div class="stat"><b>{{ hot }}</b>סיגנלים חמים</div>
    <div class="stat"><b>{{ updated }}</b>עדכון אחרון</div>
  </div>
  {% if error %}<div class="empty">שגיאת API: {{ error }}</div>{% endif %}
  {% if not games %}
    <div class="empty">אין משחקים בלייב כרגע או שאין סטטיסטיקות זמינות.</div>
  {% endif %}
  {% for g in games %}
    <div class="card">
      <div class="signal">{{ g.signal }}</div>
      <div class="teams">{{ g.home }} נגד {{ g.away }}</div>
      <div class="meta">{{ g.country }} · {{ g.league }} · דקה {{ g.minute }} · תוצאה {{ g.score }}</div>
      <div class="grid">
        <div class="box"><div class="label">גול עד סוף מחצית</div><div class="val good">{{ g.goal_half }}%</div></div>
        <div class="box"><div class="label">גול עד סוף משחק</div><div class="val good">{{ g.goal_game }}%</div></div>
        <div class="box"><div class="label">ניצחון בית</div><div class="val">{{ g.home_win }}%</div></div>
        <div class="box"><div class="label">תיקו</div><div class="val warn">{{ g.draw }}%</div></div>
        <div class="box"><div class="label">ניצחון חוץ</div><div class="val">{{ g.away_win }}%</div></div>
        <div class="box"><div class="label">קצב קרנות גבוה</div><div class="val">{{ g.corners_over }}%</div></div>
      </div>
      <div class="exp">📊 {{ g.explanation }}<br>בעיטות: {{ g.shots_total }} · למסגרת: {{ g.shots_on }} · קרנות: {{ g.corners }}</div>
    </div>
  {% endfor %}
  <div class="footer">האתר מתרענן כל 45 שניות. לשימוש אישי וניתוח בלבד.</div>
</div>
</body>
</html>
"""


@app.route("/")
def index():
    games, error = get_live_games()
    hot = sum(1 for g in games if "חם" in g["signal"])
    return render_template_string(HTML, games=games, error=error, hot=hot, updated=datetime.now().strftime("%H:%M"))


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
