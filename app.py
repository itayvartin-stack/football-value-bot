import os, time, math
from datetime import datetime
import requests
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)
API_KEY = os.getenv('API_FOOTBALL_KEY', '').strip()
BASE = 'https://v3.football.api-sports.io'
CACHE = {'ts': 0, 'data': None, 'error': None}
TTL = 45

def api_get(path, params=None):
    if not API_KEY:
        raise RuntimeError('Missing API_FOOTBALL_KEY')
    r = requests.get(BASE + path, headers={'x-apisports-key': API_KEY}, params=params or {}, timeout=20)
    try:
        payload = r.json()
    except Exception:
        raise RuntimeError(f'API returned non JSON status={r.status_code}')
    if r.status_code != 200:
        raise RuntimeError(f'API status {r.status_code}: {payload}')
    if payload.get('errors'):
        raise RuntimeError(f"API errors: {payload.get('errors')}")
    return payload.get('response', [])

def val_stat(stats, name):
    for item in stats or []:
        if str(item.get('type','')).lower() == name.lower():
            v = item.get('value')
            if v is None: return 0
            if isinstance(v, str) and v.endswith('%'):
                try: return int(v.replace('%',''))
                except: return 0
            try: return int(v)
            except: return 0
    return 0

def pct(x):
    return max(1, min(99, int(round(x))))

def analyze(fix, stats_by_team):
    home = fix['teams']['home']['name']
    away = fix['teams']['away']['name']
    elapsed = fix['fixture']['status'].get('elapsed') or 0
    gh = fix['goals'].get('home') or 0
    ga = fix['goals'].get('away') or 0
    home_stats = stats_by_team.get(home, [])
    away_stats = stats_by_team.get(away, [])
    shots_on = val_stat(home_stats,'Shots on Goal') + val_stat(away_stats,'Shots on Goal')
    shots_total = val_stat(home_stats,'Total Shots') + val_stat(away_stats,'Total Shots')
    corners = val_stat(home_stats,'Corner Kicks') + val_stat(away_stats,'Corner Kicks')
    reds = val_stat(home_stats,'Red Cards') + val_stat(away_stats,'Red Cards')
    possession_home = val_stat(home_stats,'Ball Possession')
    # simple baseline model (not betting advice)
    remaining_ht = max(0, 45 - min(elapsed,45))
    remaining_ft = max(0, 90 - min(elapsed,90))
    pressure = shots_on*10 + shots_total*2.2 + corners*4 + max(0, (gh+ga))*3
    if reds: pressure += 4
    goal_ht = pct(8 + pressure * (remaining_ht/45) * 0.85)
    goal_ft = pct(12 + pressure * (remaining_ft/90) * 1.15)
    hot = goal_ht >= 55 or goal_ft >= 70 or (shots_on >= 5 and corners >= 5)
    signal = '🔥 חם' if hot else 'לעקוב'
    confidence = pct((shots_on*8 + shots_total + corners*3) / 1.6)
    return {
        'league': fix['league']['name'], 'country': fix['league']['country'],
        'home': home, 'away': away, 'minute': elapsed, 'score': f'{gh}-{ga}',
        'status': fix['fixture']['status'].get('short'),
        'shots_on': shots_on, 'shots_total': shots_total, 'corners': corners,
        'red_cards': reds, 'home_possession': possession_home,
        'goal_ht': goal_ht, 'goal_ft': goal_ft, 'confidence': confidence, 'signal': signal,
    }

def load_live():
    now = time.time()
    if CACHE['data'] is not None and now - CACHE['ts'] < TTL:
        return CACHE['data'], CACHE['error']
    try:
        fixtures = api_get('/fixtures', {'live':'all'})
        games = []
        for f in fixtures[:35]:
            fid = f['fixture']['id']
            stats_resp = api_get('/fixtures/statistics', {'fixture': fid})
            stats_by_team = {s.get('team',{}).get('name',''): s.get('statistics',[]) for s in stats_resp}
            games.append(analyze(f, stats_by_team))
        CACHE.update(ts=now, data=games, error=None)
        return games, None
    except Exception as e:
        CACHE.update(ts=now, data=[], error=str(e))
        return [], str(e)

HTML = '''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="45"><title>Football Value Bot</title><style>
body{margin:0;background:#07111f;color:#e8eef7;font-family:Arial,sans-serif}.wrap{max-width:930px;margin:auto;padding:28px 16px}h1{color:#22c55e;font-size:40px;text-align:center}.sub{text-align:center;color:#a8b3c7;font-size:22px;line-height:1.5}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:22px 0}.box,.card{background:#101b2d;border:1px solid #26344d;border-radius:22px;padding:18px;text-align:center}.num{font-size:38px;color:#22c55e;font-weight:bold}.muted{color:#9aa8bd}.card{text-align:right;margin:14px 0}.teams{font-size:25px;font-weight:bold}.badge{display:inline-block;background:#17304d;border:1px solid #2c4b73;border-radius:999px;padding:7px 12px;margin:5px}.hot{background:#3a2208;border-color:#b45309;color:#fbbf24}.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:12px}.stat{background:#0b1424;border-radius:13px;padding:10px}.err{background:#3b0d0d;border:1px solid #7f1d1d;color:#fecaca}.foot{text-align:center;color:#718096;margin-top:30px}@media(max-width:650px){h1{font-size:34px}.grid,.stats{grid-template-columns:1fr}.teams{font-size:22px}}
</style></head><body><div class="wrap"><h1>Football Value Bot ⚽</h1><div class="sub">Live Pro V4 · נתוני API-Football · סטטיסטיקות לייב · סיגנלים בסיסיים</div>
<div class="grid"><div class="box"><div class="num">{{games|length}}</div><div>משחקים בלייב</div></div><div class="box"><div class="num">{{hot}}</div><div>סיגנלים חמים</div></div><div class="box"><div class="num">{{updated}}</div><div>עדכון אחרון</div></div></div>
{% if error %}<div class="card err">שגיאת API: {{error}}</div>{% endif %}
{% if not games %}<div class="card" style="text-align:center;font-size:24px">אין משחקים בלייב כרגע או שאין סטטיסטיקות זמינות.</div>{% endif %}
{% for g in games %}<div class="card"><div class="teams">{{g.home}} - {{g.away}}</div><div class="muted">{{g.country}} · {{g.league}} · דקה {{g.minute}} · תוצאה {{g.score}}</div><div><span class="badge {% if '🔥' in g.signal %}hot{% endif %}">{{g.signal}}</span><span class="badge">ביטחון {{g.confidence}}%</span></div><div class="stats"><div class="stat">⚽ גול עד מחצית: <b>{{g.goal_ht}}%</b></div><div class="stat">⚽ גול עד סוף משחק: <b>{{g.goal_ft}}%</b></div><div class="stat">🎯 בעיטות למסגרת: <b>{{g.shots_on}}</b></div><div class="stat">🥅 סה״כ בעיטות: <b>{{g.shots_total}}</b></div><div class="stat">🚩 קרנות: <b>{{g.corners}}</b></div><div class="stat">🟥 אדומים: <b>{{g.red_cards}}</b></div></div></div>{% endfor %}
<div class="foot">מתרענן אוטומטית כל 45 שניות. ניתוח הסתברות בסיסי בלבד, לא הבטחת רווח.</div></div></body></html>'''

@app.route('/')
def index():
    games, error = load_live()
    hot = sum(1 for g in games if '🔥' in g['signal'])
    return render_template_string(HTML, games=games, hot=hot, error=error, updated=datetime.now().strftime('%H:%M'))

@app.route('/health')
def health():
    return jsonify(ok=True, has_api_key=bool(API_KEY), version='live-pro-v4')

@app.route('/api/live')
def api_live():
    games, error = load_live()
    return jsonify(ok=not bool(error), error=error, count=len(games), games=games)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
