"""Round 3: correct names + abuse probes (payload size, magic links, account deletion)."""
import os, re, json, sqlite3

os.environ.setdefault("CHURCH_DB", "/tmp/test_church.db")
os.environ.setdefault("SECRET_KEY", "testkey")
os.environ.setdefault("ADMIN_PASSWORD", "testadmin123")

import app as appmod
app = appmod.app
app.config["TESTING"] = True

PASS, FAIL, NOTE = [], [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
def note(name, detail):
    NOTE.append((name, detail))

def get_csrf(client, path="/"):
    html = client.get(path).get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else None

def jpost(client, url, payload, tok):
    return client.post(url, json=payload, headers={"X-CSRF-Token": tok})

db = sqlite3.connect("/tmp/test_church.db")

# ---------- confirmations ----------
c = app.test_client()
tok = get_csrf(c, "/admin/login")
c.post("/admin/login", data={"password": "testadmin123", "csrf_token": tok})
cal = c.get("/community/calendar?month=2026-08").get_data(as_text=True)
check("event visible on its month", "Round2 Service" in cal)

m = app.test_client()
tok = get_csrf(m, "/account/signup")
m.post("/account/signup", data={"name": "R3 User", "email": "r3@example.com",
                                "password": "s3curePass!", "csrf_token": tok})
tok = get_csrf(m, "/account")

r = jpost(m, "/api/sync/verse", {"key": "john-3-16", "value": {"ref": "John 3:16"}}, tok)
check("sync 'verse' kind works", r.status_code == 200, r.get_data(as_text=True)[:60])
r = m.get("/api/sync/verse")
check("sync read-back", r.status_code == 200 and "john-3-16" in r.get_data(as_text=True))

r = jpost(m, "/games/memory_game/score", {"score": 12, "name": "T"}, tok)
check("score with real game key", r.status_code == 200, r.get_data(as_text=True)[:60])
r = jpost(m, "/games/memory_game/score", {"score": -5}, tok)
note("negative score (moves game)", f"{r.status_code} {r.get_data(as_text=True)[:60]}")
r = jpost(m, "/games/memory_game/score", {"score": 999999999}, tok)
note("absurd score", f"{r.status_code} {r.get_data(as_text=True)[:60]}")

tok_q = get_csrf(m, "/questions/ask")
m.post("/questions/ask", data={"question_text": "XSS? <script>alert(2)</script>",
                               "author_name": "<b>bold</b>", "csrf_token": tok_q},
       follow_redirects=True)
q = db.execute("SELECT id FROM questions ORDER BY id DESC LIMIT 1").fetchone()
check("question stored with real field name", q is not None)
if q:
    tok_a = get_csrf(c, "/admin/questions")
    c.post(f"/admin/questions/{q[0]}/answer", data={"answer": "Answer", "csrf_token": tok_a})
    pub = m.get("/questions").get_data(as_text=True)
    check("XSS escaped on public questions page", "<script>alert(2)</script>" not in pub)

tok_p = get_csrf(m, "/prayer/new")
m.post("/prayer/new", data={"body": "Please pray for my interview", "author_name": "R3",
                            "visibility": "public", "csrf_token": tok_p}, follow_redirects=True)
p = db.execute("SELECT status, body FROM prayers ORDER BY id DESC LIMIT 1").fetchone()
check("prayer stored", p is not None, f"status={p[0] if p else None}")

r = m.post("/prayer/new", data={"body": "I want to end my life", "author_name": "R3",
                                "visibility": "public",
                                "csrf_token": get_csrf(m, "/prayer/new")}, follow_redirects=True)
p2 = db.execute("SELECT status FROM prayers ORDER BY id DESC LIMIT 1").fetchone()
check("crisis prayer auto-held (not public)", p2 is not None and p2[0] == "held", f"status={p2[0] if p2 else None}")
wall = m.get("/prayer").get_data(as_text=True)
check("held prayer NOT on public wall", "end my life" not in wall)

# honeypot actually blocks
before = db.execute("SELECT COUNT(*) FROM prayers").fetchone()[0]
m.post("/prayer/new", data={"body": "spam", "website": "http://spam.com",
                            "csrf_token": get_csrf(m, "/prayer/new")}, follow_redirects=True)
after = db.execute("SELECT COUNT(*) FROM prayers").fetchone()[0]
check("honeypot blocks bot submissions", before == after)

# ---------- abuse probes ----------
# 1. Sync payload size: can a member store megabytes?
big = "x" * 2_000_000
r = jpost(m, "/api/sync/note", {"key": "big", "value": {"v": big}}, tok)
note("2MB sync payload", f"status={r.status_code}")
row = db.execute("SELECT LENGTH(payload) FROM member_data ORDER BY id DESC LIMIT 1").fetchone()
note("stored size", f"{row[0] if row else 'n/a'} bytes")

# 2. Sync key count: unbounded rows per member?
for i in range(60):
    jpost(m, "/api/sync/note", {"key": f"k{i}", "value": {"v": i}}, tok)
n = db.execute("SELECT COUNT(*) FROM member_data").fetchall()
note("rows after 60 keys", str(n))

# 3. Magic link token: entropy + expiry
r = m.post("/account/link", data={"email": "r3@example.com",
                                  "csrf_token": get_csrf(m, "/account/link")}, follow_redirects=True)
mem = db.execute("SELECT * FROM members WHERE email='r3@example.com'").fetchone()
cols = [d[1] for d in db.execute("PRAGMA table_info(members)").fetchall()]
note("members columns", str(cols))
tokrow = db.execute("SELECT magic_token, magic_expires FROM members WHERE email='r3@example.com'").fetchone() \
    if "magic_token" in cols else None
if tokrow:
    note("magic token len/expiry", f"len={len(tokrow[0]) if tokrow[0] else 0} expires={tokrow[1]}")
    check("magic token reasonably long", tokrow[0] is None or len(tokrow[0]) >= 32)

# 4. Account deletion available? (Apple requirement)
acct_html = m.get("/account").get_data(as_text=True)
has_delete = ("delete" in acct_html.lower() and "account" in acct_html.lower())
check("account deletion present on /account (Apple 5.1.1(v))", has_delete,
      "no delete control found" if not has_delete else "")
del_routes = [str(r) for r in app.url_map.iter_rules() if "delete" in str(r) and "account" in str(r)]
note("account-deletion routes", str(del_routes) or "none")

# 5. Study assistant (AI) endpoint — exposed without auth? rate limited?
r = jpost(m, "/api/study/ask", {"question": "What does John 3:16 mean?"}, tok)
note("study ask (member)", f"{r.status_code} {r.get_data(as_text=True)[:100]}")
anon = app.test_client()
tok_anon = get_csrf(anon, "/bible")
r = jpost(anon, "/api/study/ask", {"question": "hi"}, tok_anon)
note("study ask (anon)", f"{r.status_code} {r.get_data(as_text=True)[:100]}")

# 6. Backup endpoint: admin only (verified earlier via redirect) — check restore validation exists
src = open("app.py").read()
check("restore validates uploaded DB before replacing", "integrity_check" in src or "PRAGMA" in src,
      "no integrity check found")

# 7. SECRET_KEY fallback — what happens if env var missing?
m_sk = re.search(r"SECRET_KEY.{0,200}", src)
note("secret key handling", src[m_sk.start():m_sk.start()+300].replace("\n", " ")[:250] if m_sk else "not found")

print(f"\n{'='*60}\nPASS: {len(PASS)}  FAIL: {len(FAIL)}\n{'='*60}")
for name, d in PASS: print(f"  ✓ {name}" + (f"  [{d}]" if d else ""))
print()
for name, d in FAIL: print(f"  ✗ {name}" + (f"  [{d}]" if d else ""))
print("\nNOTES:")
for name, d in NOTE: print(f"  • {name}: {d}")
