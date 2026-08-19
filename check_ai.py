"""
check_ai.py — works out why the Bible study assistant isn't showing.

Run it from the app folder:

    Windows :  check.bat
    Mac/Linux: python3 check_ai.py

It checks each link in the chain and stops at the first broken one, telling
you exactly what to change. It never prints your key.
"""

import os
import sys
import json

OK = "  [OK]  "
NO = "  [--]  "
BAD = "  [X]   "


def line():
    print("  " + "-" * 56)


def fail(msg, *fixes):
    print()
    print(BAD + msg)
    print()
    for f in fixes:
        print("        " + f)
    print()
    sys.exit(1)


print()
print("  Clearspring — study assistant check")
line()

# ---------------------------------------------------------------- 1. folder
if not os.path.exists("app.py"):
    fail(
        "This isn't the app folder.",
        "Put check_ai.py next to app.py and run it from there.",
    )
print(OK + "Found app.py, running from the right folder")

# ------------------------------------------------------------ 2. settings
on_windows = os.name == "nt"
if on_windows:
    if os.path.exists("settings.bat"):
        print(OK + "settings.bat exists")
        with open("settings.bat", "r", errors="replace") as fh:
            content = fh.read()

        active = [
            ln.strip() for ln in content.splitlines()
            if "GEMINI_API_KEY" in ln and not ln.strip().upper().startswith("REM")
        ]
        commented = [
            ln.strip() for ln in content.splitlines()
            if "GEMINI_API_KEY" in ln and ln.strip().upper().startswith("REM")
        ]

        if not active and commented:
            fail(
                "The GEMINI_API_KEY line in settings.bat is still commented out.",
                "Open settings.bat and find this line near the bottom:",
                "",
                "    REM  set GEMINI_API_KEY=your-key-here",
                "",
                "Delete the 'REM  ' from the front and put your real key in:",
                "",
                "    set GEMINI_API_KEY=AIzaSy...",
                "",
                "Save the file, then run this check again.",
            )
        if not active and not commented:
            fail(
                "settings.bat has no GEMINI_API_KEY line at all.",
                "Add this line at the end of settings.bat:",
                "",
                "    set GEMINI_API_KEY=AIzaSy...your-key",
            )

        raw = active[0]
        print(OK + "settings.bat has an active GEMINI_API_KEY line")

        # Common batch-file mistakes that produce a variable that never matches.
        after_set = raw[3:].strip() if raw.lower().startswith("set") else raw
        name_part = after_set.split("=", 1)[0] if "=" in after_set else after_set
        if name_part != name_part.strip():
            fail(
                "There's a space around the '=' in settings.bat.",
                "In a .bat file 'set NAME = value' creates a variable whose",
                "name ends with a space, so nothing ever finds it.",
                "",
                "Write it with no spaces:  set GEMINI_API_KEY=AIzaSy...",
            )
        value_part = after_set.split("=", 1)[1] if "=" in after_set else ""
        if value_part.startswith('"') or value_part.startswith("'"):
            fail(
                "The key in settings.bat is wrapped in quotes.",
                "Batch files treat the quotes as part of the value.",
                "",
                "Remove them:  set GEMINI_API_KEY=AIzaSy...",
            )
    else:
        print(NO + "No settings.bat (that's OK if you set the variable another way)")

# ------------------------------------------------------- 3. is it loaded?
key = os.environ.get("GEMINI_API_KEY", "").strip()

if not key:
    if on_windows:
        fail(
            "GEMINI_API_KEY isn't set in this window.",
            "settings.bat is only loaded by run.bat, so running this check",
            "on its own won't see it. Use check.bat instead — it loads your",
            "settings first.",
            "",
            "If you already used check.bat, then run.bat isn't loading",
            "settings.bat. Check the file is named exactly 'settings.bat'",
            "and sits in the same folder as run.bat.",
        )
    fail(
        "GEMINI_API_KEY isn't set in this terminal.",
        "Set it, then run this again in the SAME window:",
        "",
        '    export GEMINI_API_KEY="AIzaSy...your-key"',
    )

print(OK + f"GEMINI_API_KEY is set ({len(key)} characters)")

# ------------------------------------------------------- 4. does it look right?
if key in ("your-key-here", "AIzaSy...", "your-key"):
    fail(
        "The placeholder text is still there instead of a real key.",
        "Get one free from https://aistudio.google.com/apikey",
    )

if " " in key:
    fail(
        "The key contains a space, so it won't be accepted.",
        "Re-copy it from Google AI Studio without any line breaks.",
    )

if key.startswith("AIza") and len(key) == 39:
    print(OK + "Key format looks right (classic AIza key)")
elif key.startswith("AQ."):
    print(OK + "Key format looks right (newer AQ. key)")
else:
    print(NO + f"Unfamiliar key format ({len(key)} chars, begins '{key[:4]}')")
    print("        Google uses two formats: 39-char keys starting AIza,")
    print("        and newer ones starting AQ. — yours matches neither,")
    print("        but the live test below is what actually matters.")

# ------------------------------------------------------- 5. app agrees?
try:
    import study_assistant
except Exception as e:
    fail(f"Couldn't load study_assistant.py: {e}")

if not study_assistant.is_available():
    fail(
        "The app still reports the assistant as unavailable.",
        "The key is in your environment but study_assistant.py can't see it.",
        "This usually means the app was started before the key was set.",
    )
print(OK + f"App reports assistant ON (will try: {study_assistant.current_model()})")

# ------------------------------------------------------- 6. real API call
#
# Deliberately bypasses study_assistant.ask(). That function turns every
# failure into a gentle sentence for visitors, which is right for them and
# useless here — "the daily limit may have been reached" is what it says for
# any 429, including ones that have nothing to do with quota. We want the
# actual response.
print()
print("  Asking Google directly...")
line()

import urllib.request
import urllib.error

payload = json.dumps({
    "contents": [{"role": "user", "parts": [{"text": "Say the word: working"}]}],
}).encode("utf-8")

candidates = ([study_assistant._MODEL_OVERRIDE] if study_assistant._MODEL_OVERRIDE
              else study_assistant.MODEL_CANDIDATES)

worked = None
problems = []

for model in candidates:
    req = urllib.request.Request(
        study_assistant.GEMINI_URL.format(model=model),
        data=payload,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        worked = (model, raw)
        print(f"  [OK]   {model}")
        break
    except urllib.error.HTTPError as e:
        detail, status = "", ""
        try:
            body = json.loads(e.read().decode("utf-8"))
            err = body.get("error", {})
            detail = err.get("message", "")
            status = err.get("status", "")
        except Exception:
            pass
        short = "retired / not available" if e.code == 404 else f"HTTP {e.code} {status}"
        print(f"  [--]   {model} — {short}")
        problems.append((model, e.code, status, detail))
        continue
    except urllib.error.URLError as e:
        print()
        print(BAD + "Couldn't reach Google at all.")
        print(f"        {e.reason}")
        print()
        print("        Something is blocking generativelanguage.googleapis.com —")
        print("        usually a firewall, proxy or antivirus web filter.")
        print()
        sys.exit(1)

line()

if worked:
    model, raw = worked
    print()
    print(OK + "The study assistant is working.")
    print()
    print(f"        Model in use: {model}")
    try:
        said = raw["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f"        It replied: {said[:90]}")
    except Exception:
        pass
    print()
    print("        Start the app with run.bat, open any Bible chapter, and")
    print("        look for 'Study help' at the bottom right.")
    print()
else:
    print()
    print(BAD + "No model would answer.")
    print()
    for model, code, status, detail in problems:
        print(f"        {model}  ->  HTTP {code} {status}")
        if detail:
            for chunk in [detail[i:i + 58] for i in range(0, len(detail), 58)]:
                print("            " + chunk)
    print()

    codes = {c for _, c, _, _ in problems}
    if codes == {404}:
        print("        >> Every model returned 'not found'. Google retires")
        print("           models faster than announced. Check the current")
        print("           list at ai.google.dev/gemini-api/docs/models and")
        print("           set GEMINI_MODEL in settings.bat to a live one.")
    elif 429 in codes:
        print("        >> Quota refused. Note that Google's Gemini free tier")
        print("           is NOT available in the UK, EU or Switzerland. From")
        print("           the UK you generally need billing enabled on the")
        print("           Google Cloud project behind the key.")
    elif codes & {401, 403}:
        print("        >> The key was rejected. Create a fresh one at")
        print("           https://aistudio.google.com/apikey")
    print()
    sys.exit(1)
