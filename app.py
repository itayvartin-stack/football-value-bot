import os
import math
import requests
from datetime import datetime
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

API_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()
BASE_URL = "https://v3.football.api-sports.io"


def api_get(path, params=None):
    if not API_KEY:
        return {"error": "Missing API_FOOTBALL_KEY", "response": []}
    headers = {"x-apisports-key": API_KEY}
    try:
        r = requests.get(BASE_URL + path, headers=headers, params=params or {}, timeout=15)
        if r.status_code != 200:
            return {"error": f"API status {r.status_code}: {r.text[:200]}", "response": []}
        return r.json()
    except Exception as e:
        return {"error": str(e), "response": []}


def safe_int(value, default=0):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("%", "").strip()
        return int(float(value))
    except Exception:
        return default


def get_stat(stats, team_side, stat_type):
    # stats format: [{team:{...}, statistics:[{type,value}]}]
    if len(stats) < 2:
        return 0
    idx = 0 if team_side == "home" else 1
    for item in stats[idx].get("statistics", []):
        if item.get("type") == stat_type:
            return safe_int(item.get("value"), 0)
    return 0


def probability_from_score(score):
    # smooth score into 5%-92%
    return round(max(5, min(92, 5 + (score * 1.35))), 1)


def analyze_match(fixture, stats):
    minute = safe_int(fixture.get("fixture", {}).get("status", {}).get("elapsed"), 0)
    goals_home = safe_int(fixture.get("goals", {}).get("home"), 0)
    goals_away = safe_int(fixture.get("goals", {}).get("away"), 0)
    total_goals = goals_home + goals_away

    h_shots = get_stat(stats, "home", "Total Shots")
    a_shots = get_stat(stats, "away", "Total Shots")
    h_on = get_stat(stats, "home", "Shots on Goal")
    a_on = get_stat(stats, "away", "Shots on Goal")
    h_corners = get_stat(stats, "home", "Corner Kicks")
    a_corners = get_stat(stats, "away", "Corner Kicks")
    h_red = get_stat(stats, "home", "Red Cards")
    a_red = get_stat(stats, "away", "Red Cards")
    h_yellow = get_stat(stats, "home", "Yellow Cards")
    a_yellow = get_stat(stats, "away", "Yellow Cards")
    h_pos = get_stat(stats, "home", "Ball Possession")
    a_pos = get_stat(stats, "away", "Ball Possession")

    shots = h_shots + a_shots
    on_target = h_on + a_on
    corners = h_corners + a_corners
    reds = h_red + a_red
    yellows = h_yellow + a_yellow

    # time factors
    remaining_half = max(0, 45 - minute) if minute <= 45 else max(0, 90 - minute)
    remaining_match = max(0, 90 - minute)

    pressure_score = (
        on_target * 8 +
        shots * 2.2 +
        corners * 3.2 +
        yellows * 0.8 +
        total_goals * 2
    )
    if reds:
        pressure_score += 4

    half_factor = max(0.15, remaining_half / 45) if minute <= 45 else 0.1
    match_factor = max(0.1, remaining_match / 90)

    goal_half = probability_from_score(pressure_score * half_factor)
    goal_match = probability_from_score(pressure_score * (0.55 + match_factor))

    # over/under rough estimates
    over_15 = probability_from_score((pressure_score * 0.85) + total_goals * 12)
    over_25 = probability_from_score((pressure_score * 0.55) + max(0, total_goals - 1) * 18)
    btts = probability_from_score((min(h_on + h_shots * 0.25, a_on + a_shots * 0.25) * 10) + total_goals * 4)

    # corners projection
    projected_corners = corners
    if minute > 0:
        projected_corners = round(corners / minute * 90, 1)
    corners_over_85 = max(5, min(90, round((projected_corners - 5.5) * 12, 1)))

    # 1X2 rough live pressure model
    home_power = h_on * 8 + h_shots * 2 + h_corners * 3 + h_pos * 0.15 + goals_home * 25 - h_red * 10
    away_power = a_on * 8 + a_shots * 2 + a_corners * 3 + a_pos * 0.15 + goals_away * 25 - a_red * 10
    diff = home_power - away_power
    home_win = round(max(5, min(85, 38 + diff * 0.9)), 1)
    away_win = round(max(5, min(85, 38 - diff * 0.9)), 1)
    draw = round(max(8, min(55, 100 - home_win - away_win)), 1)

    hot_score = max(goal_half, goal_match, over_15, corners_over_85)
    if hot_score >= 75:
        signal = "🔥 סיגנל חם"
    elif hot_score >= 60:
        signal = "🟡 לעקוב"
    else:
        signal = "⚪ רגוע"

    explanation = []
    if on_target >= 5:
        explanation.append("הרבה בעיטות למסגרת")
    if corners >= 7:
        explanation.append("הרבה קרנות")
    if shots >= 14:
        explanation.append("קצב בעיטות גבוה")
    if reds:
        explanation.append("יש כרטיס אדום שמשנה את המשחק")
    if not explanation:
        explanation.append("אין מספיק לחץ התקפי חריג כרגע")

    return {
        "minute": minute,
        "score": f"{goals_home}-{goals_away}",
        "stats": {
            "shots": shots,
            "on_target": on_target,
            "corners": corners,
            "yellow_cards": yellows,
            "red_cards": reds,
            "possession": f"{h_pos}% - {a_pos}%" if h_pos or a_pos else "לא זמין",
        },
        "markets": {
            "goal_half": goal_half,
            "goal_match": goal_match,
            "over_15": over_15,
            "over_25": over_25,
            "btts": btts,
            "corners_over_85": corners_over_85,
            "home_win": home_win,
            "draw": draw,
            "away_win": away_win,
        },
        "signal": signal,
        "hot_score": hot_score,
        "explanation": " · ".join(explanation),
    }


def load_live_matches():
    fixtures_data = api_get("/fixtures", {"live": "all"})
    if fixtures_data.get("error"):
        return [], fixtures_data.get("error")

    fixtures = fixtures_data.get("response", []) or []
    matches = []
    api_errors = []

    for f in fixtures[:25]:
        fixture_id = f.get("fixture", {}).get("id")
        stats_data = api_get("/fixtures/statistics", {"fixture": fixture_id}) if fixture_id else {"response": []}
        if stats_data.get("error"):
            api_errors.append(stats_data.get("error"))
        stats = stats_data.get("response", []) or []
        analysis = analyze_match(f, stats)
        matches.append({
            "fixture_id": fixture_id,
            "league": f.get("league", {}).get("name", "לא ידוע"),
            "country": f.get("league", {}).get("country", ""),
            "home": f.get("teams", {}).get("home", {}).get("name", "Home"),
            "away": f.get("teams", {}).get("away", {}).get("name", "Away"),
            "analysis": analysis,
        })

    matches.sort(key=lambda x: x["analysis"]["hot_score"], reverse=True)
    return matches, (api_errors[0] if api_errors and not matches else None)


HTML = """
<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="45">
  <title>Football Value Bot</title>
  <style>
    body{margin:0;background:#07111f;color:#e6edf7;font-family:Arial,Helvetica,sans-serif;padding:22px}
    .wrap{max-width:980px;margin:auto}.title{text-align:center;margin:18px 0 8px;color:#22c55e;font-size:42px;font-weight:900}
    .sub{text-align:center;color:#a8b3c7;font-size:18px;line-height:1.5;margin-bottom:24px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:20px 0}
    .box,.card{background:#0e1a2b;border:1px solid #26354d;border-radius:18px;padding:18px;box-shadow:0 10px 30px rgba(0,0,0,.18)}
    .num{font-size:34px;color:#22c55e;font-weight:900;text-align:center}.label{text-align:center;color:#cbd5e1}.card{margin:16px 0}.teams{font-size:24px;font-weight:800;margin-bottom:6px}.league{color:#94a3b8;margin-bottom:12px}
    .score{font-size:28px;color:#22c55e;font-weight:900}.row{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}.pill{background:#15233a;border:1px solid #2b3d58;border-radius:999px;padding:8px 12px;color:#dbeafe}
    .markets{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:14px}.market{background:#081525;border:1px solid #24344c;border-radius:14px;padding:12px}.market b{color:#22c55e;font-size:22px}
    .signal{font-size:22px;font-weight:900;margin-top:8px}.exp{color:#cbd5e1;margin-top:10px;line-height:1.5}.warn{background:#2a1720;border:1px solid #7f1d1d;color:#fecaca;border-radius:16px;padding:16px;margin:18px 0;text-align:center}
    .empty{text-align:center;background:#0e1a2b;border:1px solid #26354d;border-radius:18px;padding:28px;font-size:22px;color:#cbd5e1}.small{text-align:center;color:#64748b;margin-top:30px}
    @media(max-width:700px){.grid,.markets{grid-template-columns:1fr}.title{font-size:34px}.teams{font-size:21px}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="title">⚽ Football Value Bot</div>
    <div class="sub">Live Pro V3 · נתוני API-Football · סטטיסטיקות לייב · סיגנלים והסתברויות בסיסיות בלבד</div>

    {% if error %}<div class="warn">שגיאת API: {{ error }}</div>{% endif %}

    <div class="grid">
      <div class="box"><div class="num">{{ matches|length }}</div><div class="label">משחקים בלייב</div></div>
      <div class="box"><div class="num">{{ hot_count }}</div><div class="label">סיגנלים חמים</div></div>
      <div class="box"><div class="num">{{ updated }}</div><div class="label">עדכון אחרון</div></div>
    </div>

    {% if not matches %}
      <div class="empty">אין משחקים בלייב כרגע או שאין סטטיסטיקות זמינות.</div>
    {% endif %}

    {% for m in matches %}
      <div class="card">
        <div class="teams">{{ m.home }} נגד {{ m.away }}</div>
        <div class="league">{{ m.country }} · {{ m.league }}</div>
        <div class="row"><div class="pill">דקה {{ m.analysis.minute }}</div><div class="pill score">{{ m.analysis.score }}</div><div class="pill">{{ m.analysis.signal }}</div></div>
        <div class="row">
          <div class="pill">בעיטות: {{ m.analysis.stats.shots }}</div>
          <div class="pill">למסגרת: {{ m.analysis.stats.on_target }}</div>
          <div class="pill">קרנות: {{ m.analysis.stats.corners }}</div>
          <div class="pill">צהובים: {{ m.analysis.stats.yellow_cards }}</div>
          <div class="pill">אדומים: {{ m.analysis.stats.red_cards }}</div>
          <div class="pill">החזקה: {{ m.analysis.stats.possession }}</div>
        </div>
        <div class="markets">
          <div class="market">גול עד מחצית<br><b>{{ m.analysis.markets.goal_half }}%</b></div>
          <div class="market">גול עד סוף משחק<br><b>{{ m.analysis.markets.goal_match }}%</b></div>
          <div class="market">Over 1.5<br><b>{{ m.analysis.markets.over_15 }}%</b></div>
          <div class="market">Over 2.5<br><b>{{ m.analysis.markets.over_25 }}%</b></div>
          <div class="market">BTTS<br><b>{{ m.analysis.markets.btts }}%</b></div>
          <div class="market">קרנות Over 8.5<br><b>{{ m.analysis.markets.corners_over_85 }}%</b></div>
          <div class="market">ניצחון בית<br><b>{{ m.analysis.markets.home_win }}%</b></div>
          <div class="market">תיקו / חוץ<br><b>{{ m.analysis.markets.draw }}% / {{ m.analysis.markets.away_win }}%</b></div>
        </div>
        <div class="exp">הסבר: {{ m.analysis.explanation }}</div>
      </div>
    {% endfor %}

    <div class="small">האתר מתרענן אוטומטית כל 45 שניות. זה כלי ניתוח בלבד, לא הבטחת רווח.</div>
  </div>
</body>
</html>
"""


@app.route("/")
def index():
    matches, error = load_live_matches()
    hot_count = sum(1 for m in matches if "חם" in m["analysis"]["signal"])
    updated = datetime.utcnow().strftime("%H:%M")
    return render_template_string(HTML, matches=matches, error=error, hot_count=hot_count, updated=updated)


@app.route("/health")
def health():
    return jsonify({"ok": True, "has_api_key": bool(API_KEY)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
