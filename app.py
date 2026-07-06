import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

API_BASE = "https://api.football-data.org/v4"
TOKEN = os.getenv("FOOTBALL_DATA_TOKEN") or os.getenv("API_FOOTBALL_KEY") or ""

HTML = r'''
<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="60">
  <title>Football Value Bot</title>
  <style>
    :root { --bg:#07111f; --card:#0d1a2b; --line:#24344e; --green:#25d366; --muted:#a8b3c7; --red:#7d1717; --orange:#ffb020; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: Arial, sans-serif; background:var(--bg); color:#edf2ff; }
    .wrap { max-width: 980px; margin:0 auto; padding:28px 16px 60px; }
    h1 { color:var(--green); text-align:center; font-size:44px; margin:22px 0 8px; }
    .sub { text-align:center; color:var(--muted); font-size:20px; line-height:1.6; margin-bottom:22px; }
    .stats { display:grid; grid-template-columns: repeat(3,1fr); gap:14px; margin:18px 0; }
    .stat,.msg,.match { background:var(--card); border:1px solid var(--line); border-radius:18px; padding:20px; }
    .stat b { display:block; color:var(--green); font-size:34px; text-align:center; }
    .stat span { display:block; color:#d7deec; text-align:center; font-size:18px; margin-top:6px; }
    .msg { text-align:center; font-size:20px; color:#d7deec; margin:18px 0; }
    .err { background:#3d1010; border-color:#8d2b2b; }
    .warn { background:#3b2a09; border-color:#9b6a10; }
    .match { margin:14px 0; }
    .top { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; flex-wrap:wrap; }
    .teams { font-size:22px; font-weight:700; }
    .league { color:var(--muted); font-size:15px; margin-top:5px; }
    .score { color:var(--green); font-size:28px; font-weight:800; direction:ltr; }
    .grid { display:grid; grid-template-columns: repeat(3,1fr); gap:10px; margin-top:14px; }
    .pill { border:1px solid var(--line); border-radius:12px; padding:12px; background:#091626; text-align:center; }
    .pill b { display:block; color:#fff; font-size:20px; }
    .pill span { color:var(--muted); font-size:14px; }
    .signal { margin-top:14px; border-radius:12px; padding:12px; background:#0b2217; border:1px solid #1f6d42; color:#d7ffe6; }
    .small { text-align:center; color:#738099; font-size:14px; margin-top:28px; line-height:1.7; }
    a { color:#81b6ff; }
    @media (max-width:700px) { h1{font-size:34px}.stats{grid-template-columns:1fr}.grid{grid-template-columns:1fr}.teams{font-size:20px}.score{font-size:24px} }
  </style>
</head>
<body>
<div class="wrap">
  <h1>Football Value Bot ⚽</h1>
  <div class="sub">גרסת Football-Data V1 · מקור נתונים חדש · לייב/משחקים זמינים</div>

  <div class="stats">
    <div class="stat"><b>{{ live_count }}</b><span>משחקים בלייב</span></div>
    <div class="stat"><b>{{ signals }}</b><span>סיגנלים</span></div>
    <div class="stat"><b>{{ updated }}</b><span>עדכון אחרון</span></div>
  </div>

  {% if error %}<div class="msg err">API: {{ error }}</div>{% endif %}
  {% if warning %}<div class="msg warn">{{ warning }}</div>{% endif %}

  {% if matches %}
    {% for m in matches %}
      <div class="match">
        <div class="top">
          <div>
            <div class="teams">{{ m.home }} - {{ m.away }}</div>
            <div class="league">{{ m.competition }} · {{ m.status }} · {{ m.utcDate }}</div>
          </div>
          <div class="score">{{ m.score }}</div>
        </div>
        <div class="grid">
          <div class="pill"><b>{{ m.home_win }}%</b><span>בית</span></div>
          <div class="pill"><b>{{ m.draw }}%</b><span>תיקו</span></div>
          <div class="pill"><b>{{ m.away_win }}%</b><span>חוץ</span></div>
        </div>
        <div class="grid">
          <div class="pill"><b>{{ m.goal_signal }}%</b><span>שער נוסף משוער</span></div>
          <div class="pill"><b>{{ m.total_goals }}</b><span>שערים במשחק</span></div>
          <div class="pill"><b>{{ m.minute }}</b><span>זמן</span></div>
        </div>
        <div class="signal">{{ m.explain }}</div>
      </div>
    {% endfor %}
  {% else %}
    <div class="msg">אין משחקים בלייב כרגע או שאין משחקים זמינים במסלול החינמי.</div>
  {% endif %}

  <div class="small">
    Football-Data.org במסלול החינמי נותן בעיקר תוצאות, לוחות משחקים ותחרויות נתמכות. הוא בדרך כלל לא נותן סטטיסטיקות לייב עמוקות כמו קרנות, בעיטות ו־xG.<br>
    קישורי בדיקה: <a href="/health">/health</a> · <a href="/api/live">/api/live</a>
  </div>
</div>
</body>
</html>
'''


def now_str() -> str:
    return datetime.now().strftime("%H:%M")


def fd_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not TOKEN:
        return {"__error": "Missing FOOTBALL_DATA_TOKEN / API_FOOTBALL_KEY in Render Environment"}
    try:
        r = requests.get(
            f"{API_BASE}{path}",
            headers={"X-Auth-Token": TOKEN},
            params=params or {},
            timeout=15,
        )
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:500]}
        if r.status_code >= 400:
            message = data.get("message") or data.get("error") or str(data)
            return {"__error": f"HTTP {r.status_code}: {message}", "__raw": data}
        return data
    except Exception as e:
        return {"__error": str(e)}


def get_matches() -> Dict[str, Any]:
    # First try LIVE. If no live matches, show today's matches for debugging and usefulness.
    live = fd_get("/matches", {"status": "LIVE"})
    if live.get("__error"):
        return live
    matches = live.get("matches", []) or []
    if matches:
        live["__source"] = "LIVE"
        return live

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day = fd_get("/matches", {"dateFrom": today, "dateTo": today})
    if day.get("__error"):
        # If today's fallback failed, return live response rather than error if live worked.
        live["__source"] = "LIVE_EMPTY"
        return live
    day["__source"] = "TODAY_FALLBACK"
    return day


def score_to_text(score: Dict[str, Any]) -> str:
    ft = score.get("fullTime") or {}
    ht = score.get("halfTime") or {}
    home = ft.get("home")
    away = ft.get("away")
    if home is None or away is None:
        home = ht.get("home")
        away = ht.get("away")
    if home is None or away is None:
        return "0-0"
    return f"{home}-{away}"


def safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x) if x is not None else default
    except Exception:
        return default


def estimate(match: Dict[str, Any]) -> Dict[str, Any]:
    home_team = (match.get("homeTeam") or {}).get("name", "Home")
    away_team = (match.get("awayTeam") or {}).get("name", "Away")
    comp = (match.get("competition") or {}).get("name", "Competition")
    status = match.get("status", "UNKNOWN")
    score = match.get("score") or {}
    ft = score.get("fullTime") or {}
    ht = score.get("halfTime") or {}
    home_goals = ft.get("home") if ft.get("home") is not None else ht.get("home")
    away_goals = ft.get("away") if ft.get("away") is not None else ht.get("away")
    home_goals = safe_int(home_goals, 0)
    away_goals = safe_int(away_goals, 0)
    total = home_goals + away_goals

    # Football-Data does not expose minute in this endpoint. Use status instead.
    minute = "LIVE" if status in ["IN_PLAY", "PAUSED", "LIVE"] else status

    # Basic placeholder model based only on score/status because provider lacks live stats.
    if status in ["IN_PLAY", "LIVE"]:
        goal_signal = min(78, 38 + total * 9)
    elif status == "PAUSED":
        goal_signal = min(65, 30 + total * 8)
    else:
        goal_signal = 18

    if home_goals > away_goals:
        home_win, draw, away_win = 58, 25, 17
    elif away_goals > home_goals:
        home_win, draw, away_win = 17, 25, 58
    else:
        home_win, draw, away_win = 34, 36, 30

    if status in ["IN_PLAY", "LIVE", "PAUSED"]:
        explain = "סיגנל בסיסי לפי מצב המשחק והתוצאה. לסיגנל מקצועי נצטרך ספק שנותן בעיטות, קרנות, xG ומומנטום."
    else:
        explain = "משחק לא בלייב כרגע. מוצג כמידע זמין מהספק החינמי."

    return {
        "home": home_team,
        "away": away_team,
        "competition": comp,
        "status": status,
        "utcDate": match.get("utcDate", ""),
        "score": score_to_text(score),
        "total_goals": total,
        "minute": minute,
        "goal_signal": goal_signal,
        "home_win": home_win,
        "draw": draw,
        "away_win": away_win,
        "explain": explain,
    }


@app.route("/")
def index():
    data = get_matches()
    error = data.get("__error")
    source = data.get("__source")
    matches_raw = data.get("matches", []) if not error else []
    matches = [estimate(m) for m in matches_raw[:30]]
    live_count = sum(1 for m in matches if m["status"] in ["IN_PLAY", "LIVE", "PAUSED"])
    signals = sum(1 for m in matches if m["goal_signal"] >= 55 and m["status"] in ["IN_PLAY", "LIVE", "PAUSED"])
    warning = ""
    if source == "TODAY_FALLBACK" and not live_count:
        warning = "אין כרגע משחקי LIVE מהספק, לכן מוצגים משחקי היום/זמינים מהמסלול החינמי."
    return render_template_string(
        HTML,
        matches=matches,
        live_count=live_count,
        signals=signals,
        updated=now_str(),
        error=error,
        warning=warning,
    )


@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "provider": "football-data.org",
        "version": "football-data-v1",
        "has_token": bool(TOKEN),
        "token_env": "FOOTBALL_DATA_TOKEN" if os.getenv("FOOTBALL_DATA_TOKEN") else ("API_FOOTBALL_KEY" if os.getenv("API_FOOTBALL_KEY") else None),
    })


@app.route("/api/live")
def api_live():
    data = get_matches()
    if data.get("__error"):
        return jsonify({"ok": False, "error": data.get("__error"), "raw": data.get("__raw")}), 502
    matches = data.get("matches", []) or []
    return jsonify({
        "ok": True,
        "provider": "football-data.org",
        "source": data.get("__source"),
        "count": len(matches),
        "sample": matches[:3],
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
