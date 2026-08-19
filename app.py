import os
import json
import re
import shutil
from urllib.parse import quote_plus
import calendar as calendar_mod
import sqlite3
import secrets
from datetime import datetime, date, timedelta
from functools import wraps, lru_cache

import requests
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, Response, abort, make_response, send_from_directory, send_file, jsonify

from recurrence import occurrences
from ics import build_calendar
from trivia_data import TRIVIA_LADDER, TRIVIA_FOOTBALL
from verses_data import VERSES
from bible_books import ALL_BOOKS, OLD_TESTAMENT, NEW_TESTAMENT, BOOKS_BY_SLUG, parse_reference
from prayer_safety import screen as prayer_screen
from sermon_media import embed_url, thumbnail_url, format_duration, build_podcast_feed
from reading_plans import get_plan, plan_summary
from devotionals_data import STARTER_DEVOTIONALS
from resources_data import STARTER_RESOURCES, RESOURCE_CATEGORIES
from notifications import (
    NOTIFICATION_TYPES,
    TYPE_KEYS,
    VAPID_PUBLIC_KEY,
    is_configured as push_is_configured,
    native_is_configured as native_push_is_configured,
    send_to_subscription as send_push,
)
import achievements
import bible_sources
from study_assistant import (
    is_available as study_available,
    ask as study_ask_ai,
)
import emailer
from auth import (
    valid_email, normalise_email, password_problem,
    hash_password, verify_password,
    new_token, hash_token, token_expiry, token_expired,
    SESSION_DAYS,
)

CHURCH_NAME = "Clearspring"

# The seven ministry areas. `safeguarded` marks those working with under-18s —
# these are restricted to role-based contacts only (no personal names or mobiles),
# so a volunteer's private details can never be published on a page children see.
DEFAULT_MINISTRIES = [
    {"slug": "kids", "name": "Kids", "tagline": "Sundays for children up to 11", "safeguarded": True},
    {"slug": "youth", "name": "Youth", "tagline": "Ages 11–18", "safeguarded": True},
    {"slug": "young-adults", "name": "Young Adults", "tagline": "Late teens to thirties", "safeguarded": False},
    {"slug": "men", "name": "Men", "tagline": "Fellowship, breakfasts and study", "safeguarded": False},
    {"slug": "women", "name": "Women", "tagline": "Fellowship, study and support", "safeguarded": False},
    {"slug": "seniors", "name": "Seniors", "tagline": "Friendship and care for our older members", "safeguarded": False},
    {"slug": "missions", "name": "Missions", "tagline": "Our work at home and overseas", "safeguarded": False},
]

SAFEGUARDED_SLUGS = {m["slug"] for m in DEFAULT_MINISTRIES if m["safeguarded"]}

app = Flask(__name__)
def _secret_key():
    """Session signing key.

    A predictable key means anyone can forge a session cookie, which would
    undo both the admin login and the CSRF protection. If one isn't supplied,
    generate a random one and keep it alongside the database so sessions
    survive a restart without a known value ever being shipped in the code.
    """
    from_env = os.environ.get("SECRET_KEY")
    if from_env:
        return from_env

    key_path = os.path.join(os.path.dirname(DB_PATH), "secret_key")
    try:
        if os.path.exists(key_path):
            with open(key_path) as f:
                existing = f.read().strip()
                if existing:
                    return existing
        generated = secrets.token_urlsafe(48)
        with open(key_path, "w") as f:
            f.write(generated)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        return generated
    except OSError:
        # Can't persist one — fall back to a per-run key. Sessions won't
        # survive a restart, but they still can't be forged.
        return secrets.token_urlsafe(48)


app.permanent_session_lifetime = timedelta(days=SESSION_DAYS)


@app.template_filter("pretty_date")
def pretty_date(value):
    try:
        d = datetime.strptime(value, "%Y-%m-%d")
    except (ValueError, TypeError):
        return value
    return f"{d.strftime('%A, %B')} {d.day}"


@app.template_filter("pretty_datetime")
def pretty_datetime(value):
    try:
        d = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return value
    return f"{d.strftime('%B')} {d.day}, {d.strftime('%Y')}"


@app.template_filter("pretty_date_short_day")
def pretty_date_short_day(value):
    try:
        d = datetime.strptime(value, "%Y-%m-%d")
    except (ValueError, TypeError):
        return value
    return d.strftime("%a")


@app.template_filter("pretty_date_num")
def pretty_date_num(value):
    try:
        d = datetime.strptime(value, "%Y-%m-%d")
    except (ValueError, TypeError):
        return value
    return str(d.day)


@app.template_filter("gbp")
def gbp(pence):
    """Format pence as a readable pounds figure, e.g. 250000 -> £2,500."""
    if pence is None:
        return ""
    pounds = pence / 100
    if pounds == int(pounds):
        return f"£{int(pounds):,}"
    return f"£{pounds:,.2f}"


@app.template_filter("excerpt")
def excerpt(text, length=140):
    """Truncate to roughly `length` characters without cutting a word in half."""
    if not text or len(text) <= length:
        return text
    cut = text[:length].rsplit(" ", 1)[0]
    return f"{cut}…"

def _resolve_db_path():
    """Work out where the database should live.

    The database deliberately sits OUTSIDE the app folder so that replacing the
    app with a new version never touches your data. Order of preference:

      1. CHURCH_DB env var — explicit override, useful on a server
      2. A 'church-data' folder next to the app folder
      3. The app folder itself — last resort, e.g. read-only parent

    If a database already exists inside the app folder from an older version,
    it is moved to the new location automatically the first time this runs.
    """
    explicit = os.environ.get("CHURCH_DB")
    if explicit:
        path = os.path.abspath(explicit)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    app_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(os.path.dirname(app_dir), "church-data")

    try:
        os.makedirs(data_dir, exist_ok=True)
        target = os.path.join(data_dir, "church.db")
    except OSError:
        # Can't create a sibling folder — fall back to the app folder.
        return os.path.join(app_dir, "church.db")

    # One-time migration from the old in-app location.
    legacy = os.path.join(app_dir, "church.db")
    if os.path.exists(legacy) and not os.path.exists(target):
        try:
            import shutil
            shutil.copy2(legacy, target)
            shutil.move(legacy, legacy + ".migrated")
            print(f"Moved your existing data to {target}")
            print(f"(The old file is kept as {os.path.basename(legacy)}.migrated)")
        except OSError as e:
            print(f"Couldn't move existing database: {e}")
            return legacy

    return target


# True when this is a real deployment rather than someone running it locally.
# Defined early because both the storage check and the cookie policy need it.
_HTTPS_ONLY = os.environ.get("HTTPS_ONLY") == "1" or os.environ.get("RENDER") == "1"

DB_PATH = _resolve_db_path()


def _assert_persistent_storage():
    """On a real deployment, refuse to run from an ephemeral filesystem.

    The fallback in _resolve_db_path() is deliberately forgiving so the app
    always starts locally. In production that forgiveness is dangerous: if
    CHURCH_DB is unset or misspelled, the app writes to the container's own
    filesystem, works perfectly, and then loses every account, prayer and
    sermon the next time the service redeploys. Nothing warns you.

    So in production we require the database to sit on a mounted disk.
    """
    if not _HTTPS_ONLY:
        return

    explicit = os.environ.get("CHURCH_DB")
    if not explicit:
        raise RuntimeError(
            "CHURCH_DB is not set. On a deployed instance the database must "
            "live on a mounted persistent disk (e.g. /var/data/church.db), or "
            "all data is lost on the next deploy."
        )

    parent = os.path.dirname(os.path.abspath(explicit))

    # Directory existence is not enough. _resolve_db_path() calls makedirs(),
    # so if the disk failed to mount we will have cheerfully created an
    # ordinary folder at the same path on the container's own filesystem —
    # which looks identical and is wiped on the next deploy. Check that the
    # path actually sits on a mounted volume.
    probe_dir = parent
    on_mount = False
    while probe_dir and probe_dir != "/":
        if os.path.ismount(probe_dir):
            on_mount = True
            break
        probe_dir = os.path.dirname(probe_dir)

    if not on_mount:
        # This check is a safety net, not gospel. Mount detection can in
        # principle disagree with reality on some hosts, and a false positive
        # here would take a working site offline — which is worse than the
        # problem it guards against. So there is a documented way past it.
        if os.environ.get("SKIP_DISK_CHECK") == "1":
            print(
                "WARNING: CHURCH_DB is not on a detected mount point, and "
                "SKIP_DISK_CHECK=1 is set, so starting anyway. If the disk "
                "really isn't mounted, all data will be lost on the next "
                "deploy. Check /admin/status and take a backup.",
                flush=True,
            )
        else:
            raise RuntimeError(
                f"CHURCH_DB points at {parent}, which is not on a mounted "
                "disk. The persistent disk is probably missing, or its mount "
                "path doesn't match CHURCH_DB. Data written here is lost on "
                "redeploy.\n\n"
                "In Render: Settings -> Disks. The mount path must match the "
                "folder in CHURCH_DB (e.g. disk at /var/data, and "
                "CHURCH_DB=/var/data/church.db).\n\n"
                "If you are certain the disk is fine and this check is wrong, "
                "set SKIP_DISK_CHECK=1 to start anyway."
            )

    # A writable check catches a disk that exists but is mounted read-only.
    probe = os.path.join(parent, ".write-probe")
    try:
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
    except OSError as e:
        raise RuntimeError(
            f"Cannot write to {parent} ({e}). The database directory must be "
            "writable, or nothing will be saved."
        )


_assert_persistent_storage()

app.secret_key = _secret_key()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")

# On a real deployment an unset admin password means the entire admin area is
# open to anyone who guesses "changeme". Fail loudly at startup instead of
# quietly serving a wide-open site.
if _HTTPS_ONLY and ADMIN_PASSWORD == "changeme":
    raise RuntimeError(
        "ADMIN_PASSWORD is unset (or still 'changeme') on a production "
        "deployment. Set it in your environment variables before starting."
    )

# Simple in-memory rate limit on the admin login. Held per-process, which is
# fine for a single worker; swap for Flask-Limiter + Redis if this ever runs
# behind several.
_login_attempts = {}
LOGIN_MAX_ATTEMPTS = 8
LOGIN_WINDOW_SECONDS = 300


def _login_rate_limited(ip):
    now = datetime.now().timestamp()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
    _login_attempts[ip] = attempts
    return len(attempts) >= LOGIN_MAX_ATTEMPTS


def _record_login_failure(ip):
    _login_attempts.setdefault(ip, []).append(datetime.now().timestamp())


# Generic per-IP limiter for anything that sends email or costs money to run.
# Session-based limits are trivially bypassed by clearing cookies; this is
# keyed on address instead.
_action_hits = {}


def rate_limited(bucket, ip, limit, window_seconds):
    """True if this IP has already used up its allowance for this action."""
    now = datetime.now().timestamp()
    key = (bucket, ip)
    hits = [t for t in _action_hits.get(key, []) if now - t < window_seconds]

    # Stop the dict growing without bound on a long-running process.
    if len(_action_hits) > 5000:
        _action_hits.clear()

    if len(hits) >= limit:
        _action_hits[key] = hits
        return True
    hits.append(now)
    _action_hits[key] = hits
    return False


def client_ip():
    """Caller's address, trusting Render's proxy header when present."""
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"

# Cookie hardening. Lax lets ordinary links into the site work while blocking
# cookies on cross-site POSTs, which is the shape a CSRF attack takes.
#
# Secure is decided once at startup from the environment. It must NOT be set
# per-request: app.config is global and shared by every worker thread, so
# mutating it mid-request is a race, and one visitor's connection type would
# silently change the cookie policy for everyone else.

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,      # JavaScript can't read the session cookie
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=_HTTPS_ONLY,
    # Cap request bodies. Without this the database restore upload will happily
    # read an arbitrarily large file straight into memory.
    MAX_CONTENT_LENGTH=32 * 1024 * 1024,   # 32 MB
)


@app.after_request
def security_headers(response):
    """Standard protective headers.

    The content security policy is the substantive one: even if a script did
    somehow get injected, the browser would refuse to run it unless it came
    from somewhere on this list.
    """
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
    )

    # Only send HSTS over a genuinely secure connection, never on local HTTP.
    if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )

    # Skip CSP on the podcast feed and other non-HTML responses.
    if response.mimetype == "text/html":
        # The native iOS/Android shell runs the page inside a WKWebView /
        # WebView whose bridge lives on capacitor://localhost (iOS) or
        # https://localhost (Android). Without these origins the Capacitor
        # bridge is blocked and native push, the back button, and external
        # link handling all silently stop working.
        NATIVE_ORIGINS = "capacitor://localhost https://localhost http://localhost"

        response.headers.setdefault("Content-Security-Policy", "; ".join([
            f"default-src 'self' {NATIVE_ORIGINS}",
            # 'unsafe-inline' is needed because the app uses inline scripts and
            # styles throughout. Removing it would mean refactoring every
            # template to external files — worth doing eventually.
            # 'wasm-unsafe-eval' is needed by the Unity WebGL game, which
            # compiles WebAssembly at runtime. It is far narrower than
            # 'unsafe-eval' — it permits WebAssembly compilation only, and
            # does not re-enable eval() or new Function() for JavaScript.
            f"script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' {NATIVE_ORIGINS}",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: blob: https://i.ytimg.com",
            "media-src 'self' blob: https:",
            "frame-src https://www.youtube.com https://player.vimeo.com "
            "https://www.facebook.com",
            f"connect-src 'self' https://bible-api.com {NATIVE_ORIGINS}",
            "form-action 'self'",
            "base-uri 'self'",
            "object-src 'none'",
        ]))

    return response


# ---------- CSRF protection ----------

def csrf_token():
    """The token for this session, created on first use."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


# Which stylesheet to serve. Set CLEARSPRING_THEME=classic to put the original
# warm cream-and-brown design back without touching any templates — the old
# stylesheet is kept at static/style-classic.css.
CLASSIC_THEME = os.environ.get("CLEARSPRING_THEME", "").strip().lower() == "classic"


@app.context_processor
def inject_theme_choice():
    return {"classic_theme": CLASSIC_THEME}


@app.context_processor
def inject_csrf():
    return {"csrf_token": csrf_token}


@app.before_request
def protect_against_csrf():
    """Reject state-changing requests that don't carry a valid token.

    Applied globally rather than per-route, so a route added later is covered
    by default rather than by remembering to decorate it.
    """
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None

    expected = session.get("csrf_token")

    # Look in both places rather than deciding by endpoint name.
    #
    # This used to consult a hand-maintained list of endpoints that send the
    # token as a header. The list added no security — the token itself is the
    # protection, and where it travels doesn't change that — but it did mean
    # any new fetch-based endpoint silently rejected every request until
    # someone remembered to add it, and the failure looked like a network
    # error rather than a missing entry.
    supplied = (
        request.form.get("csrf_token")
        or request.headers.get("X-CSRF-Token")
        or ""
    )

    if not expected or not supplied or not secrets.compare_digest(
        str(expected), str(supplied)
    ):
        # A missing token usually means an expired session rather than an attack,
        # so say something a person can act on.
        #
        # How we say it depends on who's listening: a fetch() call needs JSON
        # it can parse, a submitted form needs a page with a message on it.
        wants_json = (
            request.is_json
            or request.headers.get("X-CSRF-Token") is not None
            or "application/json" in (request.headers.get("Accept") or "")
        )
        if wants_json:
            return {"ok": False, "error": "csrf"}, 400
        flash("Your session expired, so that wasn't submitted. Please try again.")
        return redirect(request.referrer or url_for("index")), 303

    return None


# ---------- Database ----------

def get_db():
    if "db" not in g:
        # timeout: wait for a lock rather than failing instantly. Without this
        # two people saving at the same moment can produce "database is locked".
        g.db = sqlite3.connect(DB_PATH, timeout=15.0)
        g.db.row_factory = sqlite3.Row
        # WAL lets reads carry on while a write is in progress. On a read-heavy
        # site like this one that is the difference between smooth and stalling.
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA busy_timeout=15000")
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA synchronous=NORMAL")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH, timeout=15.0)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'event',
            event_date TEXT NOT NULL,
            event_time TEXT NOT NULL,
            location TEXT,
            description TEXT,
            recurring TEXT NOT NULL DEFAULT 'none'
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_text TEXT NOT NULL,
            asker_name TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            answer_text TEXT,
            submitted_at TEXT NOT NULL,
            answered_at TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sermons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            speaker TEXT,
            series TEXT,
            topic TEXT,
            passage TEXT,
            summary TEXT,
            preached_on TEXT NOT NULL,
            video_url TEXT,
            audio_url TEXT,
            duration_seconds INTEGER,
            published INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            name TEXT,
            password_hash TEXT,
            email_verified INTEGER NOT NULL DEFAULT 0,
            login_token_hash TEXT,
            login_token_expires TEXT,
            created_at TEXT NOT NULL,
            last_login TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS member_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            item_key TEXT NOT NULL,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(member_id, kind, item_key),
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'other',
            summary TEXT,
            description TEXT,
            price_pence INTEGER,
            price_note TEXT,
            image_url TEXT,
            buy_url TEXT,
            stock TEXT NOT NULL DEFAULT 'available',
            featured INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS game_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            game_key TEXT NOT NULL,
            score INTEGER NOT NULL,
            achieved_at TEXT NOT NULL,
            UNIQUE(member_id, game_key),
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT NOT NULL UNIQUE,
            subscription_json TEXT NOT NULL,
            prefs_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            last_seen TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'growing',
            summary TEXT,
            body TEXT,
            url TEXT,
            file_path TEXT,
            kind TEXT NOT NULL DEFAULT 'link',
            author TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            published INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS ministries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            tagline TEXT,
            description TEXT,
            meets TEXT,
            location TEXT,
            contact_name TEXT,
            contact_email TEXT,
            contact_phone TEXT,
            resources TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            blurb TEXT,
            target_pence INTEGER,
            raised_pence INTEGER NOT NULL DEFAULT 0,
            give_url TEXT,
            closes_on TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS prayers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            body TEXT NOT NULL,
            author_name TEXT,
            visibility TEXT NOT NULL DEFAULT 'public',
            kind TEXT NOT NULL DEFAULT 'request',
            status TEXT NOT NULL DEFAULT 'live',
            hold_reason TEXT,
            pray_count INTEGER NOT NULL DEFAULT 0,
            submitted_at TEXT NOT NULL,
            answered_at TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS devotionals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            verse_ref TEXT,
            body TEXT NOT NULL,
            video_url TEXT,
            created_at TEXT NOT NULL,
            published INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS polls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            show_results TEXT NOT NULL DEFAULT 'live',
            created_at TEXT NOT NULL,
            opened_at TEXT,
            closed_at TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS poll_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            vote_count INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE
        )
        """
    )
    # Seed starter devotionals once (only if the table is empty)
    existing = db.execute("SELECT COUNT(*) FROM devotionals").fetchone()[0]
    if existing == 0:
        base = datetime.now()
        for i, d in enumerate(STARTER_DEVOTIONALS):
            created = (base - timedelta(days=i)).isoformat()
            db.execute(
                "INSERT INTO devotionals (title, verse_ref, body, created_at, published) VALUES (?, ?, ?, ?, 1)",
                (d["title"], d["verse_ref"], d["body"], created),
            )
    # Migration: add an optional video to devotionals for existing databases
    devo_cols = [r[1] for r in db.execute("PRAGMA table_info(devotionals)").fetchall()]
    if "video_url" not in devo_cols:
        db.execute("ALTER TABLE devotionals ADD COLUMN video_url TEXT")

    # Migration: add ministry tag to events for existing databases
    achievements.ensure_tables(db)

    cols = [r[1] for r in db.execute("PRAGMA table_info(events)").fetchall()]
    if "ministry" not in cols:
        db.execute("ALTER TABLE events ADD COLUMN ministry TEXT")

    # Seed the standard ministries once (only if the table is empty)
    if db.execute("SELECT COUNT(*) FROM ministries").fetchone()[0] == 0:
        for order, m in enumerate(DEFAULT_MINISTRIES):
            db.execute(
                """INSERT INTO ministries (slug, name, tagline, sort_order, active)
                   VALUES (?, ?, ?, ?, 1)""",
                (m["slug"], m["name"], m["tagline"], order),
            )

    # Seed starter resources once (only if the table is empty)
    if db.execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 0:
        now = datetime.now().isoformat()
        for order, r in enumerate(STARTER_RESOURCES):
            db.execute(
                """INSERT INTO resources (title, category, summary, body, kind,
                   sort_order, published, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
                (r["title"], r["category"], r.get("summary"), r.get("body"),
                 r.get("kind", "article"), order, now),
            )

    db.commit()
    db.close()


# ---------- Auth ----------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Behind a proxy the real address is in X-Forwarded-For; fall back to
        # the direct address locally.
        ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "")
              .split(",")[0].strip())

        if _login_rate_limited(ip):
            flash("Too many attempts. Please wait a few minutes and try again.")
            return render_template(
                "login.html",
                using_default_password=(ADMIN_PASSWORD == "changeme"),
            ), 429

        password = request.form.get("password", "")
        # Constant-time comparison so response timing can't be used to
        # work the password out character by character.
        if password and secrets.compare_digest(password, ADMIN_PASSWORD):
            session["is_admin"] = True
            session.permanent = False
            _login_attempts.pop(ip, None)
            return redirect(request.args.get("next") or url_for("admin"))

        _record_login_failure(ip)
        flash("That password isn't right. Try again.")
    return render_template(
        "login.html",
        using_default_password=(ADMIN_PASSWORD == "changeme"),
    )


@app.route("/admin/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


# ---------- Public ----------

WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def verse_of_the_day():
    day_number = date.today().toordinal()
    return VERSES[day_number % len(VERSES)]


def upcoming_occurrences(limit=3, days_ahead=45):
    db = get_db()
    rows = db.execute("SELECT * FROM events").fetchall()
    today = date.today()
    range_end = today + timedelta(days=days_ahead)
    items = []
    for row in rows:
        for occ_date in occurrences(row, today, range_end):
            items.append((occ_date.isoformat(), row))
    items.sort(key=lambda pair: (pair[0], pair[1]["event_time"]))
    return items[:limit]


HOME_DEFAULTS = {
    "home_eyebrow": "Cheltenham · Sundays 11am",
    "home_statement": "Jesus is always\nthe *lead story*",
    "home_sub": "Centenary Hall, Dean Close Prep School, GL51 6QS",
    "home_cta": "Plan your visit",
}


def render_statement(raw):
    """Turn 'the *lead story*' into markup with the signature italic word.

    Built as DOM-safe pieces rather than dropping the setting straight into
    the page: this text is editable from admin, and admin input should never
    become live HTML. Only two things are emitted — <em> and <br> — and the
    words themselves are escaped.
    """
    from markupsafe import Markup, escape

    out = []
    for i, line in enumerate((raw or "").split("\n")):
        if i:
            out.append("<br>")
        # Split on *emphasis*, keeping the delimiters.
        for part in re.split(r"(\*[^*]+\*)", line):
            if len(part) > 2 and part.startswith("*") and part.endswith("*"):
                out.append(f"<em>{escape(part[1:-1])}</em>")
            else:
                out.append(str(escape(part)))
    return Markup("".join(out))


@app.route("/admin/home", methods=["GET", "POST"])
@login_required
def admin_home():
    saved = False
    if request.method == "POST":
        for key in HOME_DEFAULTS:
            set_setting(key, (request.form.get(key) or "").strip())
        get_db().commit()
        saved = True
    return render_template(
        "admin_home.html",
        church_name=CHURCH_NAME,
        content={k: (get_setting(k, v) or v) for k, v in HOME_DEFAULTS.items()},
        saved=saved,
    )


@app.route("/")
def index():
    db = get_db()
    latest_sermon = db.execute(
        "SELECT * FROM sermons WHERE published=1 ORDER BY preached_on DESC LIMIT 1"
    ).fetchone()
    devotional = db.execute(
        "SELECT * FROM devotionals WHERE published=1 ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    live_on = get_setting("live_is_on", "0") == "1"
    return render_template(
        "home.html",
        church_name=CHURCH_NAME,
        verse=verse_of_the_day(),
        upcoming=upcoming_occurrences(),
        latest_sermon=latest_sermon,
        sermon_thumb=thumbnail_url(latest_sermon["video_url"]) if latest_sermon else None,
        devotional=devotional,
        live_on=live_on,
        hero={k: (get_setting(k, v) or v) for k, v in HOME_DEFAULTS.items()},
        hero_statement=render_statement(
            get_setting("home_statement", HOME_DEFAULTS["home_statement"])
        ),
    )


def get_setting(key, default=None):
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    db = get_db()
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    db.commit()


@app.route("/watch")
def watch_hub():
    db = get_db()
    q = request.args.get("q", "").strip()
    speaker = request.args.get("speaker", "").strip()
    series = request.args.get("series", "").strip()

    sql = "SELECT * FROM sermons WHERE published=1"
    params = []
    if q:
        sql += (" AND (title LIKE ? OR speaker LIKE ? OR topic LIKE ? "
                "OR passage LIKE ? OR series LIKE ? OR summary LIKE ?)")
        params.extend([f"%{q}%"] * 6)
    if speaker:
        sql += " AND speaker = ?"
        params.append(speaker)
    if series:
        sql += " AND series = ?"
        params.append(series)
    sql += " ORDER BY preached_on DESC"

    rows = db.execute(sql, params).fetchall()

    sermons = []
    for r in rows:
        sermons.append({
            "row": r,
            "thumb": thumbnail_url(r["video_url"]),
            "duration": format_duration(r["duration_seconds"]),
        })

    speakers = [r["speaker"] for r in db.execute(
        "SELECT DISTINCT speaker FROM sermons WHERE published=1 AND speaker IS NOT NULL "
        "AND speaker != '' ORDER BY speaker"
    ).fetchall()]
    all_series = [r["series"] for r in db.execute(
        "SELECT DISTINCT series FROM sermons WHERE published=1 AND series IS NOT NULL "
        "AND series != '' ORDER BY series"
    ).fetchall()]

    latest = sermons[0] if sermons and not (q or speaker or series) else None
    rest = sermons[1:] if latest else sermons

    live_url = get_setting("live_stream_url", "")
    live_on = get_setting("live_is_on", "0") == "1"

    return render_template(
        "watch.html",
        church_name=CHURCH_NAME,
        latest=latest,
        sermons=rest,
        speakers=speakers,
        all_series=all_series,
        q=q,
        active_speaker=speaker,
        active_series=series,
        live_embed=embed_url(live_url) if live_url else None,
        live_on=live_on,
        total=len(sermons),
    )


@app.route("/watch/<int:sermon_id>")
def sermon_detail(sermon_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM sermons WHERE id=? AND published=1", (sermon_id,)
    ).fetchone()
    if not row:
        abort(404)
    passage_link = parse_reference(row["passage"]) if row["passage"] else None
    return render_template(
        "sermon_detail.html",
        church_name=CHURCH_NAME,
        s=row,
        video_embed=embed_url(row["video_url"]),
        duration=format_duration(row["duration_seconds"]),
        passage_link=passage_link,
    )


@app.route("/watch/podcast.xml")
def podcast_feed():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM sermons WHERE published=1 AND audio_url IS NOT NULL "
        "AND audio_url != '' ORDER BY preached_on DESC"
    ).fetchall()
    site = request.url_root.rstrip("/")
    xml = build_podcast_feed(
        rows,
        church_name=CHURCH_NAME,
        site_url=site,
        feed_url=url_for("podcast_feed", _external=True),
    )
    return Response(xml, mimetype="application/rss+xml")


# ---------- Live Polls ----------
#
# A lightweight "ask the room a question during the service" feature. No
# sign-in required to vote — like the prayer wall's "praying for you" count,
# one vote per browser session is tracked in the session itself rather than
# tied to a member account, so it stays anonymous and frictionless on a
# phone mid-service.

def poll_to_dict(poll_row, option_rows, voted_option_id):
    total = sum(o["vote_count"] for o in option_rows)
    reveal = poll_row["show_results"] == "live" or poll_row["status"] == "closed"
    options = []
    for o in option_rows:
        pct = round(100 * o["vote_count"] / total) if total and reveal else 0
        options.append({
            "id": o["id"],
            "label": o["label"],
            "votes": o["vote_count"] if reveal else None,
            "pct": pct if reveal else None,
        })
    return {
        "id": poll_row["id"],
        "question": poll_row["question"],
        "status": poll_row["status"],
        "options": options,
        "total_votes": total if reveal else None,
        "reveal": reveal,
        "voted_option_id": voted_option_id,
    }


@app.route("/poll/active")
def poll_active():
    """The current live (or just-closed) poll, if any — polled every few
    seconds from the Watch page rather than pushed, since a service-length
    poll doesn't need anything fancier than that."""
    db = get_db()
    poll = db.execute(
        "SELECT * FROM polls WHERE status IN ('live', 'closed') "
        "ORDER BY (status = 'live') DESC, COALESCE(closed_at, opened_at) DESC LIMIT 1"
    ).fetchone()
    if not poll:
        return {"ok": True, "poll": None}, 200

    options = db.execute(
        "SELECT * FROM poll_options WHERE poll_id=? ORDER BY sort_order, id",
        (poll["id"],),
    ).fetchall()
    voted = session.get("poll_votes", {}).get(str(poll["id"]))
    return {"ok": True, "poll": poll_to_dict(poll, options, voted)}, 200


@app.route("/poll/<int:poll_id>/vote", methods=["POST"])
def poll_vote(poll_id):
    voted = session.get("poll_votes", {})
    if str(poll_id) in voted:
        return {"ok": False, "error": "already_voted"}, 200

    db = get_db()
    poll = db.execute(
        "SELECT * FROM polls WHERE id=? AND status='live'", (poll_id,)
    ).fetchone()
    if not poll:
        return {"ok": False, "error": "not_live"}, 404

    data = request.get_json(silent=True) or {}
    try:
        option_id = int(data.get("option_id"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid_option"}, 400

    option = db.execute(
        "SELECT * FROM poll_options WHERE id=? AND poll_id=?", (option_id, poll_id)
    ).fetchone()
    if not option:
        return {"ok": False, "error": "invalid_option"}, 400

    db.execute(
        "UPDATE poll_options SET vote_count = vote_count + 1 WHERE id=?", (option_id,)
    )
    db.commit()

    voted[str(poll_id)] = option_id
    session["poll_votes"] = voted

    options = db.execute(
        "SELECT * FROM poll_options WHERE poll_id=? ORDER BY sort_order, id",
        (poll_id,),
    ).fetchall()
    return {"ok": True, "poll": poll_to_dict(poll, options, option_id)}, 200


@app.route("/community")
def community_hub():
    return render_template("community.html", church_name=CHURCH_NAME)


@app.route("/bible")
def bible_hub():
    db = get_db()
    todays_devotional = db.execute(
        "SELECT * FROM devotionals WHERE published=1 ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    return render_template(
        "bible.html",
        church_name=CHURCH_NAME,
        verse=verse_of_the_day(),
        devotional=todays_devotional,
        plans=plan_summary(),
    )


@app.route("/bible/saved")
def saved_verses():
    return render_template("saved_verses.html", church_name=CHURCH_NAME)


# ---------- Reading Plans ----------

def _resolve_passages(refs):
    """Turn a list of references into dicts with reader links."""
    resolved = []
    for ref in refs:
        parsed = parse_reference(ref)
        if parsed:
            slug, chapter = parsed
            resolved.append({"ref": ref, "slug": slug, "chapter": chapter})
        else:
            resolved.append({"ref": ref, "slug": None, "chapter": None})
    return resolved


@app.route("/bible/plans")
def reading_plans():
    return render_template(
        "reading_plans.html", church_name=CHURCH_NAME, plans=plan_summary()
    )


@app.route("/bible/plans/<plan_slug>")
def reading_plan_detail(plan_slug):
    plan = get_plan(plan_slug)
    if not plan:
        abort(404)
    days = []
    for i, day_refs in enumerate(plan["days"], start=1):
        days.append({"num": i, "passages": _resolve_passages(day_refs)})
    return render_template(
        "reading_plan_detail.html",
        video_embed=embed_url(plan.get("video_url")),
        church_name=CHURCH_NAME,
        plan=plan,
        plan_slug=plan_slug,
        days=days,
    )


def ministry_options():
    db = get_db()
    return db.execute(
        "SELECT slug, name FROM ministries WHERE active=1 ORDER BY sort_order, name"
    ).fetchall()


@app.route("/service-worker.js")
def service_worker():
    """Served from the root so its scope covers the whole app.

    A worker served from /static/ can only control /static/ pages, which means
    navigator.serviceWorker.ready never resolves for the rest of the site and
    push registration silently hangs.
    """
    response = make_response(
        send_from_directory(app.static_folder, "service-worker.js")
    )
    response.headers["Content-Type"] = "application/javascript"
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


# ---------- Bible study assistant ----------

@app.route("/api/study/ask", methods=["POST"])
def study_ask():
    if not study_available():
        return {"ok": False, "answer": "The study assistant isn't switched on yet."}, 200

    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()[:500]
    if not question:
        return {"ok": False, "answer": "Please type a question first."}, 200

    # Modest per-session rate limit, so the free daily quota isn't burned
    # through by one person and left empty for everyone else.
    #
    # Session limits alone are bypassed by simply clearing cookies, so this is
    # backed by a per-IP ceiling. This endpoint calls a paid API — an unmetered
    # one would let a single script run up the bill.
    if rate_limited("study_ask", client_ip(), limit=40, window_seconds=3600):
        return {
            "ok": False,
            "answer": "The study assistant is busy right now. Please try again shortly.",
        }, 200

    asked = session.get("study_asked", [])
    now = datetime.now().timestamp()
    asked = [t for t in asked if now - t < 3600]
    if len(asked) >= 15:
        return {
            "ok": False,
            "answer": "You've asked quite a few questions in the last hour. "
                      "Please take a break and come back shortly.",
        }, 200
    asked.append(now)
    session["study_asked"] = asked

    # Conversation history from the client, so follow-up questions make sense.
    # It comes from the browser and is therefore untrusted: validate the shape,
    # cap the length, and never let it through unchecked.
    raw_history = data.get("history")
    history = []
    if isinstance(raw_history, list):
        for turn in raw_history[-20:]:
            if not isinstance(turn, dict):
                continue
            role = turn.get("role")
            text = turn.get("text")
            if role in ("user", "model") and isinstance(text, str) and text.strip():
                history.append({"role": role, "text": text.strip()[:2000]})

    ok, answer = study_ask_ai(
        question,
        passage_ref=(data.get("ref") or "")[:80],
        passage_text=(data.get("text") or "")[:2500],
        history=history,
    )
    return {"ok": ok, "answer": answer}, 200


# ---------- Member accounts ----------

def current_member():
    """The signed-in member, or None. Cached per request."""
    if "member" not in g:
        g.member = None
        member_id = session.get("member_id")
        if member_id:
            row = get_db().execute(
                "SELECT * FROM members WHERE id=? AND active=1", (member_id,)
            ).fetchone()
            g.member = row
            if row is None:
                session.pop("member_id", None)
    return g.member


@app.context_processor
def inject_member():
    return {"member": current_member()}


def member_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_member():
            session["after_signin"] = request.path
            return redirect(url_for("signin"))
        return view(*args, **kwargs)
    return wrapped


def _finish_signin(member_row):
    session["member_id"] = member_row["id"]
    session.permanent = True
    get_db().execute(
        "UPDATE members SET last_login=? WHERE id=?",
        (datetime.now().isoformat(), member_row["id"]),
    )
    get_db().commit()
    target = session.pop("after_signin", None)
    return redirect(target or url_for("account"))


@app.route("/account/signup", methods=["GET", "POST"])
def signup():
    if current_member():
        return redirect(url_for("account"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = normalise_email(request.form.get("email", ""))
        password = request.form.get("password", "")

        if not valid_email(email):
            flash("Please enter a valid email address.")
            return render_template("signup.html", name=name, email=email)

        problem = password_problem(password, email=email, name=name)
        if problem:
            flash(problem)
            return render_template("signup.html", name=name, email=email)

        db = get_db()
        existing = db.execute(
            "SELECT id FROM members WHERE email=?", (email,)
        ).fetchone()
        if existing:
            # Don't confirm the address is registered — point them at sign-in.
            flash("That email may already have an account. Try signing in, "
                  "or use the email link option if you've forgotten your password.")
            return redirect(url_for("signin"))

        db.execute(
            """INSERT INTO members (email, name, password_hash, created_at, active)
               VALUES (?, ?, ?, ?, 1)""",
            (email, name or None, hash_password(password), datetime.now().isoformat()),
        )
        db.commit()
        row = db.execute("SELECT * FROM members WHERE email=?", (email,)).fetchone()
        return _finish_signin(row)

    return render_template("signup.html", name="", email="")


@app.route("/account/signin", methods=["GET", "POST"])
def signin():
    if current_member():
        return redirect(url_for("account"))

    if request.method == "POST":
        email = normalise_email(request.form.get("email", ""))
        password = request.form.get("password", "")

        db = get_db()
        row = db.execute(
            "SELECT * FROM members WHERE email=? AND active=1", (email,)
        ).fetchone()

        if row and verify_password(row["password_hash"], password):
            return _finish_signin(row)

        # Same message whether the account exists or the password was wrong.
        flash("That email and password don't match. Please try again, or use "
              "the email link option below.")
        return render_template("signin.html", email=email)

    return render_template("signin.html", email="")


@app.route("/account/link", methods=["GET", "POST"])
def magic_link_request():
    """Request a one-time sign-in link by email."""
    if request.method == "POST":
        email = normalise_email(request.form.get("email", ""))

        # Without this, anyone can point a script at this form and send an
        # unbounded number of emails to a member — and burn through the
        # sending quota for everyone else.
        if rate_limited("magic_link", client_ip(), limit=5, window_seconds=900):
            return render_template(
                "magic_link_sent.html",
                email=email,
                email_working=email_is_configured(),
            )

        db = get_db()
        row = db.execute(
            "SELECT * FROM members WHERE email=? AND active=1", (email,)
        ).fetchone()

        if row:
            token = new_token()
            db.execute(
                "UPDATE members SET login_token_hash=?, login_token_expires=? WHERE id=?",
                (hash_token(token), token_expiry(), row["id"]),
            )
            db.commit()
            link = url_for("magic_link_use", token=token, _external=True)
            send_magic_link(row["email"], row["name"], link)

        # The same confirmation either way, so this page can't be used to
        # discover which addresses have accounts.
        #
        # The link is NEVER shown on screen. Doing so would let anyone type
        # someone else's address and sign in as them.
        return render_template(
            "magic_link_sent.html",
            email=email,
            email_working=email_is_configured(),
        )

    return render_template(
        "magic_link.html", email="", email_working=email_is_configured()
    )


@app.route("/account/link/<token>")
def magic_link_use(token):
    db = get_db()
    row = db.execute(
        "SELECT * FROM members WHERE login_token_hash=? AND active=1",
        (hash_token(token),),
    ).fetchone()

    if not row or token_expired(row["login_token_expires"]):
        flash("That sign-in link has expired or already been used. "
              "Please request a new one.")
        return redirect(url_for("magic_link_request"))

    # Single use: clear the token immediately.
    db.execute(
        "UPDATE members SET login_token_hash=NULL, login_token_expires=NULL, "
        "email_verified=1 WHERE id=?",
        (row["id"],),
    )
    db.commit()
    return _finish_signin(row)


@app.route("/account/signout", methods=["POST"])
def signout():
    session.pop("member_id", None)
    g.pop("member", None)
    flash("You've been signed out.")
    return redirect(url_for("index"))


@app.route("/account/delete", methods=["POST"])
@member_required
def account_delete():
    """Permanently delete the signed-in member and everything they own.

    Required for App Store approval (guideline 5.1.1(v)): any app that offers
    account creation must offer account deletion inside the app. Password is
    re-confirmed so a borrowed unlocked phone can't destroy an account.
    """
    m = current_member()
    password = request.form.get("password", "")
    confirm_email = (request.form.get("confirm_email") or "").strip().lower()

    db = get_db()
    row = db.execute(
        "SELECT password_hash, email FROM members WHERE id=?", (m["id"],)
    ).fetchone()

    if not row:
        flash("That account no longer exists.")
        return redirect(url_for("index"))

    # Members who signed up by magic link have no password at all. Requiring
    # one meant they could never delete their account — they'd be told the
    # password was wrong forever. That breaks the right to erasure, and it
    # breaks the App Store rule this route exists to satisfy. So confirm by
    # typing the account's own email address instead: still a deliberate act
    # that a borrowed phone won't produce by accident.
    if row["password_hash"]:
        confirmed = verify_password(row["password_hash"], password)
        failure = "That password wasn't right, so nothing was deleted."
    else:
        confirmed = confirm_email == (row["email"] or "").strip().lower()
        failure = ("That email address didn't match, so nothing was deleted.")

    if not confirmed:
        flash(failure)
        return redirect(url_for("account"))

    # Their synced data (saved verses, notes, journal, reading progress).
    db.execute("DELETE FROM member_data WHERE member_id=?", (m["id"],))
    # Their leaderboard entries.
    db.execute("DELETE FROM game_scores WHERE member_id=?", (m["id"],))
    # Streaks and badges. These also cascade from the foreign key, but delete
    # them explicitly so it doesn't depend on foreign_keys being on.
    db.execute("DELETE FROM member_activity WHERE member_id=?", (m["id"],))
    db.execute("DELETE FROM member_badges WHERE member_id=?", (m["id"],))
    # The account itself.
    db.execute("DELETE FROM members WHERE id=?", (m["id"],))
    db.commit()

    session.pop("member_id", None)
    g.pop("member", None)
    flash("Your account and all its data have been deleted.")
    return redirect(url_for("index"))


@app.route("/account/progress")
@member_required
def member_progress():
    """Streaks and badges for the signed-in member."""
    m = current_member()
    db = get_db()
    # Re-check on view, so anything earned before this feature existed
    # gets picked up rather than only counting from now on.
    achievements.evaluate(db, m["id"], total_games=len(GAMES))
    db.commit()
    data = achievements.summary(db, m["id"], total_games=len(GAMES))
    return render_template(
        "progress.html",
        church_name=CHURCH_NAME,
        member=m,
        grace_days=achievements.GRACE_DAYS,
        **data,
    )


@app.route("/account")
@member_required
def account():
    m = current_member()
    db = get_db()
    counts = {}
    for kind, label in [
        ("verse", "Saved verses"),
        ("note", "Sermon notes"),
        ("plan", "Reading plans"),
        ("journal", "Journal entries"),
    ]:
        counts[label] = db.execute(
            "SELECT COUNT(*) FROM member_data WHERE member_id=? AND kind=?",
            (m["id"], kind),
        ).fetchone()[0]
    return render_template("account.html", m=m, counts=counts)


def email_is_configured():
    return emailer.is_configured()


def send_magic_link(to, name, link):
    """Send a sign-in link. Logs rather than crashes if it fails, so a mail
    outage never breaks the sign-in page."""
    ok, message = emailer.send_sign_in_link(CHURCH_NAME, to, name, link)
    if not ok:
        app.logger.warning("Could not send sign-in link to %s: %s", to, message)
    return ok


SYNC_KINDS = {"verse", "note", "plan", "journal", "highlight"}


@app.route("/api/sync/<kind>", methods=["GET"])
def sync_get(kind):
    """Return everything of this kind for the signed-in member."""
    if kind not in SYNC_KINDS:
        return {"ok": False, "error": "unknown kind"}, 400
    m = current_member()
    if not m:
        return {"ok": False, "signed_in": False, "items": []}, 200

    rows = get_db().execute(
        "SELECT item_key, payload, updated_at FROM member_data "
        "WHERE member_id=? AND kind=? ORDER BY updated_at DESC",
        (m["id"], kind),
    ).fetchall()
    items = []
    for r in rows:
        try:
            payload = json.loads(r["payload"])
        except (ValueError, TypeError):
            continue
        items.append({"key": r["item_key"], "value": payload, "updated": r["updated_at"]})
    return {"ok": True, "signed_in": True, "items": items}, 200


@app.route("/api/sync/<kind>", methods=["POST"])
def sync_put(kind):
    """Store or update one item. Silently ignored when signed out."""
    if kind not in SYNC_KINDS:
        return {"ok": False, "error": "unknown kind"}, 400
    m = current_member()
    if not m:
        return {"ok": False, "signed_in": False}, 200

    data = request.get_json(silent=True) or {}
    item_key = str(data.get("key", ""))[:200]
    if not item_key:
        return {"ok": False, "error": "missing key"}, 400

    db = get_db()
    if data.get("delete"):
        db.execute(
            "DELETE FROM member_data WHERE member_id=? AND kind=? AND item_key=?",
            (m["id"], kind, item_key),
        )
    else:
        db.execute(
            """INSERT INTO member_data (member_id, kind, item_key, payload, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(member_id, kind, item_key) DO UPDATE SET
                 payload=excluded.payload, updated_at=excluded.updated_at""",
            (m["id"], kind, item_key, json.dumps(data.get("value")),
             datetime.now().isoformat()),
        )
        # Saving a verse, note or journal entry counts as showing up today.
        # Deleting doesn't — otherwise tidying up would count as activity.
        achievements.record(db, m["id"], kind if kind in
                            achievements.ACTIVITY_SOURCES else "read")

    new_badges = achievements.evaluate(db, m["id"], total_games=len(GAMES))
    db.commit()
    return {
        "ok": True,
        "signed_in": True,
        "new_badges": [{"name": b["name"], "desc": b["desc"]} for b in new_badges],
    }, 200


@app.route("/api/sync/<kind>/bulk", methods=["POST"])
def sync_bulk(kind):
    """Upload everything held locally — used once when someone first signs in,
    so nothing they saved before having an account is lost."""
    if kind not in SYNC_KINDS:
        return {"ok": False, "error": "unknown kind"}, 400
    m = current_member()
    if not m:
        return {"ok": False, "signed_in": False}, 200

    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    db = get_db()
    stored = 0
    for item in items[:500]:
        key = str(item.get("key", ""))[:200]
        if not key:
            continue
        db.execute(
            """INSERT INTO member_data (member_id, kind, item_key, payload, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(member_id, kind, item_key) DO NOTHING""",
            (m["id"], kind, key, json.dumps(item.get("value")),
             datetime.now().isoformat()),
        )
        stored += 1
    db.commit()
    return {"ok": True, "stored": stored}, 200


# ---------- Notifications ----------

@app.route("/settings")
def settings():
    return render_template("settings.html", church_name=CHURCH_NAME)


@app.route("/settings/notifications")
def notification_settings():
    return render_template(
        "notifications.html",
        church_name=CHURCH_NAME,
        types=NOTIFICATION_TYPES,
        vapid_public_key=VAPID_PUBLIC_KEY,
        push_configured=push_is_configured(),
    )


@app.route("/api/push/subscribe", methods=["POST"])
def push_subscribe():
    data = request.get_json(silent=True) or {}
    sub = data.get("subscription")
    prefs = data.get("prefs") or {}

    # The native iOS/Android shell has no Web Push endpoint. It sends an APNs
    # or FCM token instead, which we store under a synthetic endpoint so it
    # shares the same table and uniqueness guarantee as web subscriptions.
    native_token = (data.get("native_token") or "").strip()
    if native_token:
        platform = (data.get("platform") or "").strip().lower()
        if platform not in ("ios", "android"):
            return {"ok": False, "error": "unknown platform"}, 400
        sub = {
            "endpoint": f"native:{platform}:{native_token}",
            "native": True,
            "platform": platform,
            "token": native_token,
        }

    if not sub or not sub.get("endpoint"):
        return {"ok": False, "error": "missing subscription"}, 400

    # Only store keys we recognise, all defaulting to off.
    clean_prefs = {k: bool(prefs.get(k)) for k in TYPE_KEYS}

    db = get_db()
    db.execute(
        """INSERT INTO push_subscriptions (endpoint, subscription_json, prefs_json, created_at, last_seen)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(endpoint) DO UPDATE SET
             subscription_json=excluded.subscription_json,
             prefs_json=excluded.prefs_json,
             last_seen=excluded.last_seen""",
        (
            sub["endpoint"],
            json.dumps(sub),
            json.dumps(clean_prefs),
            datetime.now().isoformat(),
            datetime.now().isoformat(),
        ),
    )
    db.commit()
    return {"ok": True}, 200


@app.route("/api/push/unsubscribe", methods=["POST"])
def push_unsubscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")

    native_token = (data.get("native_token") or "").strip()
    if native_token:
        platform = (data.get("platform") or "").strip().lower()
        endpoint = f"native:{platform}:{native_token}"

    if endpoint:
        db = get_db()
        db.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))
        db.commit()
    return {"ok": True}, 200


def broadcast(type_key, title, body, url="/"):
    """Send a notification to everyone opted in to this type.

    Returns (sent, failed). Safe to call even when push isn't configured —
    it simply does nothing, so features that trigger it never break.
    """
    if type_key not in TYPE_KEYS:
        return 0, 0
    # Either transport being available is enough — a church might run the
    # native apps without web push configured, or the other way round.
    if not push_is_configured() and not native_push_is_configured():
        return 0, 0

    db = get_db()
    rows = db.execute("SELECT * FROM push_subscriptions").fetchall()
    sent = failed = 0
    dead = []

    for row in rows:
        try:
            prefs = json.loads(row["prefs_json"])
        except (ValueError, TypeError):
            continue
        if not prefs.get(type_key):
            continue
        try:
            sub = json.loads(row["subscription_json"])
        except (ValueError, TypeError):
            continue

        ok, should_remove = send_push(sub, title, body, url, tag=type_key)
        if ok:
            sent += 1
        else:
            failed += 1
            if should_remove:
                dead.append(row["endpoint"])

    for endpoint in dead:
        db.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))
    if dead:
        db.commit()

    return sent, failed


# ---------- Resources ----------

@app.route("/resources")
def resources():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM resources WHERE published=1 ORDER BY sort_order, title"
    ).fetchall()
    grouped = []
    for slug, name, blurb in RESOURCE_CATEGORIES:
        items = [r for r in rows if r["category"] == slug]
        if items:
            grouped.append({"slug": slug, "name": name, "blurb": blurb, "items": items})
    return render_template(
        "resources.html", church_name=CHURCH_NAME, grouped=grouped
    )


@app.route("/resources/<int:resource_id>")
def resource_detail(resource_id):
    db = get_db()
    r = db.execute(
        "SELECT * FROM resources WHERE id=? AND published=1", (resource_id,)
    ).fetchone()
    if not r:
        abort(404)
    # Links and files go straight out; only articles have a reader page.
    if r["kind"] != "article":
        target = r["url"] or r["file_path"]
        if target:
            return redirect(target)
        abort(404)
    category_name = next(
        (n for s, n, _ in RESOURCE_CATEGORIES if s == r["category"]), "Resources"
    )
    return render_template(
        "resource_detail.html", church_name=CHURCH_NAME, r=r, category_name=category_name
    )


# ---------- Ministries ----------

@app.route("/ministries")
def ministries():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM ministries WHERE active=1 ORDER BY sort_order, name"
    ).fetchall()
    return render_template("ministries.html", church_name=CHURCH_NAME, ministries=rows)


@app.route("/ministries/<slug>")
def ministry_detail(slug):
    db = get_db()
    m = db.execute(
        "SELECT * FROM ministries WHERE slug=? AND active=1", (slug,)
    ).fetchone()
    if not m:
        abort(404)

    # Upcoming events tagged to this ministry, using the same recurrence logic
    today = date.today()
    range_end = today + timedelta(days=120)
    rows = db.execute("SELECT * FROM events WHERE ministry=?", (slug,)).fetchall()
    items = []
    for row in rows:
        for occ in occurrences(row, today, range_end):
            items.append((occ.isoformat(), row))
    items.sort(key=lambda pair: (pair[0], pair[1]["event_time"]))

    resources = []
    if m["resources"]:
        for line in m["resources"].splitlines():
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                label, url = line.split("|", 1)
                resources.append({"label": label.strip(), "url": url.strip()})
            else:
                resources.append({"label": line, "url": None})

    return render_template(
        "ministry_detail.html",
        church_name=CHURCH_NAME,
        m=m,
        events=items[:6],
        resources=resources,
        safeguarded=slug in SAFEGUARDED_SLUGS,
    )


# ---------- Store ----------

STORE_CATEGORIES = [
    ("books", "Books & resources"),
    ("merchandise", "Merchandise"),
    ("tickets", "Events & tickets"),
    ("music", "Music"),
    ("gifts", "Gifts"),
    ("other", "Other"),
]

STOCK_LABELS = {
    "available": None,                    # nothing shown — the normal case
    "low": "Only a few left",
    "out": "Sold out",
    "preorder": "Available to pre-order",
    "collect": "Collect at church",
}


def store_settings():
    return {
        "enabled": get_setting("store_enabled", "0") == "1",
        "provider": get_setting("store_provider", ""),
        "default_buy_url": get_setting("store_buy_url", ""),
        "delivery_note": get_setting("store_delivery_note", ""),
        "returns_url": get_setting("store_returns_url", ""),
    }


@app.route("/store")
def store():
    cfg = store_settings()
    if not cfg["enabled"]:
        return render_template("store_closed.html", church_name=CHURCH_NAME)

    category = request.args.get("category", "").strip()
    db = get_db()

    sql = "SELECT * FROM products WHERE active=1"
    params = []
    if category and category in dict(STORE_CATEGORIES):
        sql += " AND category=?"
        params.append(category)
    sql += " ORDER BY featured DESC, sort_order, name"
    rows = db.execute(sql, params).fetchall()

    # Only offer category filters that actually have something in them
    used = {
        r["category"] for r in db.execute(
            "SELECT DISTINCT category FROM products WHERE active=1"
        ).fetchall()
    }
    categories = [(slug, label) for slug, label in STORE_CATEGORIES if slug in used]

    featured = [r for r in rows if r["featured"]] if not category else []
    rest = [r for r in rows if not r["featured"]] if not category else rows

    return render_template(
        "store.html",
        church_name=CHURCH_NAME,
        featured=featured,
        products=rest,
        categories=categories,
        active_category=category,
        stock_labels=STOCK_LABELS,
        charity_number=CHARITY_NUMBER,
        **cfg,
    )


@app.route("/store/<int:product_id>")
def product_detail(product_id):
    cfg = store_settings()
    if not cfg["enabled"]:
        abort(404)
    p = get_db().execute(
        "SELECT * FROM products WHERE id=? AND active=1", (product_id,)
    ).fetchone()
    if not p:
        abort(404)
    category_label = dict(STORE_CATEGORIES).get(p["category"], "Other")
    return render_template(
        "product_detail.html",
        church_name=CHURCH_NAME,
        p=p,
        category_label=category_label,
        stock_labels=STOCK_LABELS,
        charity_number=CHARITY_NUMBER,
        **cfg,
    )


# ---------- Giving ----------

CHARITY_NUMBER = "1201405"


def giving_settings():
    return {
        "give_url": get_setting("give_url", ""),
        "regular_url": get_setting("give_regular_url", ""),
        "portal_url": get_setting("give_portal_url", ""),
        "provider": get_setting("give_provider", "Stewardship"),
    }


@app.route("/giving")
def giving():
    db = get_db()
    campaigns = db.execute(
        "SELECT * FROM campaigns WHERE active=1 ORDER BY created_at DESC"
    ).fetchall()
    items = []
    for c in campaigns:
        pct = None
        if c["target_pence"]:
            pct = min(100, round((c["raised_pence"] / c["target_pence"]) * 100))
        items.append({"row": c, "pct": pct})
    return render_template(
        "giving.html",
        church_name=CHURCH_NAME,
        charity_number=CHARITY_NUMBER,
        campaigns=items,
        **giving_settings(),
    )


@app.route("/giving/campaign/<int:campaign_id>")
def campaign_detail(campaign_id):
    db = get_db()
    c = db.execute(
        "SELECT * FROM campaigns WHERE id=? AND active=1", (campaign_id,)
    ).fetchone()
    if not c:
        abort(404)
    pct = None
    if c["target_pence"]:
        pct = min(100, round((c["raised_pence"] / c["target_pence"]) * 100))
    return render_template(
        "campaign_detail.html",
        church_name=CHURCH_NAME,
        charity_number=CHARITY_NUMBER,
        c=c,
        pct=pct,
        **giving_settings(),
    )


@app.route("/giving/gift-aid")
def gift_aid_info():
    return render_template(
        "gift_aid.html",
        church_name=CHURCH_NAME,
        charity_number=CHARITY_NUMBER,
        **giving_settings(),
    )


# ---------- Prayer ----------

CRISIS_NOTE = {
    "line": "If you are in immediate danger or crisis, please don't wait for a reply here.",
    "contacts": [
        ("Samaritans (UK, 24/7)", "116 123"),
        ("Emergency services", "999"),
    ],
}


@app.route("/prayer")
def prayer_wall():
    db = get_db()
    requests_ = db.execute(
        """SELECT * FROM prayers
           WHERE visibility='public' AND status='live' AND kind='request'
           ORDER BY submitted_at DESC LIMIT 50"""
    ).fetchall()
    praises = db.execute(
        """SELECT * FROM prayers
           WHERE visibility='public' AND status='live' AND kind='praise'
           ORDER BY COALESCE(answered_at, submitted_at) DESC LIMIT 20"""
    ).fetchall()
    return render_template(
        "prayer.html",
        church_name=CHURCH_NAME,
        requests=requests_,
        praises=praises,
    )


@app.route("/prayer/new", methods=["GET", "POST"])
def prayer_new():
    if request.method == "POST":
        # Honeypot
        if request.form.get("website"):
            return redirect(url_for("prayer_new", sent=1))

        body = request.form.get("body", "").strip()
        if not body:
            flash("Please write your prayer request before submitting.")
            return render_template(
                "prayer_form.html", church_name=CHURCH_NAME, crisis=CRISIS_NOTE
            )

        visibility = request.form.get("visibility", "public")
        if visibility not in ("public", "team", "pastors"):
            visibility = "public"

        kind = request.form.get("kind", "request")
        if kind not in ("request", "praise"):
            kind = "request"

        # Safeguarding screen: hold sensitive posts for a human, even public ones.
        hold_reason = prayer_screen(body)
        if visibility == "public" and hold_reason:
            status = "held"
        elif visibility == "public":
            status = "live"
        else:
            # Team/pastor requests never appear publicly; they sit in the staff queue.
            status = "private"

        db = get_db()
        db.execute(
            """INSERT INTO prayers (body, author_name, visibility, kind, status,
                                    hold_reason, submitted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                body,
                request.form.get("author_name", "").strip() or None,
                visibility,
                kind,
                status,
                hold_reason,
                datetime.now().isoformat(),
            ),
        )
        db.commit()

        # Only public, immediately-live requests trigger a notification.
        # Held, team-only and pastor-only requests never do.
        if status == "live" and visibility == "public":
            broadcast(
                "prayer",
                "New prayer request",
                "Someone has asked for prayer.",
                url_for("prayer_wall"),
            )

        return redirect(url_for("prayer_new", sent=1, held=1 if status == "held" else None))

    return render_template(
        "prayer_form.html",
        church_name=CHURCH_NAME,
        crisis=CRISIS_NOTE,
        sent=request.args.get("sent"),
        held=request.args.get("held"),
    )


@app.route("/prayer/<int:prayer_id>/pray", methods=["POST"])
def prayer_pray(prayer_id):
    """Increment the 'praying for you' count. Rate-limited per session."""
    prayed = session.get("prayed_for", [])
    if prayer_id in prayed:
        return {"ok": False, "reason": "already"}, 200
    db = get_db()
    row = db.execute(
        "SELECT id FROM prayers WHERE id=? AND status='live' AND visibility='public'",
        (prayer_id,),
    ).fetchone()
    if not row:
        return {"ok": False, "reason": "not_found"}, 404
    db.execute("UPDATE prayers SET pray_count = pray_count + 1 WHERE id=?", (prayer_id,))
    db.commit()
    prayed.append(prayer_id)
    session["prayed_for"] = prayed
    count = db.execute("SELECT pray_count FROM prayers WHERE id=?", (prayer_id,)).fetchone()[0]
    return {"ok": True, "count": count}, 200


@app.route("/prayer/journal")
def prayer_journal():
    return render_template("prayer_journal.html", church_name=CHURCH_NAME)


# ---------- Devotionals ----------

@app.route("/bible/devotionals")
def devotionals():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM devotionals WHERE published=1 ORDER BY created_at DESC"
    ).fetchall()
    items = []
    for r in rows:
        parsed = parse_reference(r["verse_ref"]) if r["verse_ref"] else None
        items.append({"row": r, "ref_link": parsed, "video_embed": embed_url(r["video_url"])})
    today = items[0] if items else None
    archive = items[1:] if len(items) > 1 else []
    return render_template(
        "devotionals.html",
        church_name=CHURCH_NAME,
        today=today,
        archive=archive,
    )


@app.route("/bible/devotionals/<int:devotional_id>")
def devotional_detail(devotional_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM devotionals WHERE id=? AND published=1", (devotional_id,)
    ).fetchone()
    if not row:
        abort(404)
    ref_link = parse_reference(row["verse_ref"]) if row["verse_ref"] else None
    return render_template(
        "devotional_detail.html", church_name=CHURCH_NAME, d=row, ref_link=ref_link,
        video_embed=embed_url(row["video_url"]),
    )


@app.route("/bible/read")
def bible_books():
    return render_template(
        "bible_books.html", church_name=CHURCH_NAME,
        old_testament=OLD_TESTAMENT, new_testament=NEW_TESTAMENT,
    )


@app.route("/bible/read/<book_slug>")
def bible_chapters(book_slug):
    book = BOOKS_BY_SLUG.get(book_slug)
    if not book:
        abort(404)
    return render_template("bible_chapters.html", church_name=CHURCH_NAME, book=book)


DEFAULT_TRANSLATION = "kjv"


def available_translations():
    """Public domain always; licensed ones only when a key is configured."""
    return bible_sources.translations()


@lru_cache(maxsize=512)
def fetch_chapter(book_name, chapter, translation, book_usfm=None):
    return bible_sources.fetch_chapter(
        book_name, chapter, translation, book_id=book_usfm
    )


@app.route("/bible/read/<book_slug>/<int:chapter>")
def bible_read_chapter(book_slug, chapter):
    book = BOOKS_BY_SLUG.get(book_slug)
    if not book or chapter < 1 or chapter > book["chapters"]:
        abort(404)

    all_translations = available_translations()
    translation = request.args.get("translation", DEFAULT_TRANSLATION)
    if translation not in all_translations:
        translation = DEFAULT_TRANSLATION

    error = None
    fell_back = False
    data = None
    try:
        data = fetch_chapter(book["name"], chapter, translation,
                             book_usfm=book.get("usfm"))
    except requests.exceptions.RequestException:
        # One translation being unavailable — a licence lapsing, an ID
        # changing, a provider outage — shouldn't leave someone unable to
        # read at all. Fall back to a public domain text and say so.
        if translation != DEFAULT_TRANSLATION:
            try:
                data = fetch_chapter(book["name"], chapter, DEFAULT_TRANSLATION,
                                     book_usfm=book.get("usfm"))
                translation = DEFAULT_TRANSLATION
                fell_back = True
            except requests.exceptions.RequestException:
                error = True
        else:
            error = True

    gateway_query = f"{book['name']} {chapter}".replace(" ", "%20")

    # Note the read for streaks and badges. Only for signed-in members, and
    # only when the chapter actually loaded — recording a failed fetch as
    # "read today" would be dishonest. Chapters are stored per book/chapter so
    # re-reading the same one doesn't inflate the count.
    new_badges = []
    member = current_member()
    if member and data and not error:
        db = get_db()
        db.execute(
            "INSERT OR IGNORE INTO member_data "
            "(member_id, kind, item_key, payload, updated_at) VALUES (?,?,?,?,?)",
            (member["id"], "read", f"{book_slug}/{chapter}", "{}",
             datetime.now().isoformat(timespec="seconds")),
        )
        achievements.record(db, member["id"], "read")
        new_badges = achievements.evaluate(db, member["id"], total_games=len(GAMES))
        db.commit()

    # Compact book list for the in-reader chapter jump, tagged by testament so
    # the picker can group them without another lookup.
    jump_books = (
        [{"name": b["name"], "slug": b["slug"], "chapters": b["chapters"],
          "testament": "old"} for b in OLD_TESTAMENT]
        + [{"name": b["name"], "slug": b["slug"], "chapters": b["chapters"],
           "testament": "new"} for b in NEW_TESTAMENT]
    )

    return render_template(
        "bible_reader.html",
        church_name=CHURCH_NAME,
        book=book,
        chapter=chapter,
        data=data,
        error=error,
        translation=translation,
        translations=all_translations,
        fell_back=fell_back,
        study_enabled=study_available(),
        new_badges=new_badges,
        jump_books=jump_books,
        gateway_url=f"https://www.biblegateway.com/passage/?search={gateway_query}",
    )


VISIT_DEFAULTS = {
    "visit_address": "",
    "visit_postcode": "",
    "visit_what3words": "",
    "visit_service_times": "Sundays at 10:30am",
    "visit_duration": "About 90 minutes",
    "visit_parking": "",
    "visit_transport": "",
    "visit_accessibility": "",
    "visit_kids": "",
    "visit_dress": "Come as you are — you'll see everything from jeans to smart.",
    "visit_expect": "",
    "visit_contact_email": "",
    "visit_contact_phone": "",
}


def visit_info():
    """Everything the visit page shows, with sensible fallbacks."""
    info = {k: (get_setting(k, v) or v) for k, v in VISIT_DEFAULTS.items()}

    # Build map links from whatever address detail we have. Deep links rather
    # than an embedded map: no API key to manage or pay for, and it opens in
    # whichever maps app the person already uses and trusts.
    full = ", ".join(p for p in [info["visit_address"], info["visit_postcode"]] if p)
    info["full_address"] = full
    if full:
        q = quote_plus(full)
        info["maps_google"] = f"https://www.google.com/maps/dir/?api=1&destination={q}"
        info["maps_apple"] = f"https://maps.apple.com/?daddr={q}"
        info["maps_citymapper"] = f"https://citymapper.com/directions?endcoord=&endname={q}"
    else:
        info["maps_google"] = info["maps_apple"] = info["maps_citymapper"] = ""
    return info


@app.route("/visit")
def plan_visit():
    """For someone thinking about coming for the first time.

    Deliberately answers the practical worries rather than selling the church:
    where to park, what to wear, what happens to the children, how long it
    lasts, and whether anyone will make a fuss of them.
    """
    return render_template(
        "visit.html",
        church_name=CHURCH_NAME,
        info=visit_info(),
    )


@app.route("/admin/visit", methods=["GET", "POST"])
@login_required
def admin_visit():
    saved = False
    if request.method == "POST":
        for key in VISIT_DEFAULTS:
            set_setting(key, (request.form.get(key) or "").strip())
        get_db().commit()
        saved = True
    return render_template(
        "admin_visit.html",
        church_name=CHURCH_NAME,
        info=visit_info(),
        defaults=VISIT_DEFAULTS,
        saved=saved,
    )


@app.route("/more")
def more_hub():
    return render_template("more.html", church_name=CHURCH_NAME)


@app.route("/community/calendar")
def calendar_page():
    today = date.today()
    cat = request.args.get("cat", "all")

    month_param = request.args.get("month")
    if month_param:
        try:
            view_year, view_month = map(int, month_param.split("-"))
            first_day = date(view_year, view_month, 1)
        except (ValueError, TypeError):
            first_day = date(today.year, today.month, 1)
    else:
        first_day = date(today.year, today.month, 1)

    view_year, view_month = first_day.year, first_day.month
    last_day_num = calendar_mod.monthrange(view_year, view_month)[1]
    last_day = date(view_year, view_month, last_day_num)

    # Full weeks (Sun-Sat) covering the month, so the grid has no gaps
    grid_start = first_day - timedelta(days=(first_day.weekday() + 1) % 7)
    grid_end = last_day + timedelta(days=(6 - (last_day.weekday() + 1) % 7))

    db = get_db()
    if cat in ("service", "event"):
        rows = db.execute("SELECT * FROM events WHERE category=?", (cat,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM events").fetchall()

    occ_map = {}
    for row in rows:
        for occ_date in occurrences(row, grid_start, grid_end):
            occ_map.setdefault(occ_date.isoformat(), []).append(row)

    # Build the grid: list of weeks, each a list of day dicts
    weeks = []
    cursor = grid_start
    while cursor <= grid_end:
        week = []
        for _ in range(7):
            iso = cursor.isoformat()
            week.append({
                "date": cursor,
                "iso": iso,
                "in_month": cursor.month == view_month,
                "is_today": cursor == today,
                "categories": sorted({e["category"] for e in occ_map.get(iso, [])}),
                "has_events": iso in occ_map,
            })
            cursor += timedelta(days=1)
        weeks.append(week)

    # Agenda: occurrences within the visible month only, chronological
    agenda_items = []
    for iso, evs in occ_map.items():
        if first_day.isoformat() <= iso <= last_day.isoformat():
            for e in evs:
                agenda_items.append((iso, e))
    agenda_items.sort(key=lambda pair: (pair[0], pair[1]["event_time"]))

    agenda = {}
    for iso, e in agenda_items:
        agenda.setdefault(iso, []).append(e)

    prev_month = _shift_month(first_day, -1)
    next_month = _shift_month(first_day, 1)

    feed_url = url_for("calendar_feed", _external=True)
    webcal_url = feed_url.replace("https://", "webcal://").replace("http://", "webcal://")

    return render_template(
        "calendar.html",
        weeks=weeks,
        weekday_labels=WEEKDAY_LABELS,
        month_label=first_day.strftime("%B %Y"),
        agenda=agenda,
        cat=cat,
        prev_month=prev_month.strftime("%Y-%m"),
        next_month=next_month.strftime("%Y-%m"),
        today_month=today.strftime("%Y-%m"),
        feed_url=feed_url,
        webcal_url=webcal_url,
        church_name=CHURCH_NAME,
    )


def _shift_month(d, delta):
    month = d.month - 1 + delta
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)


@app.route("/event/<int:event_id>.ics")
def event_ics(event_id):
    db = get_db()
    event = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not event:
        abort(404)
    ics_text = build_calendar([event], cal_name=event["title"])
    return Response(
        ics_text,
        mimetype="text/calendar",
        headers={"Content-Disposition": f"attachment; filename=event-{event_id}.ics"},
    )


@app.route("/calendar.ics")
def calendar_feed():
    db = get_db()
    rows = db.execute("SELECT * FROM events ORDER BY event_date").fetchall()
    ics_text = build_calendar(rows, cal_name=f"{CHURCH_NAME} Calendar")
    return Response(ics_text, mimetype="text/calendar")


# ---------- Q&A ----------

@app.route("/questions")
def questions():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM questions WHERE status='answered' ORDER BY answered_at DESC"
    ).fetchall()
    return render_template("questions.html", questions=rows, church_name=CHURCH_NAME)


@app.route("/questions/ask", methods=["GET", "POST"])
def ask_question():
    if request.method == "POST":
        # Honeypot: a real visitor never fills this hidden field in
        if request.form.get("website"):
            return redirect(url_for("ask_question", sent=1))

        question_text = request.form.get("question_text", "").strip()
        if not question_text:
            flash("Please write your question before submitting.")
            return render_template("ask.html", church_name=CHURCH_NAME)

        db = get_db()
        db.execute(
            "INSERT INTO questions (question_text, asker_name, status, submitted_at) VALUES (?, ?, 'pending', ?)",
            (
                question_text,
                request.form.get("asker_name", "").strip() or None,
                datetime.now().isoformat(),
            ),
        )
        db.commit()
        return redirect(url_for("ask_question", sent=1))

    return render_template("ask.html", church_name=CHURCH_NAME, sent=request.args.get("sent"))


# ---------- Kids Games ----------

GAMES = {
    "giant_slayer": {"label": "Giant Slayer", "unit": "points", "higher_is_better": True},
    "manna_maze": {"label": "Manna Maze", "unit": "moves", "higher_is_better": False},
    "memory_game": {"label": "Memory Match", "unit": "moves", "higher_is_better": False},
    "trivia_challenge": {"label": "Bible Trivia Challenge", "unit": "points", "higher_is_better": True},
    "trivia_football": {"label": "Bible Trivia Football", "unit": "touchdowns", "higher_is_better": True},
    "chess": {"label": "Chess", "unit": "toughest bot beaten", "higher_is_better": True},
    "verse_builder": {"label": "Verse Builder", "unit": "points", "higher_is_better": True},
    "books_sprint": {"label": "Books Sprint", "unit": "points", "higher_is_better": True},
    "lost_sheep": {"label": "Lost Sheep", "unit": "searches", "higher_is_better": False},
    "rock_slinger": {"label": "Rock Slinger", "unit": "points", "higher_is_better": True},
}


def leaderboard_display_name(full_name):
    """First name + last initial only — this board is visible to any signed-in
    member, including in the Kids Games section, so we never show a full name."""
    parts = (full_name or "").strip().split()
    if not parts:
        return "A church member"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0]}."


@app.route("/games/giant-slayer")
def giant_slayer():
    return render_template("giant_slayer.html", church_name=CHURCH_NAME)


@app.route("/games/rockslinger/build/<path:filename>")
def rockslinger_build(filename):
    """Serve the Unity build files with explicit headers.

    Unity ships its build brotli-compressed (.br). The browser only knows to
    decompress those if the response carries `Content-Encoding: br`, and if it
    doesn't, Unity is handed compressed bytes and reports "Unable to load
    file" — which looks like a missing file but isn't.

    Flask can work this out from the filename, but only when the Python
    version and the OS mime database both know about `.br`. That landed in
    Python's table in 3.9, and on Windows it comes from the registry, where
    it's usually absent. So it works on one machine and fails on another.

    Setting the headers here removes that whole class of problem.
    """
    safe = os.path.basename(filename)
    build_dir = os.path.join(app.static_folder, "games", "rockslinger", "Build")
    path = os.path.join(build_dir, safe)
    if not os.path.isfile(path):
        abort(404)

    if safe.endswith(".wasm.br"):
        mime = "application/wasm"
    elif safe.endswith(".js.br") or safe.endswith(".js"):
        mime = "application/javascript"
    else:
        mime = "application/octet-stream"

    resp = send_from_directory(build_dir, safe, mimetype=mime)
    if safe.endswith(".br"):
        resp.headers["Content-Encoding"] = "br"
    # These files never change without their name changing, so they can be
    # cached hard. It's an 11 MB download; not repeating it matters.
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@app.route("/games/rock-slinger")
def rock_slinger():
    """A Unity WebGL game contributed by a member of the church.

    Hosted from static/ rather than the Unity default template: that template
    ships Unity branding, a fixed 1080x1920 canvas that overflows every phone,
    and an alert() on failure.
    """
    return render_template("rock_slinger.html", church_name=CHURCH_NAME,
                           member=current_member())


@app.route("/games/verse-builder")
def verse_builder():
    """Reassemble a scrambled verse. Uses the same verse set as the rest of
    the app so nothing new has to be maintained."""
    return render_template(
        "verse_builder.html",
        church_name=CHURCH_NAME,
        verses=VERSES,
    )


@app.route("/games/books-sprint")
def books_sprint():
    """Which book comes first? Position is sent with each book because the
    name alone doesn't tell you where it sits."""
    books = [
        {"name": b["name"], "pos": i}
        for i, b in enumerate(ALL_BOOKS)
    ]
    return render_template(
        "books_sprint.html",
        church_name=CHURCH_NAME,
        books=books,
    )


@app.route("/games/lost-sheep")
def lost_sheep():
    return render_template("lost_sheep.html", church_name=CHURCH_NAME)


@app.route("/games/<game_key>/score", methods=["POST"])
def submit_game_score(game_key):
    """Record a member's best score. Called by each game's own 'Publish score'
    button — never automatically, so nothing is shared without the player
    (or their parent, on a shared device) choosing to."""
    if game_key not in GAMES:
        return {"ok": False, "error": "unknown game"}, 404

    m = current_member()
    if not m:
        return {"ok": True, "signed_in": False}, 200

    data = request.get_json(silent=True) or {}
    try:
        score = int(data.get("score"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid score"}, 400
    if score < 0 or score > 10_000_000:
        return {"ok": False, "error": "score out of range"}, 400

    higher_is_better = GAMES[game_key]["higher_is_better"]
    db = get_db()
    existing = db.execute(
        "SELECT score FROM game_scores WHERE member_id=? AND game_key=?",
        (m["id"], game_key),
    ).fetchone()

    improved = existing is None or (
        score > existing["score"] if higher_is_better else score < existing["score"]
    )
    if improved:
        db.execute(
            """INSERT INTO game_scores (member_id, game_key, score, achieved_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(member_id, game_key) DO UPDATE SET
                 score=excluded.score, achieved_at=excluded.achieved_at""",
            (m["id"], game_key, score, datetime.now().isoformat()),
        )

    # Publishing a score counts as activity whether or not it beat your best,
    # otherwise a bad day at Manna Maze wouldn't count as showing up.
    achievements.record(db, m["id"], "game")
    new_badges = achievements.evaluate(db, m["id"], total_games=len(GAMES))
    db.commit()

    best = score if improved else existing["score"]
    return {
        "ok": True, "signed_in": True, "improved": improved, "best": best,
        "new_badges": [{"name": b["name"], "desc": b["desc"]} for b in new_badges],
    }, 200


@app.route("/games/<game_key>/leaderboard")
def game_leaderboard(game_key):
    if game_key not in GAMES:
        abort(404)
    info = GAMES[game_key]
    order_sql = "DESC" if info["higher_is_better"] else "ASC"
    rows = get_db().execute(
        f"""SELECT gs.member_id, gs.score, gs.achieved_at, m.name
            FROM game_scores gs JOIN members m ON m.id = gs.member_id
            WHERE gs.game_key = ?
            ORDER BY gs.score {order_sql}, gs.achieved_at ASC
            LIMIT 20""",
        (game_key,),
    ).fetchall()

    me = current_member()
    board = [
        {
            "rank": i + 1,
            "name": leaderboard_display_name(r["name"]),
            "score": r["score"],
            "is_me": bool(me and me["id"] == r["member_id"]),
        }
        for i, r in enumerate(rows)
    ]

    return render_template(
        "game_leaderboard.html",
        church_name=CHURCH_NAME,
        game_key=game_key,
        info=info,
        board=board,
        signed_in=bool(me),
    )


@app.route("/games/<game_key>/leaderboard.json")
def game_leaderboard_json(game_key):
    """Leaderboard as JSON, for a game to display rankings on its own screen.

    The web page at /games/<key>/leaderboard is for people; this is for the
    game itself. FOR FINN: a Unity build can fetch this URL to draw the
    leaderboard inside the game. It needs no login and no CSRF token — it's
    read-only public data — so Unity can request it directly with
    UnityWebGL's UnityWebRequest. Returns:
        { "ok": true,
          "board": [ {"rank": 1, "name": "Sam T.", "score": 900}, ... ] }
    """
    if game_key not in GAMES:
        abort(404)
    info = GAMES[game_key]
    order_sql = "DESC" if info["higher_is_better"] else "ASC"
    rows = get_db().execute(
        f"""SELECT gs.score, m.name
            FROM game_scores gs JOIN members m ON m.id = gs.member_id
            WHERE gs.game_key = ?
            ORDER BY gs.score {order_sql}, gs.achieved_at ASC
            LIMIT 20""",
        (game_key,),
    ).fetchall()
    board = [
        {
            "rank": i + 1,
            "name": leaderboard_display_name(r["name"]),
            "score": r["score"],
        }
        for i, r in enumerate(rows)
    ]
    return jsonify({"ok": True, "board": board})


@app.route("/games")
def games_hub():
    # Presentation lives here rather than in GAMES, which is the scoring
    # registry and is also read by the leaderboard and score endpoints.
    # Order is deliberate: gentlest first, chess last.
    tiles = [
        {"key": "rock_slinger", "endpoint": "rock_slinger", "emoji": "🪨",
         "name": "Rock Slinger", "desc": "Five smooth stones · by Finn",
         "c1": "#2DD4BF", "c2": "#0C4F4A"},
        {"key": "memory_game", "endpoint": "memory_game", "emoji": "🃏",
         "name": "Memory Match", "desc": "Find the matching pairs",
         "c1": "#27BAA9", "c2": "#145C54"},
        {"key": "lost_sheep", "endpoint": "lost_sheep", "emoji": "🐑",
         "name": "Lost Sheep", "desc": "Bring them all home",
         "c1": "#23A899", "c2": "#12544D"},
        {"key": "verse_builder", "endpoint": "verse_builder", "emoji": "🧩",
         "name": "Verse Builder", "desc": "Put the verse back together",
         "c1": "#1F9689", "c2": "#104C46"},
        {"key": "manna_maze", "endpoint": "manna_maze", "emoji": "🗺️",
         "name": "Manna Maze", "desc": "Gather it before morning",
         "c1": "#1B847A", "c2": "#0E443F"},
        {"key": "books_sprint", "endpoint": "books_sprint", "emoji": "📖",
         "name": "Books Sprint", "desc": "Which one comes first?",
         "c1": "#17726A", "c2": "#0D3C38"},
        {"key": "trivia_challenge", "endpoint": "trivia_challenge", "emoji": "🎯",
         "name": "Bible Trivia", "desc": "How much do you know?",
         "c1": "#12605A", "c2": "#0A3431"},
        {"key": "trivia_football", "endpoint": "trivia_football", "emoji": "🏈",
         "name": "Trivia Football", "desc": "Answer to move down the field",
         "c1": "#0E4E4A", "c2": "#082C2A"},
        {"key": "giant_slayer", "endpoint": "giant_slayer", "emoji": "🪨",
         "name": "Giant Slayer", "desc": "Five smooth stones",
         "c1": "#0A3C3B", "c2": "#072423"},
        {"key": "chess", "endpoint": "chess_game", "emoji": "♟️",
         "name": "Chess", "desc": "Two players, or the computer",
         "c1": "#062A2B", "c2": "#051C1C"},
    ]
    return render_template("games.html", church_name=CHURCH_NAME, games=tiles)


@app.route("/games/memory")
def memory_game():
    return render_template("memory_game.html", church_name=CHURCH_NAME)


@app.route("/games/trivia-challenge")
def trivia_challenge():
    return render_template(
        "trivia_challenge.html", church_name=CHURCH_NAME, questions=TRIVIA_LADDER
    )


@app.route("/games/trivia-football")
def trivia_football():
    return render_template(
        "trivia_football.html", church_name=CHURCH_NAME, questions=TRIVIA_FOOTBALL
    )


@app.route("/games/manna-maze")
def manna_maze():
    return render_template("manna_maze.html", church_name=CHURCH_NAME)


@app.route("/games/chess")
def chess_game():
    return render_template("chess.html", church_name=CHURCH_NAME)


# ---------- Admin ----------

@app.route("/admin")
@login_required
def admin():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM events ORDER BY event_date ASC, event_time ASC"
    ).fetchall()
    pending_count = db.execute(
        "SELECT COUNT(*) FROM questions WHERE status='pending'"
    ).fetchone()[0]
    held_count = db.execute(
        "SELECT COUNT(*) FROM prayers WHERE status='held'"
    ).fetchone()[0]
    return render_template(
        "admin.html", events=rows, pending_count=pending_count, held_count=held_count
    )


@app.route("/admin/new", methods=["GET", "POST"])
@login_required
def new_event():
    if request.method == "POST":
        db = get_db()
        db.execute(
            """INSERT INTO events (title, category, event_date, event_time, location, description, recurring, ministry)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                request.form["title"],
                request.form["category"],
                request.form["event_date"],
                request.form["event_time"],
                request.form.get("location", ""),
                request.form.get("description", ""),
                request.form.get("recurring", "none"),
                request.form.get("ministry", "").strip() or None,
            ),
        )
        db.commit()
        flash("Event added.")
        return redirect(url_for("admin"))
    return render_template("event_form.html", event=None, ministries=ministry_options())


@app.route("/admin/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
def edit_event(event_id):
    db = get_db()
    if request.method == "POST":
        db.execute(
            """UPDATE events SET title=?, category=?, event_date=?, event_time=?,
               location=?, description=?, recurring=?, ministry=? WHERE id=?""",
            (
                request.form["title"],
                request.form["category"],
                request.form["event_date"],
                request.form["event_time"],
                request.form.get("location", ""),
                request.form.get("description", ""),
                request.form.get("recurring", "none"),
                request.form.get("ministry", "").strip() or None,
                event_id,
            ),
        )
        db.commit()
        flash("Event updated.")
        return redirect(url_for("admin"))
    event = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    return render_template("event_form.html", event=event, ministries=ministry_options())


@app.route("/admin/<int:event_id>/delete", methods=["POST"])
@login_required
def delete_event(event_id):
    db = get_db()
    db.execute("DELETE FROM events WHERE id=?", (event_id,))
    db.commit()
    flash("Event removed.")
    return redirect(url_for("admin"))


# ---------- Admin: Q&A moderation ----------

@app.route("/admin/questions")
@login_required
def admin_questions():
    db = get_db()
    pending = db.execute(
        "SELECT * FROM questions WHERE status='pending' ORDER BY submitted_at ASC"
    ).fetchall()
    answered = db.execute(
        "SELECT * FROM questions WHERE status='answered' ORDER BY answered_at DESC"
    ).fetchall()
    return render_template("admin_questions.html", pending=pending, answered=answered)


@app.route("/admin/questions/<int:question_id>/answer", methods=["POST"])
@login_required
def answer_question(question_id):
    answer_text = request.form.get("answer_text", "").strip()
    if not answer_text:
        flash("Write an answer before publishing.")
        return redirect(url_for("admin_questions"))
    db = get_db()
    db.execute(
        "UPDATE questions SET status='answered', answer_text=?, answered_at=? WHERE id=?",
        (answer_text, datetime.now().isoformat(), question_id),
    )
    db.commit()
    flash("Answer published.")
    return redirect(url_for("admin_questions"))


@app.route("/admin/questions/<int:question_id>/reject", methods=["POST"])
@login_required
def reject_question(question_id):
    db = get_db()
    db.execute("UPDATE questions SET status='rejected' WHERE id=?", (question_id,))
    db.commit()
    flash("Question dismissed.")
    return redirect(url_for("admin_questions"))


@app.route("/admin/questions/<int:question_id>/delete", methods=["POST"])
@login_required
def delete_question(question_id):
    db = get_db()
    db.execute("DELETE FROM questions WHERE id=?", (question_id,))
    db.commit()
    flash("Question deleted.")
    return redirect(url_for("admin_questions"))


# ---------- Admin: Devotionals ----------

@app.route("/admin/email", methods=["GET", "POST"])
@login_required
def admin_email():
    """Check email is working, and send the safeguarding digest on demand.

    emailer.py already had send_test() and send_prayer_digest() written but
    nothing called them, so there was no way to find out whether SMTP worked
    short of asking a member to try signing in.
    """
    db = get_db()
    result = None

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "test":
            to = (request.form.get("to") or "").strip()
            if not to or "@" not in to:
                result = ("bad", "Enter an email address to send the test to.")
            elif not emailer.is_configured():
                result = ("bad", "Email isn't configured yet — see the list below.")
            else:
                ok, message = emailer.send_test(CHURCH_NAME, to)
                result = ("good" if ok else "bad",
                          f"Test sent to {to}." if ok else f"Failed: {message}")

        elif action == "digest":
            to = (request.form.get("to") or "").strip()
            held = db.execute(
                "SELECT body, submitted_at FROM prayers WHERE status='held' "
                "ORDER BY submitted_at ASC"
            ).fetchall()
            if not to or "@" not in to:
                result = ("bad", "Enter an email address to send the digest to.")
            elif not held:
                result = ("bad", "Nothing is held for review, so there's no digest to send.")
            else:
                # No part of the request text goes in the email.
                #
                # A first attempt truncated each request to 70 characters,
                # which turned out to be useless as a safeguard: "Please pray
                # for my mum who is very unwell in hospital" is 67 characters,
                # so a full health disclosure went out untouched. These are
                # exactly the messages held back for review — often the most
                # sensitive things anyone submits — and email is not a private
                # channel. The reminder therefore carries only how many are
                # waiting, when they arrived, and a link to read them behind
                # the admin login.
                items = []
                for i, row in enumerate(held, start=1):
                    when = (row["submitted_at"] or "")[:10]
                    items.append(f"Request {i} — submitted {when}" if when
                                 else f"Request {i}")
                ok, message = emailer.send_prayer_digest(
                    CHURCH_NAME, to, len(held), items,
                    url_for("admin_prayers", _external=True),
                )
                result = ("good" if ok else "bad",
                          f"Digest sent to {to}." if ok else f"Failed: {message}")

    held_count = db.execute(
        "SELECT COUNT(*) FROM prayers WHERE status='held'"
    ).fetchone()[0]

    return render_template(
        "admin_email.html",
        church_name=CHURCH_NAME,
        configured=emailer.is_configured(),
        problems=emailer.config_problems(),
        smtp_host=emailer.SMTP_HOST or "(not set)",
        smtp_port=emailer.SMTP_PORT,
        smtp_from=emailer.SMTP_FROM or "(not set)",
        smtp_security=emailer.SMTP_SECURITY,
        max_recipients=emailer.MAX_RECIPIENTS_PER_SEND,
        held_count=held_count,
        result=result,
    )


@app.route("/admin/status")
@login_required
def admin_status():
    """What's switched on and what isn't.

    Optional features fail silently by design — a missing API key just hides
    the feature rather than breaking the page. That's the right behaviour for
    visitors, but it makes it very hard to tell whether something is off
    because it's misconfigured or because you're looking in the wrong place.
    This page answers that directly.
    """
    import study_assistant

    def state(on, env_names, note_on, note_off, where):
        return {
            "on": on,
            "env": env_names,
            "note": note_on if on else note_off,
            "where": where,
        }

    features = [
        ("Bible study assistant", state(
            study_available(),
            ["GEMINI_API_KEY"],
            f"Working. Model: {study_assistant.current_model()}.",
            "Off. Add GEMINI_API_KEY, then redeploy.",
            "Bible → open any chapter → 'Study help' button, bottom right",
        )),
        ("Web push notifications", state(
            push_is_configured(),
            ["VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_SUBJECT"],
            "Working for browsers.",
            "Off. All three VAPID values are needed.",
            "Settings → Notifications",
        )),
        ("Native app notifications", state(
            native_push_is_configured(),
            ["FCM_SERVER_KEY"],
            "Working for the iOS and Android apps.",
            "Off. Only needed once the native apps are published.",
            "iOS / Android app only",
        )),
        ("Outgoing email", state(
            email_is_configured(),
            ["SMTP_HOST", "SMTP_FROM"],
            "Working. Sign-in links will be delivered.",
            "Off. Members cannot receive sign-in links.",
            "Account → Sign in",
        )),
    ]

    # Where the database actually lives, since that is the other thing people
    # need to be able to confirm at a glance.
    storage = {
        "path": DB_PATH,
        "explicit": bool(os.environ.get("CHURCH_DB")),
        "exists": os.path.exists(DB_PATH),
        "production": _HTTPS_ONLY,
    }

    return render_template(
        "admin_status.html",
        church_name=CHURCH_NAME,
        features=features,
        storage=storage,
    )


@app.route("/admin/data")
@login_required
def admin_data():
    """Where the data lives, plus backup and restore."""
    db = get_db()
    counts = {}
    for label, table in [
        ("Events", "events"), ("Sermons", "sermons"), ("Prayer requests", "prayers"),
        ("Questions", "questions"), ("Devotionals", "devotionals"),
        ("Resources", "resources"), ("Ministries", "ministries"),
        ("Appeals", "campaigns"),
    ]:
        try:
            counts[label] = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error:
            counts[label] = 0

    size = 0
    if os.path.exists(DB_PATH):
        size = os.path.getsize(DB_PATH)
        # WAL and shared-memory files count towards the disk quota too.
        for suffix in ("-wal", "-shm"):
            extra = DB_PATH + suffix
            if os.path.exists(extra):
                size += os.path.getsize(extra)

    # A full disk is one of the few ways SQLite can actually corrupt: writes
    # fail mid-transaction. Surface the headroom so it never comes as a
    # surprise.
    disk_free_mb = disk_total_mb = disk_used_pct = None
    try:
        usage = shutil.disk_usage(os.path.dirname(DB_PATH))
        disk_free_mb = round(usage.free / (1024 * 1024))
        disk_total_mb = round(usage.total / (1024 * 1024))
        if usage.total:
            disk_used_pct = round((usage.used / usage.total) * 100)
    except OSError:
        pass

    return render_template(
        "admin_data.html",
        db_path=DB_PATH,
        db_size_kb=round(size / 1024, 1),
        counts=counts,
        disk_free_mb=disk_free_mb,
        disk_total_mb=disk_total_mb,
        disk_used_pct=disk_used_pct,
    )


@app.route("/admin/data/backup")
@login_required
def admin_backup():
    """Download a complete copy of the database."""
    if not os.path.exists(DB_PATH):
        flash("No database file found yet.")
        return redirect(url_for("admin_data"))

    # Use SQLite's backup API so the copy is consistent even if something
    # is mid-write. Copying the file directly can produce a corrupt backup.
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    source = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(tmp.name)
    with dest:
        source.backup(dest)
    dest.close()
    source.close()

    stamp = date.today().isoformat()
    return send_file(
        tmp.name,
        as_attachment=True,
        download_name=f"clearspring-backup-{stamp}.db",
        mimetype="application/octet-stream",
    )


@app.route("/admin/data/restore", methods=["POST"])
@login_required
def admin_restore():
    """Replace the current database with an uploaded backup."""
    upload = request.files.get("backup")
    if not upload or not upload.filename:
        flash("Choose a backup file first.")
        return redirect(url_for("admin_data"))

    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    upload.save(tmp.name)
    tmp.close()

    # Verify it's actually a usable SQLite database before overwriting anything.
    try:
        check = sqlite3.connect(tmp.name)
        tables = {r[0] for r in check.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        check.close()
    except sqlite3.Error:
        os.unlink(tmp.name)
        flash("That file isn't a valid database. Nothing was changed.")
        return redirect(url_for("admin_data"))

    if "events" not in tables:
        os.unlink(tmp.name)
        flash("That doesn't look like a Clearspring backup. Nothing was changed.")
        return redirect(url_for("admin_data"))

    # Keep the current database aside before replacing it.
    import shutil
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, f"{DB_PATH}.before-restore-{stamp}")

    # Close this request's connection first. Replacing the file underneath an
    # open handle leaves it pointing at the old, now-unlinked file.
    old = g.pop("db", None)
    if old is not None:
        try:
            old.close()
        except sqlite3.Error:
            pass

    # In WAL mode the database is three files: the .db plus -wal and -shm.
    # Replacing only the .db leaves the old -wal in place, and SQLite will
    # replay it over the restored file — so the restore silently appears to
    # work while the old data comes back. Checkpoint and clear them.
    for suffix in ("-wal", "-shm"):
        stale = DB_PATH + suffix
        if os.path.exists(stale):
            try:
                shutil.copy2(stale, f"{stale}.before-restore-{stamp}")
            except OSError:
                pass
            try:
                os.remove(stale)
            except OSError:
                pass

    shutil.move(tmp.name, DB_PATH)

    # The uploaded file arrives in whatever journal mode it was saved in.
    # Put it back into WAL so the restored database behaves like the original.
    try:
        fresh = sqlite3.connect(DB_PATH)
        fresh.execute("PRAGMA journal_mode=WAL")
        fresh.close()
    except sqlite3.Error:
        pass

    flash("Backup restored. Your previous data was saved alongside it just in case.")
    return redirect(url_for("admin_data"))


# ---------- Admin: Notifications ----------

@app.route("/admin/notifications", methods=["GET", "POST"])
@login_required
def admin_notifications():
    db = get_db()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        type_key = request.form.get("type_key", "emergency")
        url_path = request.form.get("url", "/").strip() or "/"

        if not title or not body:
            flash("Both a title and a message are needed.")
        elif not push_is_configured():
            flash("Notifications aren't configured on this server yet.")
        else:
            sent, failed = broadcast(type_key, title, body, url_path)
            flash(f"Sent to {sent} device{'s' if sent != 1 else ''}."
                  + (f" {failed} failed." if failed else ""))
        return redirect(url_for("admin_notifications"))

    counts = {}
    rows = db.execute("SELECT prefs_json FROM push_subscriptions").fetchall()
    for t in NOTIFICATION_TYPES:
        counts[t["key"]] = 0
    for row in rows:
        try:
            prefs = json.loads(row["prefs_json"])
        except (ValueError, TypeError):
            continue
        for k, v in prefs.items():
            if v and k in counts:
                counts[k] += 1

    return render_template(
        "admin_notifications.html",
        types=NOTIFICATION_TYPES,
        counts=counts,
        total=len(rows),
        configured=push_is_configured(),
    )


@app.route("/admin/notifications/check")
@login_required
def notification_check():
    """Plain diagnostics so setup problems are visible rather than guesswork."""
    import notifications as notif_mod

    key_ok, key_msg = notif_mod.validate_public_key()

    checks = [
        {
            "label": "pywebpush installed",
            "ok": notif_mod.PUSH_AVAILABLE,
            "fix": "Run:  pip install pywebpush",
        },
        {
            "label": "VAPID_PUBLIC_KEY set",
            "ok": bool(notif_mod.VAPID_PUBLIC_KEY),
            "fix": "Set it in the same window before running the app.",
        },
        {
            "label": "VAPID_PRIVATE_KEY set",
            "ok": bool(notif_mod.VAPID_PRIVATE_KEY),
            "fix": "Set it in the same window before running the app.",
        },
        {
            "label": "Public key valid",
            "ok": key_ok,
            "fix": key_msg,
        },
        {
            "label": "Ready to send",
            "ok": notif_mod.is_configured() and key_ok,
            "fix": "All of the above must pass.",
        },
    ]

    db = get_db()
    subs = db.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0]

    return render_template(
        "notification_check.html",
        checks=checks,
        subs=subs,
        key_length=len(notif_mod.VAPID_PUBLIC_KEY),
        key_message=key_msg,
        public_key_preview=(notif_mod.VAPID_PUBLIC_KEY[:14] + "…")
        if notif_mod.VAPID_PUBLIC_KEY else "(not set)",
    )


# ---------- Admin: Resources ----------

@app.route("/admin/resources")
@login_required
def admin_resources():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM resources ORDER BY category, sort_order, title"
    ).fetchall()
    grouped = []
    for slug, name, _ in RESOURCE_CATEGORIES:
        items = [r for r in rows if r["category"] == slug]
        grouped.append({"slug": slug, "name": name, "items": items})
    return render_template("admin_resources.html", grouped=grouped)


def _save_resource(resource_id):
    db = get_db()
    kind = request.form.get("kind", "link")
    fields = (
        request.form.get("title", "").strip(),
        request.form.get("category", "growing"),
        request.form.get("summary", "").strip() or None,
        request.form.get("body", "").strip() or None,
        request.form.get("url", "").strip() or None,
        kind,
        request.form.get("author", "").strip() or None,
        int(request.form.get("sort_order") or 0),
        1 if request.form.get("published") else 0,
    )
    if resource_id:
        db.execute(
            """UPDATE resources SET title=?, category=?, summary=?, body=?, url=?,
               kind=?, author=?, sort_order=?, published=? WHERE id=?""",
            fields + (resource_id,),
        )
    else:
        db.execute(
            """INSERT INTO resources (title, category, summary, body, url, kind,
               author, sort_order, published, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            fields + (datetime.now().isoformat(),),
        )
    db.commit()


@app.route("/admin/resources/new", methods=["GET", "POST"])
@login_required
def new_resource():
    if request.method == "POST":
        _save_resource(None)
        flash("Resource added.")
        return redirect(url_for("admin_resources"))
    return render_template(
        "resource_form.html", r=None, categories=RESOURCE_CATEGORIES
    )


@app.route("/admin/resources/<int:resource_id>/edit", methods=["GET", "POST"])
@login_required
def edit_resource(resource_id):
    db = get_db()
    if request.method == "POST":
        _save_resource(resource_id)
        flash("Resource updated.")
        return redirect(url_for("admin_resources"))
    r = db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone()
    if not r:
        abort(404)
    return render_template(
        "resource_form.html", r=r, categories=RESOURCE_CATEGORIES
    )


@app.route("/admin/resources/<int:resource_id>/delete", methods=["POST"])
@login_required
def delete_resource(resource_id):
    db = get_db()
    db.execute("DELETE FROM resources WHERE id=?", (resource_id,))
    db.commit()
    flash("Resource deleted.")
    return redirect(url_for("admin_resources"))


# ---------- Admin: Ministries ----------

@app.route("/admin/ministries")
@login_required
def admin_ministries():
    db = get_db()
    rows = db.execute("SELECT * FROM ministries ORDER BY sort_order, name").fetchall()
    return render_template(
        "admin_ministries.html", ministries=rows, safeguarded=SAFEGUARDED_SLUGS
    )


@app.route("/admin/ministries/<slug>/edit", methods=["GET", "POST"])
@login_required
def edit_ministry(slug):
    db = get_db()
    m = db.execute("SELECT * FROM ministries WHERE slug=?", (slug,)).fetchone()
    if not m:
        abort(404)

    is_safeguarded = slug in SAFEGUARDED_SLUGS

    if request.method == "POST":
        contact_name = request.form.get("contact_name", "").strip() or None
        contact_email = request.form.get("contact_email", "").strip() or None
        contact_phone = request.form.get("contact_phone", "").strip() or None

        # Safeguarding: ministries working with under-18s must not publish a
        # named individual or a personal phone number. Enforced here, not just
        # in the form, so it holds even if the form is bypassed.
        if is_safeguarded:
            contact_name = None
            contact_phone = None

        db.execute(
            """UPDATE ministries SET name=?, tagline=?, description=?, meets=?,
               location=?, contact_name=?, contact_email=?, contact_phone=?,
               resources=?, active=? WHERE slug=?""",
            (
                request.form.get("name", "").strip() or m["name"],
                request.form.get("tagline", "").strip() or None,
                request.form.get("description", "").strip() or None,
                request.form.get("meets", "").strip() or None,
                request.form.get("location", "").strip() or None,
                contact_name,
                contact_email,
                contact_phone,
                request.form.get("resources", "").strip() or None,
                1 if request.form.get("active") else 0,
                slug,
            ),
        )
        db.commit()
        if is_safeguarded and (request.form.get("contact_name") or request.form.get("contact_phone")):
            flash("Saved. Personal name and phone were not published — Kids and Youth "
                  "use a role email only, to protect volunteers and children.")
        else:
            flash("Ministry updated.")
        return redirect(url_for("admin_ministries"))

    return render_template("ministry_form.html", m=m, is_safeguarded=is_safeguarded)


# ---------- Admin: Store ----------

@app.route("/admin/store")
@login_required
def admin_store():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM products ORDER BY active DESC, featured DESC, sort_order, name"
    ).fetchall()
    return render_template(
        "admin_store.html",
        products=rows,
        categories=STORE_CATEGORIES,
        **store_settings(),
    )


@app.route("/admin/store/settings", methods=["POST"])
@login_required
def admin_store_settings():
    set_setting("store_enabled", "1" if request.form.get("store_enabled") else "0")
    set_setting("store_provider", request.form.get("store_provider", "").strip())
    set_setting("store_buy_url", request.form.get("store_buy_url", "").strip())
    set_setting("store_delivery_note", request.form.get("store_delivery_note", "").strip())
    set_setting("store_returns_url", request.form.get("store_returns_url", "").strip())
    flash("Store settings saved.")
    return redirect(url_for("admin_store"))


def _save_product(product_id):
    db = get_db()
    fields = (
        request.form.get("name", "").strip(),
        request.form.get("category", "other"),
        request.form.get("summary", "").strip() or None,
        request.form.get("description", "").strip() or None,
        _pence(request.form.get("price")),
        request.form.get("price_note", "").strip() or None,
        request.form.get("image_url", "").strip() or None,
        request.form.get("buy_url", "").strip() or None,
        request.form.get("stock", "available"),
        1 if request.form.get("featured") else 0,
        int(request.form.get("sort_order") or 0),
        1 if request.form.get("active") else 0,
    )
    if product_id:
        db.execute(
            """UPDATE products SET name=?, category=?, summary=?, description=?,
               price_pence=?, price_note=?, image_url=?, buy_url=?, stock=?,
               featured=?, sort_order=?, active=? WHERE id=?""",
            fields + (product_id,),
        )
    else:
        db.execute(
            """INSERT INTO products (name, category, summary, description,
               price_pence, price_note, image_url, buy_url, stock, featured,
               sort_order, active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            fields + (datetime.now().isoformat(),),
        )
    db.commit()


@app.route("/admin/store/new", methods=["GET", "POST"])
@login_required
def new_product():
    if request.method == "POST":
        _save_product(None)
        flash("Product added.")
        return redirect(url_for("admin_store"))
    return render_template(
        "product_form.html", p=None, categories=STORE_CATEGORIES, stock_labels=STOCK_LABELS
    )


@app.route("/admin/store/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    db = get_db()
    if request.method == "POST":
        _save_product(product_id)
        flash("Product updated.")
        return redirect(url_for("admin_store"))
    p = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not p:
        abort(404)
    return render_template(
        "product_form.html", p=p, categories=STORE_CATEGORIES, stock_labels=STOCK_LABELS
    )


@app.route("/admin/store/<int:product_id>/delete", methods=["POST"])
@login_required
def delete_product(product_id):
    db = get_db()
    db.execute("DELETE FROM products WHERE id=?", (product_id,))
    db.commit()
    flash("Product deleted.")
    return redirect(url_for("admin_store"))


# ---------- Admin: Giving ----------

@app.route("/admin/giving")
@login_required
def admin_giving():
    db = get_db()
    campaigns = db.execute(
        "SELECT * FROM campaigns ORDER BY active DESC, created_at DESC"
    ).fetchall()
    return render_template(
        "admin_giving.html", campaigns=campaigns, **giving_settings()
    )


@app.route("/admin/giving/settings", methods=["POST"])
@login_required
def admin_giving_settings():
    set_setting("give_provider", request.form.get("give_provider", "").strip())
    set_setting("give_url", request.form.get("give_url", "").strip())
    set_setting("give_regular_url", request.form.get("give_regular_url", "").strip())
    set_setting("give_portal_url", request.form.get("give_portal_url", "").strip())
    flash("Giving links saved.")
    return redirect(url_for("admin_giving"))


def _pence(value):
    """Parse a pounds figure like '2500' or '2,500.50' into pence."""
    if not value:
        return None
    cleaned = str(value).replace(",", "").replace("£", "").strip()
    try:
        return int(round(float(cleaned) * 100))
    except ValueError:
        return None


@app.route("/admin/giving/campaign/new", methods=["GET", "POST"])
@login_required
def new_campaign():
    if request.method == "POST":
        db = get_db()
        db.execute(
            """INSERT INTO campaigns (title, blurb, target_pence, raised_pence,
               give_url, closes_on, active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                request.form.get("title", "").strip(),
                request.form.get("blurb", "").strip() or None,
                _pence(request.form.get("target")),
                _pence(request.form.get("raised")) or 0,
                request.form.get("give_url", "").strip() or None,
                request.form.get("closes_on") or None,
                1 if request.form.get("active") else 0,
                datetime.now().isoformat(),
            ),
        )
        db.commit()
        flash("Campaign created.")
        return redirect(url_for("admin_giving"))
    return render_template("campaign_form.html", c=None)


@app.route("/admin/giving/campaign/<int:campaign_id>/edit", methods=["GET", "POST"])
@login_required
def edit_campaign(campaign_id):
    db = get_db()
    if request.method == "POST":
        db.execute(
            """UPDATE campaigns SET title=?, blurb=?, target_pence=?, raised_pence=?,
               give_url=?, closes_on=?, active=? WHERE id=?""",
            (
                request.form.get("title", "").strip(),
                request.form.get("blurb", "").strip() or None,
                _pence(request.form.get("target")),
                _pence(request.form.get("raised")) or 0,
                request.form.get("give_url", "").strip() or None,
                request.form.get("closes_on") or None,
                1 if request.form.get("active") else 0,
                campaign_id,
            ),
        )
        db.commit()
        flash("Campaign updated.")
        return redirect(url_for("admin_giving"))
    c = db.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    if not c:
        abort(404)
    return render_template("campaign_form.html", c=c)


@app.route("/admin/giving/campaign/<int:campaign_id>/delete", methods=["POST"])
@login_required
def delete_campaign(campaign_id):
    db = get_db()
    db.execute("DELETE FROM campaigns WHERE id=?", (campaign_id,))
    db.commit()
    flash("Campaign deleted.")
    return redirect(url_for("admin_giving"))


# ---------- Admin: Sermons ----------

@app.route("/admin/sermons")
@login_required
def admin_sermons():
    db = get_db()
    rows = db.execute("SELECT * FROM sermons ORDER BY preached_on DESC").fetchall()
    return render_template(
        "admin_sermons.html",
        sermons=rows,
        live_url=get_setting("live_stream_url", ""),
        live_on=get_setting("live_is_on", "0") == "1",
    )


@app.route("/admin/sermons/live", methods=["POST"])
@login_required
def admin_live_settings():
    set_setting("live_stream_url", request.form.get("live_stream_url", "").strip())
    set_setting("live_is_on", "1" if request.form.get("live_is_on") else "0")
    flash("Live stream settings saved.")
    return redirect(url_for("admin_sermons"))


@app.route("/admin/sermons/new", methods=["GET", "POST"])
@login_required
def new_sermon():
    if request.method == "POST":
        _save_sermon(None)
        title = request.form.get("title", "").strip()
        if request.form.get("notify") and request.form.get("published"):
            sent, _ = broadcast(
                "sermon",
                "New message available",
                title,
                url_for("watch_hub"),
            )
            flash(f"Sermon added. Notified {sent} device{'s' if sent != 1 else ''}.")
        else:
            flash("Sermon added.")
        return redirect(url_for("admin_sermons"))
    return render_template("sermon_form.html", s=None)


@app.route("/admin/sermons/<int:sermon_id>/edit", methods=["GET", "POST"])
@login_required
def edit_sermon(sermon_id):
    db = get_db()
    if request.method == "POST":
        _save_sermon(sermon_id)
        flash("Sermon updated.")
        return redirect(url_for("admin_sermons"))
    row = db.execute("SELECT * FROM sermons WHERE id=?", (sermon_id,)).fetchone()
    if not row:
        abort(404)
    return render_template("sermon_form.html", s=row)


def _save_sermon(sermon_id):
    """Shared insert/update for the sermon form."""
    db = get_db()
    mins = request.form.get("duration_minutes", "").strip()
    try:
        duration = int(float(mins) * 60) if mins else None
    except ValueError:
        duration = None

    fields = (
        request.form.get("title", "").strip(),
        request.form.get("speaker", "").strip() or None,
        request.form.get("series", "").strip() or None,
        request.form.get("topic", "").strip() or None,
        request.form.get("passage", "").strip() or None,
        request.form.get("summary", "").strip() or None,
        request.form.get("preached_on") or date.today().isoformat(),
        request.form.get("video_url", "").strip() or None,
        request.form.get("audio_url", "").strip() or None,
        duration,
        1 if request.form.get("published") else 0,
    )

    if sermon_id:
        db.execute(
            """UPDATE sermons SET title=?, speaker=?, series=?, topic=?, passage=?,
               summary=?, preached_on=?, video_url=?, audio_url=?, duration_seconds=?,
               published=? WHERE id=?""",
            fields + (sermon_id,),
        )
    else:
        db.execute(
            """INSERT INTO sermons (title, speaker, series, topic, passage, summary,
               preached_on, video_url, audio_url, duration_seconds, published)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            fields,
        )
    db.commit()


@app.route("/admin/sermons/<int:sermon_id>/delete", methods=["POST"])
@login_required
def delete_sermon(sermon_id):
    db = get_db()
    db.execute("DELETE FROM sermons WHERE id=?", (sermon_id,))
    db.commit()
    flash("Sermon deleted.")
    return redirect(url_for("admin_sermons"))


# ---------- Admin: Live Polls ----------

@app.route("/admin/polls")
@login_required
def admin_polls():
    db = get_db()
    polls = db.execute(
        "SELECT * FROM polls ORDER BY (status = 'live') DESC, created_at DESC"
    ).fetchall()
    polls_with_options = []
    for p in polls:
        options = db.execute(
            "SELECT * FROM poll_options WHERE poll_id=? ORDER BY sort_order, id",
            (p["id"],),
        ).fetchall()
        polls_with_options.append({"row": p, "options": options})
    return render_template("admin_polls.html", polls=polls_with_options)


@app.route("/admin/polls/new", methods=["POST"])
@login_required
def new_poll():
    question = request.form.get("question", "").strip()
    show_results = "live" if request.form.get("show_results") == "live" else "after_close"
    option_labels = [
        v.strip() for v in request.form.getlist("option") if v.strip()
    ]

    if not question or len(option_labels) < 2:
        flash("A poll needs a question and at least two options.")
        return redirect(url_for("admin_polls"))

    db = get_db()
    cur = db.execute(
        "INSERT INTO polls (question, status, show_results, created_at) "
        "VALUES (?, 'draft', ?, ?)",
        (question, show_results, datetime.now().isoformat()),
    )
    poll_id = cur.lastrowid
    for i, label in enumerate(option_labels):
        db.execute(
            "INSERT INTO poll_options (poll_id, label, sort_order) VALUES (?, ?, ?)",
            (poll_id, label, i),
        )
    db.commit()
    flash("Poll created. Open it when you're ready to take votes.")
    return redirect(url_for("admin_polls"))


@app.route("/admin/polls/<int:poll_id>/open", methods=["POST"])
@login_required
def open_poll(poll_id):
    db = get_db()
    poll = db.execute("SELECT * FROM polls WHERE id=?", (poll_id,)).fetchone()
    if not poll:
        abort(404)
    # Only one poll live at a time — close any other so the Watch page
    # never has to reconcile two active polls at once.
    db.execute(
        "UPDATE polls SET status='closed', closed_at=? "
        "WHERE status='live' AND id != ?",
        (datetime.now().isoformat(), poll_id),
    )
    db.execute(
        "UPDATE polls SET status='live', opened_at=? WHERE id=?",
        (datetime.now().isoformat(), poll_id),
    )
    db.commit()
    flash("Poll is live.")
    return redirect(url_for("admin_polls"))


@app.route("/admin/polls/<int:poll_id>/close", methods=["POST"])
@login_required
def close_poll(poll_id):
    db = get_db()
    db.execute(
        "UPDATE polls SET status='closed', closed_at=? WHERE id=?",
        (datetime.now().isoformat(), poll_id),
    )
    db.commit()
    flash("Poll closed.")
    return redirect(url_for("admin_polls"))


@app.route("/admin/polls/<int:poll_id>/delete", methods=["POST"])
@login_required
def delete_poll(poll_id):
    db = get_db()
    # SQLite foreign keys aren't enforced on this connection, so the
    # options need deleting explicitly rather than relying on the
    # table's ON DELETE CASCADE.
    db.execute("DELETE FROM poll_options WHERE poll_id=?", (poll_id,))
    db.execute("DELETE FROM polls WHERE id=?", (poll_id,))
    db.commit()
    flash("Poll deleted.")
    return redirect(url_for("admin_polls"))


# ---------- Admin: Prayer ----------

@app.route("/admin/prayers")
@login_required
def admin_prayers():
    db = get_db()
    held = db.execute(
        "SELECT * FROM prayers WHERE status='held' ORDER BY submitted_at ASC"
    ).fetchall()
    private = db.execute(
        "SELECT * FROM prayers WHERE status='private' ORDER BY submitted_at DESC"
    ).fetchall()
    live = db.execute(
        "SELECT * FROM prayers WHERE status='live' ORDER BY submitted_at DESC LIMIT 40"
    ).fetchall()
    hidden = db.execute(
        "SELECT * FROM prayers WHERE status='hidden' ORDER BY submitted_at DESC LIMIT 20"
    ).fetchall()
    return render_template(
        "admin_prayers.html", held=held, private=private, live=live, hidden=hidden
    )


@app.route("/admin/prayers/<int:prayer_id>/<action>", methods=["POST"])
@login_required
def admin_prayer_action(prayer_id, action):
    db = get_db()
    if action == "approve":
        db.execute("UPDATE prayers SET status='live', hold_reason=NULL WHERE id=?", (prayer_id,))
        flash("Prayer request published.")
    elif action == "hide":
        db.execute("UPDATE prayers SET status='hidden' WHERE id=?", (prayer_id,))
        flash("Prayer request hidden from the wall.")
    elif action == "answered":
        db.execute(
            "UPDATE prayers SET kind='praise', answered_at=? WHERE id=?",
            (datetime.now().isoformat(), prayer_id),
        )
        flash("Marked as answered — moved to praise reports.")
    elif action == "delete":
        db.execute("DELETE FROM prayers WHERE id=?", (prayer_id,))
        flash("Prayer request deleted.")
    else:
        abort(404)
    db.commit()
    return redirect(url_for("admin_prayers"))


@app.route("/admin/devotionals")
@login_required
def admin_devotionals():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM devotionals ORDER BY created_at DESC"
    ).fetchall()
    return render_template("admin_devotionals.html", devotionals=rows)


@app.route("/admin/devotionals/new", methods=["GET", "POST"])
@login_required
def new_devotional():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        if not title or not body:
            flash("A devotional needs a title and a body.")
            return render_template("devotional_form.html", devotional=None)
        db = get_db()
        db.execute(
            "INSERT INTO devotionals (title, verse_ref, body, video_url, created_at, published) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                title,
                request.form.get("verse_ref", "").strip() or None,
                body,
                request.form.get("video_url", "").strip() or None,
                datetime.now().isoformat(),
                1 if request.form.get("published") else 0,
            ),
        )
        db.commit()
        flash("Devotional saved.")
        return redirect(url_for("admin_devotionals"))
    return render_template("devotional_form.html", devotional=None)


@app.route("/admin/devotionals/<int:devotional_id>/edit", methods=["GET", "POST"])
@login_required
def edit_devotional(devotional_id):
    db = get_db()
    if request.method == "POST":
        db.execute(
            "UPDATE devotionals SET title=?, verse_ref=?, body=?, video_url=?, published=? "
            "WHERE id=?",
            (
                request.form.get("title", "").strip(),
                request.form.get("verse_ref", "").strip() or None,
                request.form.get("body", "").strip(),
                request.form.get("video_url", "").strip() or None,
                1 if request.form.get("published") else 0,
                devotional_id,
            ),
        )
        db.commit()
        flash("Devotional updated.")
        return redirect(url_for("admin_devotionals"))
    row = db.execute("SELECT * FROM devotionals WHERE id=?", (devotional_id,)).fetchone()
    if not row:
        abort(404)
    return render_template("devotional_form.html", devotional=row)


@app.route("/admin/devotionals/<int:devotional_id>/delete", methods=["POST"])
@login_required
def delete_devotional(devotional_id):
    db = get_db()
    db.execute("DELETE FROM devotionals WHERE id=?", (devotional_id,))
    db.commit()
    flash("Devotional deleted.")
    return redirect(url_for("admin_devotionals"))


if __name__ == "__main__":
    init_db()
    # Debug mode exposes an interactive console that runs arbitrary code to
    # anyone who can trigger an error, so it is off by default and only turns
    # on when FLASK_DEBUG is set explicitly — and never on Render, whatever
    # the environment says. To debug locally, set FLASK_DEBUG=1 in your
    # settings.bat (or the shell) before starting.
    debug = os.environ.get("FLASK_DEBUG", "0") == "1" and not os.environ.get("RENDER")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, host="0.0.0.0", port=port)
else:
    init_db()
