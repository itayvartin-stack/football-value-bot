import os
from datetime import datetime
import requests
from flask import Flask, render_template_string

app = Flask(__name__)

API_KEY = os.getenv('API_FOOTBALL_KEY', '').strip()
BASE_URL = 'https://v3.football.api-sports.io'

HEADERS = {'x-apisports-key': API_KEY}


def api_get(path, params=None):
    if not API_KEY:
        return {'error': 'missing_key', 'response': []}
    try:
        r = requests.get(BASE_URL + path, headers=HEADERS, params=params or {}, timeout=15)
        data = r.json()
        if r.status_code != 200:
            return {'error': f'HTTP {r.status_code}', 'raw': data, 'response': []}
        return data
    except Exception as e:
        return {'error': str(e), 'response': []}


def stat_value(stats, team_index, stat_name, default=0):
    try:
        for item in stats[team_index].get('statistics', []):
            if item.get('type') == stat_name:
                value = item.get('value')
                if value is None:
                    return default
                if isinstance(value, str) and value.endswith('%'):
                    return int(value.replace('%', ''))
                return int(value)
    except Exception:
        pass
    return default


def estimate_goal_probability(minute, home_stats, away_stats, total_goals):
    shots_on = home_stats['shots_on'] + away_stats['shots_on']
    shots_total = home_stats['shots_total'] + away_stats['shots_total']
    corners = home_stats['corners'] + away_stats['corners']
    attacks_score = shots_on * 9 + shots_total * 2.2 + corners * 3.2 + total_goals * 4
    remaining = max(0, 90 - (minute or 0)) / 90
    pressure = min(90, max(8, attacks_score * (0.55 + remaining)))
    return round(pressure, 1)


def estimate_corner_signal(home_stats, away_stats, minute):
    corners = home_stats['corners'] + away_stats['corners']
    if not minute or minute <= 0:
        return 0
    projected = corners / minute * 90
    return round(projected, 1)


def analyze_fixture(fx):
    fixture_id = fx['fixture']['id']
    minute = fx['fixture']['status'].get('elapsed') or 0
    home = fx['teams']['home']['name']
    away = fx['teams']['away']['name']
    league = fx['league']['name']
    country = fx['league'].get('country', '')
    home_goals = fx['goals']['home'] or 0
    away_goals = fx['goals']['away'] or 0

    stats_data = api_get('/fixtures/statistics', {'fixture': fixture_id})
    stats = stats_data.get('response', [])

    home_stats = {
        'shots_on': stat_value(stats, 0, 'Shots on Goal'),
        'shots_total': stat_value(stats, 0, 'Total Shots'),
        'corners': stat_value(stats, 0, 'Corner Kicks'),
        'possession': stat_value(stats, 0, 'Ball Possession'),
        'yellow': stat_value(stats, 0, 'Yellow Cards'),
        'red': stat_value(stats, 0, 'Red Cards'),
    }
    away_stats = {
        'shots_on': stat_value(stats, 1, 'Shots on Goal'),
        'shots_total': stat_value(stats, 1, 'Total Shots'),
        'corners': stat_value(stats, 1, 'Corner Kicks'),
        'possession': stat_value(stats, 1, 'Ball Possession'),
        'yellow': stat_value(stats, 1, 'Yellow Cards'),
        'red': stat_value(stats, 1, 'Red Cards'),
    }

    goal_prob = estimate_goal_probability(minute, home_stats, away_stats, home_goals + away_goals)
    corner_projection = estimate_corner_signal(home_stats, away_stats, minute)

    if goal_prob >= 70:
        signal = '🔥 לחץ גבוה - לעקוב מקרוב'
    elif goal_prob >= 50:
        signal = '🟡 בינוני - שווה מעקב'
    else:
        signal = '⚪ נמוך כרגע'

    return {
        'home': home, 'away': away, 'league': league, 'country': country,
        'minute': minute, 'score': f'{home_goals}-{away_goals}',
        'home_stats': home_stats, 'away_stats': away_stats,
        'goal_prob': goal_prob, 'corner_projection': corner_projection,
        'signal': signal,
        'has_stats': bool(stats),
    }


HTML = '''
<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="45">
<title>Football Value Bot</title>
<style>
body{margin:0;background:#07111f;color:#e9eef7;font-family:Arial,Helvetica,sans-serif}
.wrap{max-width:980px;margin:auto;padding:24px}
h1{color:#22c55e;text-align:center;font-size:42px;margin:18px 0 8px}.sub{text-align:center;color:#9aa7b7;font-size:18px;margin-bottom:24px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:22px}.box{background:#111c2e;border:1px solid #20304a;border-radius:18px;padding:18px;text-align:center}.num{font-size:32px;color:#22c55e;font-weight:bold}.card{background:#101a2b;border:1px solid #243651;border-radius:20px;padding:18px;margin:14px 0;box-shadow:0 10px 22px rgba(0,0,0,.18)}.top{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}.teams{font-size:24px;font-weight:bold}.meta{color:#9aa7b7;margin-top:6px}.score{font-size:28px;color:#22c55e;font-weight:bold}.signal{margin-top:12px;padding:10px;border-radius:12px;background:#0b2537;border:1px solid #21465f}.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:14px}.stat{background:#0b1423;border-radius:12px;padding:10px}.label{color:#93a4b8;font-size:13px}.value{font-size:18px;font-weight:bold}.warn{background:#2a1f10;border:1px solid #594017;color:#ffd18a;padding:14px;border-radius:14px;margin:16px 0}.empty{text-align:center;background:#111c2e;border-radius:20px;padding:28px;color:#b8c3d3}@media(max-width:700px){.wrap{padding:18px}h1{font-size:34px}.grid,.stats{grid-template-columns:1fr}.teams{font-size:20px}}
</style>
</head>
<body>
<div class="wrap">
<h1>⚽ Football Value Bot</h1>
<div class="sub">Live Sport V2 · נתוני לייב מ־API-Football · מתעדכן כל 45 שניות</div>
{% if error %}<div class="warn">שגיאה: {{ error }}</div>{% endif %}
<div class="grid">
 <div class="box"><div class="num">{{ games|length }}</div><div>משחקים בלייב</div></div>
 <div class="box"><div class="num">{{ signals }}</div><div>סיגנלים חמים</div></div>
 <div class="box"><div class="num">{{ updated }}</div><div>עדכון אחרון</div></div>
</div>
{% if not games %}
 <div class="empty">אין משחקים בלייב כרגע או שאין סטטיסטיקות זמינות.</div>
{% endif %}
{% for g in games %}
<div class="card">
 <div class="top">
  <div><div class="teams">{{ g.home }} - {{ g.away }}</div><div class="meta">{{ g.country }} · {{ g.league }} · דקה {{ g.minute }}</div></div>
  <div class="score">{{ g.score }}</div>
 </div>
 <div class="signal">{{ g.signal }} · סיכוי גול משוער: <b>{{ g.goal_prob }}%</b> · תחזית קרנות ל־90 דק׳: <b>{{ g.corner_projection }}</b></div>
 <div class="stats">
  <div class="stat"><div class="label">בעיטות למסגרת</div><div class="value">{{ g.home_stats.shots_on }} - {{ g.away_stats.shots_on }}</div></div>
  <div class="stat"><div class="label">סה״כ בעיטות</div><div class="value">{{ g.home_stats.shots_total }} - {{ g.away_stats.shots_total }}</div></div>
  <div class="stat"><div class="label">קרנות</div><div class="value">{{ g.home_stats.corners }} - {{ g.away_stats.corners }}</div></div>
  <div class="stat"><div class="label">שליטה בכדור</div><div class="value">{{ g.home_stats.possession }}% - {{ g.away_stats.possession }}%</div></div>
  <div class="stat"><div class="label">צהובים</div><div class="value">{{ g.home_stats.yellow }} - {{ g.away_stats.yellow }}</div></div>
  <div class="stat"><div class="label">אדומים</div><div class="value">{{ g.home_stats.red }} - {{ g.away_stats.red }}</div></div>
 </div>
 {% if not g.has_stats %}<div class="meta" style="margin-top:10px">למשחק הזה אין סטטיסטיקות זמינות מה־API כרגע.</div>{% endif %}
</div>
{% endfor %}
<div class="sub">זה כלי ניתוח בלבד, לא המלצת הימור ולא הבטחת רווח.</div>
</div>
</body>
</html>
'''


@app.route('/')
def index():
    live_data = api_get('/fixtures', {'live': 'all'})
    raw_games = live_data.get('response', [])
    error = live_data.get('error')
    games = [analyze_fixture(fx) for fx in raw_games[:15]]
    signals = sum(1 for g in games if g['goal_prob'] >= 70)
    updated = datetime.now().strftime('%H:%M')
    return render_template_string(HTML, games=games, signals=signals, updated=updated, error=error)


@app.route('/health')
def health():
    return {'status': 'ok', 'has_api_key': bool(API_KEY)}


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
