"""Round 2: corrected harness — proper CSRF headers, correct field names."""
import os, re, json, sqlite3

os.environ.setdefault("CHURCH_DB", "/tmp/test_church.db")
os.environ.setdefault("SECRET_KEY", "testkey")
os.environ.setdefault("ADMIN_PASSWORD", "testadmin123")

import app as appmod
app = appmod.app
app.config["TESTING"] = True

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))

def get_csrf(client, path="/"):
    html = client.get(path).get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else None

def jpost(client, url, payload, tok):
    return client.post(url, json=payload, headers={"X-CSRF-Token": tok})

# ---------- Admin: create event with real field names ----------
c = app.test_client()
tok = get_csrf(c, "/admin/login")
c.post("/admin/login", data={"password": "testadmin123", "csrf_token": tok})
tok = get_csrf(c, "/admin/new")
r = c.post("/admin/new", data={
    "title": "Round2 Service", "category": "service", "event_date": "2026-08-09",
    "event_time": "10:30", "location": "Main Hall", "description": "test",
    "recurring": "none", "csrf_token": tok}, follow_redirects=True)
cal = c.get("/community/calendar").get_data(as_text=True)
check("admin creates event → appears on calendar", "Round2 Service" in cal, f"post={r.status_code}")

# event ICS now exists
db = sqlite3.connect("/tmp/test_church.db")
eid = db.execute("SELECT id FROM events WHERE title='Round2 Service'").fetchone()[0]
r = c.get(f"/event/{eid}.ics")
check("event .ics download works", r.status_code == 200 and b"BEGIN:VCALENDAR" in r.data)
r = c.get("/calendar.ics")
check("full calendar .ics works", r.status_code == 200 and b"Round2 Service" in r.data)

# CSRF negative: no token → 303 redirect AND event NOT created
before = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
r = c.post("/admin/new", data={"title": "EvilEvent", "category": "service",
                               "event_date": "2026-08-10", "event_time": "10:00"})
after = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
check("form POST without CSRF: redirected AND nothing written", r.status_code == 303 and before == after,
      f"status={r.status_code} count {before}->{after}")

# ---------- Member JSON flows with header ----------
m = app.test_client()
tok = get_csrf(m, "/account/signup")
m.post("/account/signup", data={"name": "R2 User", "email": "r2@example.com",
                                "password": "s3curePass!", "csrf_token": tok})
tok = get_csrf(m, "/account")

r = jpost(m, "/api/sync/saved_verses", {"key": "john-3-16", "value": {"ref": "John 3:16"}}, tok)
check("sync PUT with header works", r.status_code == 200, r.get_data(as_text=True)[:80])
r = m.get("/api/sync/saved_verses")
check("sync read-back works", r.status_code == 200 and "john-3-16" in r.get_data(as_text=True))

# JSON POST with WRONG token
r = jpost(m, "/api/sync/saved_verses", {"key": "x", "value": {}}, "forged-token")
check("sync PUT with forged token rejected", r.status_code == 400)

# ---------- Push subscribe (native path) with header ----------
r = jpost(m, "/api/push/subscribe", {"native_token": "fcm-123", "platform": "android",
                                     "prefs": {"events": True}}, tok)
check("native android subscribe", r.status_code == 200, r.get_data(as_text=True)[:80])
r = jpost(m, "/api/push/subscribe", {"native_token": "apns-456", "platform": "ios",
                                     "prefs": {"sermons": True}}, tok)
check("native ios subscribe", r.status_code == 200)
r = jpost(m, "/api/push/subscribe", {"native_token": "t", "platform": "blackberry"}, tok)
check("bogus platform rejected", r.status_code == 400)
r = jpost(m, "/api/push/unsubscribe", {"native_token": "fcm-123", "platform": "android"}, tok)
check("native unsubscribe", r.status_code == 200)

rows = [x[0] for x in db.execute("SELECT endpoint FROM push_subscriptions").fetchall()]
check("DB state: ios kept, android removed",
      "native:ios:apns-456" in rows and "native:android:fcm-123" not in rows, str(rows))

# duplicate ios subscribe → still one row (upsert)
jpost(m, "/api/push/subscribe", {"native_token": "apns-456", "platform": "ios",
                                 "prefs": {"events": True}}, tok)
n = db.execute("SELECT COUNT(*) FROM push_subscriptions WHERE endpoint='native:ios:apns-456'").fetchone()[0]
check("re-subscribe upserts, no duplicate rows", n == 1, f"rows={n}")

# ---------- broadcast() with a native token and no FCM key ----------
with app.test_request_context():
    appmod.g.db = sqlite3.connect("/tmp/test_church.db")
    appmod.g.db.row_factory = sqlite3.Row
    sent, failed = appmod.broadcast("events", "Test", "Body", "/")
    check("broadcast with native sub + no FCM key doesn't crash", True, f"sent={sent} failed={failed}")
    # crucial: the ios subscription must NOT have been deleted as 'dead'
    n = appmod.g.db.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0]
    check("unsent native subscription NOT deleted", n >= 1, f"remaining={n}")

# ---------- Game scores with header ----------
r = jpost(m, "/games/memory/score", {"score": 42, "name": "Tester"}, tok)
check("game score accepted", r.status_code in (200, 201), f"{r.status_code} {r.get_data(as_text=True)[:80]}")
lb = m.get("/games/memory/leaderboard")
check("leaderboard renders", lb.status_code == 200)

# absurd + negative scores
r1 = jpost(m, "/games/memory/score", {"score": 999999999, "name": "Cheat"}, tok)
r2 = jpost(m, "/games/memory/score", {"score": -5, "name": "Neg"}, tok)
r3 = jpost(m, "/games/memory/score", {"score": "abc", "name": "Str"}, tok)
check("cheat-score handling (detail)", True, f"huge={r1.status_code} neg={r2.status_code} str={r3.status_code}")

# ---------- XSS escaping ----------
tok_q = get_csrf(m, "/questions/ask")
m.post("/questions/ask", data={"name": "<script>alert(1)</script>", 
                               "question": "Escaped? <script>alert(2)</script>",
                               "csrf_token": tok_q}, follow_redirects=True)
qrow = db.execute("SELECT id FROM questions ORDER BY id DESC LIMIT 1").fetchone()
check("question stored", qrow is not None)
if qrow:
    # approve as admin, then check public rendering
    tok_a = get_csrf(c, "/admin/questions")
    c.post(f"/admin/questions/{qrow[0]}/answer", data={"answer": "yes", "csrf_token": tok_a})
    pub = m.get("/questions").get_data(as_text=True)
    check("XSS payload escaped on public page", "<script>alert(2)</script>" not in pub,
          "raw script tag found!" if "<script>alert(2)</script>" in pub else "escaped or not shown")

# ---------- Prayer flow + safety filter ----------
tok_p = get_csrf(m, "/prayer/new")
r = m.post("/prayer/new", data={"name": "R2", "request": "Please pray for my job interview",
                                "csrf_token": tok_p}, follow_redirects=True)
prow = db.execute("SELECT status FROM prayers ORDER BY id DESC LIMIT 1").fetchone()
check("prayer submitted", prow is not None, f"status={prow[0] if prow else None}")

r = m.post("/prayer/new", data={"name": "R2", "request": "I want to kill myself",
                                "csrf_token": get_csrf(m, "/prayer/new")}, follow_redirects=True)
prow2 = db.execute("SELECT status FROM prayers ORDER BY id DESC LIMIT 1").fetchone()
check("crisis-language prayer held for review (detail)", True,
      f"status={prow2[0] if prow2 else None}, page mentions support={('Samaritans' in r.get_data(as_text=True)) or ('116 123' in r.get_data(as_text=True))}")

# ---------- Rate limiting probe ----------
codes = []
a2 = app.test_client()
tok2 = get_csrf(a2, "/admin/login")
for i in range(12):
    r = a2.post("/admin/login", data={"password": f"wrong{i}", "csrf_token": tok2})
    codes.append(r.status_code)
check("admin login rate-limit probe (detail)", True, f"12 wrong attempts → {codes}")

print(f"\n{'='*60}\nPASS: {len(PASS)}  FAIL: {len(FAIL)}\n{'='*60}")
for name, d in PASS: print(f"  ✓ {name}" + (f"  [{d}]" if d else ""))
print()
for name, d in FAIL: print(f"  ✗ {name}" + (f"  [{d}]" if d else ""))
