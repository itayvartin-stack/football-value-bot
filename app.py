import os
import math
import requests
from flask import Flask, render_template_string

API_KEY = os.environ.get('API_FOOTBALL_KEY', '').strip()
API_URL = 'https://v3.football.api-sports.io'

app = Flask(__name__)

HTML = '''
<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Football Value Bot</title>
  <style>
    body{font-family:Arial,sans-serif;background:#0b1220;color:#e5e7eb;margin:0;padding:20px}
    h1{color:#22c55e}.card{background:#111827;border:1px solid #243244;border-radius:14px;padding:16px;margin:12px 0}
    .muted{color:#94a3b8}.good{color:#22c55e}.warn{color:#f59e0b}.bad{color:#ef4444}
    table{width:100%;border-collapse:collapse;margin-top:10px}td,th{border-bottom:1px solid #243244;padding:8px;text-align:right}
  </style>
</head>
<body>
<h1>⚽ Football Value Bot</h1>
<p class="muted">גרסת V1: משחקי לייב + ניתוח הסתברות בסיסי. זה כלי ניתוח בלבד, לא הבטחת רווח.</p>
{% if error %}<div class="card bad">{{ error }}</div>{% endif %}
{% if games|length == 0 and not error %}<div class="card">אין משחקים בלייב כרגע.</div>{% endif %}
{% for g in games %}
<div class="card">
  <h2>{{ g.home }} - {{ g.away }}</h2>
  <p>דקה: <b>{{ g.minute }}</b> | תוצאה: <b>{{ g.score }}</b> | ליגה: {{ g.league }}</p>
  <table>
    <tr><th>שוק</th><th>הערכת מודל</th><th>דירוג</th></tr>
    <tr><td>גול עד סוף המחצית</td><td>{{ g.goal_ht }}%</td><td class="{{ g.goal_ht_class }}">{{ g.goal_ht_text }}</td></tr>
    <tr><td>גול עד סוף המשחק</td><td>{{ g.goal_ft }}%</td><td class="{{ g.goal_ft_class }}">{{ g.goal_ft_text }}</td></tr>
    <tr><td>ניצחון בית</td><td>{{ g.home_win }}%</td><td></td></tr>
    <tr><td>תיקו</td><td>{{ g.draw }}%</td><td></td></tr>
    <tr><td>ניצחון חוץ</td><td>{{ g.away_win }}%</td><td></td></tr>
    <tr><td>קרנות - לחץ התקפי</td><td>{{ g.corners_score }}/100</td><td></td></tr>
  </table>
</div>
{% endfor %}
</body>
</html>
'''

def label(p):
    if p >= 75:
        return 'חזק למעקב', 'good'
    if p >= 55:
        return 'בינוני', 'warn'
    return 'חלש כרגע', 'bad'

def calc_game(fx):
    home = fx['teams']['home']['name']
    away = fx['teams']['away']['name']
    minute = fx['fixture']['status'].get('elapsed') or 0
    hg = fx['goals'].get('home') or 0
    ag = fx['goals'].get('away') or 0
    league = fx['league']['name']

    # V1 heuristic. Later we replace this with real stats/xG + historical model.
    total_goals = hg + ag
    remaining_ht = max(0, 45 - minute) if minute <= 45 else 0
    remaining_ft = max(0, 90 - minute)

    base_pressure = 38 + min(18, total_goals * 7)
    goal_ht = round(max(3, min(88, base_pressure * (remaining_ht / 45))))
    goal_ft = round(max(5, min(92, 22 + base_pressure * (remaining_ft / 90))))

    if hg > ag:
        home_win, draw, away_win = 58, 25, 17
    elif ag > hg:
        home_win, draw, away_win = 17, 25, 58
    else:
        home_win, draw, away_win = 35, 38, 27

    # time adjustment
    if minute > 70 and hg != ag:
        draw = max(12, draw - 8)
    if minute > 70 and hg == ag:
        draw = min(50, draw + 8)

    ht_text, ht_cls = label(goal_ht)
    ft_text, ft_cls = label(goal_ft)

    return dict(home=home, away=away, minute=minute, score=f'{hg}-{ag}', league=league,
                goal_ht=goal_ht, goal_ft=goal_ft, home_win=home_win, draw=draw, away_win=away_win,
                corners_score=min(100, round(goal_ft * 0.8)),
                goal_ht_text=ht_text, goal_ht_class=ht_cls,
                goal_ft_text=ft_text, goal_ft_class=ft_cls)

def fetch_live_games():
    if not API_KEY:
        return [], 'חסר API_FOOTBALL_KEY ב-Environment Variables של Render.'
    try:
        r = requests.get(f'{API_URL}/fixtures', headers={'x-apisports-key': API_KEY}, params={'live': 'all'}, timeout=20)
        if r.status_code != 200:
            return [], f'שגיאת API: {r.status_code} - {r.text[:200]}'
        data = r.json()
        fixtures = data.get('response', [])
        return [calc_game(fx) for fx in fixtures], None
    except Exception as e:
        return [], f'שגיאה בחיבור: {e}'

@app.route('/')
def index():
    games, error = fetch_live_games()
    return render_template_string(HTML, games=games, error=error)

@app.route('/health')
def health():
    return 'ok'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
