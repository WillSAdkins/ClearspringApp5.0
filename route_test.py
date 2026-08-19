"""Smoke-test every route in the Clearspring app with Flask's test client."""
import os, re, sys, json

os.environ.setdefault("CHURCH_DB", "/tmp/test_church.db")
os.environ.setdefault("SECRET_KEY", "testkey")
os.environ.setdefault("ADMIN_PASSWORD", "testadmin123")

import app as appmod
app = appmod.app
app.config["TESTING"] = True

client = client_anon = app.test_client()

results = {"ok": [], "redirect": [], "client_err": [], "server_err": []}

# Collect every GET-able rule with no url params, plus fill in simple int params
rules = []
for rule in app.url_map.iter_rules():
    if "GET" not in rule.methods:
        continue
    if rule.endpoint == "static":
        continue
    url = str(rule)
    # substitute simple params with plausible values
    url = re.sub(r"<int:[^>]+>", "1", url)
    url = re.sub(r"<game_key>", "memory", url)
    url = re.sub(r"<plan_slug>", "gospel-in-90", url)
    url = re.sub(r"<book_slug>", "john", url)
    url = re.sub(r"<slug>", "youth", url)
    url = re.sub(r"<kind>", "saved_verses", url)
    url = re.sub(r"<token>", "badtoken", url)
    rules.append(url)

for url in sorted(set(rules)):
    try:
        r = client.get(url, follow_redirects=False)
        code = r.status_code
    except Exception as e:
        results["server_err"].append((url, f"EXCEPTION {type(e).__name__}: {e}"))
        continue
    if code >= 500:
        results["server_err"].append((url, code))
    elif code in (301, 302, 303, 307, 308):
        results["redirect"].append((url, code, r.headers.get("Location", "?")))
    elif code >= 400:
        results["client_err"].append((url, code))
    else:
        results["ok"].append((url, code))

print(f"OK ({len(results['ok'])}):")
for u, c in results["ok"]:
    print(f"  {c} {u}")
print(f"\nREDIRECTS ({len(results['redirect'])}):")
for u, c, loc in results["redirect"]:
    print(f"  {c} {u} -> {loc}")
print(f"\nCLIENT ERRORS ({len(results['client_err'])}):")
for u, c in results["client_err"]:
    print(f"  {c} {u}")
print(f"\nSERVER ERRORS ({len(results['server_err'])}):")
for u, c in results["server_err"]:
    print(f"  {c} {u}")
