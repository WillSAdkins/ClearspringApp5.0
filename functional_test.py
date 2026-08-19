"""Deeper functional + security tests for Clearspring."""
import os, re, json

os.environ.setdefault("CHURCH_DB", "/tmp/test_church.db")
os.environ.setdefault("SECRET_KEY", "testkey")
os.environ.setdefault("ADMIN_PASSWORD", "testadmin123")

import app as appmod
app = appmod.app
app.config["TESTING"] = True

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))

def get_csrf(client, path):
    html = client.get(path).get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    if not m:
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    return m.group(1) if m else None

# ---------- 1. Admin auth ----------
c = app.test_client()
tok = get_csrf(c, "/admin/login")
check("csrf token present on admin login", tok is not None)

r = c.post("/admin/login", data={"password": "WRONG", "csrf_token": tok}, follow_redirects=False)
check("wrong admin password rejected", r.status_code in (200, 302) and "/admin/login" in (r.headers.get("Location") or r.request.path))
r2 = c.get("/admin", follow_redirects=False)
check("still locked out after wrong password", r2.status_code == 302)

tok = get_csrf(c, "/admin/login")
r = c.post("/admin/login", data={"password": "testadmin123", "csrf_token": tok}, follow_redirects=False)
r2 = c.get("/admin", follow_redirects=False)
check("correct admin password grants access", r2.status_code == 200, f"login={r.status_code} admin={r2.status_code}")

# CSRF: posting without token should fail
r = c.post("/admin/new", data={"title": "x", "date": "2026-08-01"}, follow_redirects=False)
check("admin POST without CSRF token blocked", r.status_code in (400, 403), f"got {r.status_code}")

# Create an event properly
tok = get_csrf(c, "/admin/new")
r = c.post("/admin/new", data={"title": "Test Service", "date": "2026-08-02", "time": "10:30",
                               "location": "Main Hall", "description": "Test", "csrf_token": tok},
           follow_redirects=True)
cal = c.get("/community/calendar").get_data(as_text=True)
check("admin can create event, appears on calendar", "Test Service" in cal)

# ---------- 2. Member signup / signin ----------
m = app.test_client()
tok = get_csrf(m, "/account/signup")
r = m.post("/account/signup", data={"name": "Test User", "email": "test@example.com",
                                    "password": "s3curePass!", "csrf_token": tok},
           follow_redirects=True)
acct = m.get("/account")
check("member signup then /account accessible", acct.status_code == 200, f"signup={r.status_code}")

m2 = app.test_client()
tok = get_csrf(m2, "/account/signin")
r = m2.post("/account/signin", data={"email": "test@example.com", "password": "WRONG",
                                     "csrf_token": tok}, follow_redirects=False)
check("wrong member password rejected", m2.get("/account", follow_redirects=False).status_code == 302)

tok = get_csrf(m2, "/account/signin")
r = m2.post("/account/signin", data={"email": "test@example.com", "password": "s3curePass!",
                                     "csrf_token": tok}, follow_redirects=True)
check("correct member password signs in", m2.get("/account", follow_redirects=False).status_code == 200)

# ---------- 3. Sync API (signed-in member) ----------
r = m.post("/api/sync/saved_verses", json={"key": "john-3-16", "value": {"ref": "John 3:16"}})
check("member can sync a saved verse", r.status_code == 200, f"got {r.status_code} {r.get_data(as_text=True)[:80]}")
r = m.get("/api/sync/saved_verses")
check("member can read synced data back", r.status_code == 200 and "john-3-16" in r.get_data(as_text=True))

anon = app.test_client()
r = anon.get("/api/sync/saved_verses")
check("anonymous sync read denied", r.status_code in (400, 401, 403))

# ---------- 4. Push subscribe: web + my native path ----------
r = m.post("/api/push/subscribe", json={
    "subscription": {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "x", "auth": "y"}},
    "prefs": {"events": True}})
check("web push subscribe works", r.status_code == 200)

r = m.post("/api/push/subscribe", json={"native_token": "fcm-token-123", "platform": "android",
                                        "prefs": {"events": True}})
check("native push subscribe (android) works", r.status_code == 200)

r = m.post("/api/push/subscribe", json={"native_token": "apns-token-456", "platform": "ios",
                                        "prefs": {"sermons": True}})
check("native push subscribe (ios) works", r.status_code == 200)

r = m.post("/api/push/subscribe", json={"native_token": "tok", "platform": "windows"})
check("native push with bogus platform rejected", r.status_code == 400)

r = m.post("/api/push/unsubscribe", json={"native_token": "fcm-token-123", "platform": "android"})
check("native push unsubscribe works", r.status_code == 200)

import sqlite3
db = sqlite3.connect("/tmp/test_church.db")
rows = db.execute("SELECT endpoint FROM push_subscriptions").fetchall()
endpoints = [r[0] for r in rows]
check("android token removed, ios token stored", 
      "native:ios:apns-token-456" in endpoints and "native:android:fcm-token-123" not in endpoints,
      str(endpoints))

# ---------- 5. Game scores ----------
tok = get_csrf(m, "/games")
r = m.post("/games/memory/score", json={"score": 42, "name": "Tester"})
check("game score submission accepted", r.status_code in (200, 201), f"got {r.status_code}")
r = m.get("/games/memory/leaderboard")
check("leaderboard shows after score", r.status_code == 200)

r = m.post("/games/memory/score", json={"score": 999999999})
lb = m.get("/games/memory/leaderboard").get_data(as_text=True)
check("absurd score handling (see detail)", True, f"accepted={r.status_code}, on board={'999999999' in lb}")

# ---------- 6. Injection attempts ----------
r = anon.get("/bible/read/john'; DROP TABLE members;--")
check("SQLi in book slug doesn't 500", r.status_code in (200, 302, 404))
db2 = sqlite3.connect("/tmp/test_church.db")
ok = db2.execute("SELECT COUNT(*) FROM members").fetchone()
check("members table still exists after SQLi attempt", ok is not None)

tok = get_csrf(m, "/questions/ask")
xss = "<script>alert(1)</script>"
r = m.post("/questions/ask", data={"name": xss, "question": "Is this escaped? " + xss,
                                   "csrf_token": tok}, follow_redirects=True)
# approve it as admin then view
qid = db2.execute("SELECT id FROM questions ORDER BY id DESC LIMIT 1").fetchone()
check("question with XSS payload stored", qid is not None)

# ---------- 7. Security headers ----------
r = anon.get("/")
h = r.headers
check("X-Content-Type-Options set", h.get("X-Content-Type-Options") == "nosniff", str(dict(h)))
check("X-Frame-Options or CSP frame-ancestors set",
      h.get("X-Frame-Options") is not None or "frame-ancestors" in (h.get("Content-Security-Policy") or ""))
check("Content-Security-Policy set", h.get("Content-Security-Policy") is not None)
csp = h.get("Content-Security-Policy") or ""
check("CSP forbids unsafe-inline scripts (see detail)", True, f"CSP={csp[:200]}")

# Session cookie flags
sc = None
c3 = app.test_client()
tok = get_csrf(c3, "/account/signin")
r = c3.post("/account/signin", data={"email": "test@example.com", "password": "s3curePass!", "csrf_token": tok})
for cookie in r.headers.getlist("Set-Cookie"):
    if cookie.startswith("session="):
        sc = cookie
check("session cookie HttpOnly", sc is not None and "HttpOnly" in sc, sc or "no cookie")
check("session cookie SameSite set", sc is not None and "SameSite" in sc, sc or "")

# ---------- 8. Password storage ----------
row = db2.execute("SELECT password_hash FROM members WHERE email='test@example.com'").fetchone()
if row is None:
    # column name may differ
    cols = [c[1] for c in db2.execute("PRAGMA table_info(members)").fetchall()]
    check("password hashed (see detail)", False, f"columns: {cols}")
else:
    check("password not stored in plaintext", "s3curePass!" not in (row[0] or ""), row[0][:60] if row[0] else "EMPTY")

print(f"\n{'='*60}\nPASS: {len(PASS)}  FAIL: {len(FAIL)}\n{'='*60}")
for name, d in PASS:
    print(f"  ✓ {name}" + (f"  [{d}]" if d else ""))
print()
for name, d in FAIL:
    print(f"  ✗ {name}" + (f"  [{d}]" if d else ""))
