"""
Streaks and badges.

A deliberate note on tone. Streaks are a strong motivator, and in a church app
that cuts both ways: the same mechanic that gets someone reading daily can make
them feel they have failed at their faith because they missed a Tuesday. So:

  - A single missed day does not reset the streak. You get one grace day.
  - Alongside the streak we always show days-this-month, which never resets,
    so a broken run is not the only number on the page.
  - Nothing is ever lost. Badges, once earned, stay earned.
  - No notifications nagging people about a streak at risk.

The aim is to encourage returning, not to punish absence.
"""

from datetime import date, datetime, timedelta


# How many consecutive missed days it takes to actually break a run.
# 1 means "miss a day, the streak survives; miss two, it resets".
GRACE_DAYS = 1

# The kinds of thing that count as showing up.
ACTIVITY_SOURCES = {
    "read": "Read the Bible",
    "plan": "Reading plan",
    "journal": "Journal entry",
    "verse": "Saved a verse",
    "game": "Played a game",
}


BADGES = [
    # key, name, description, how it's earned
    {"key": "first_chapter", "name": "First Steps", "icon": "book",
     "desc": "Read your first chapter"},
    {"key": "ten_chapters", "name": "Getting Going", "icon": "book",
     "desc": "Read 10 chapters"},
    {"key": "fifty_chapters", "name": "Well Read", "icon": "book",
     "desc": "Read 50 chapters"},

    {"key": "first_verse", "name": "Worth Keeping", "icon": "bookmark",
     "desc": "Save your first verse"},
    {"key": "twenty_verses", "name": "Verse Collector", "icon": "bookmark",
     "desc": "Save 20 verses"},

    {"key": "first_journal", "name": "In Your Own Words", "icon": "message",
     "desc": "Write your first journal entry"},
    {"key": "ten_journal", "name": "Journal Keeper", "icon": "message",
     "desc": "Write 10 journal entries"},

    {"key": "plan_started", "name": "Setting Out", "icon": "target",
     "desc": "Start a reading plan"},
    {"key": "plan_finished", "name": "Saw It Through", "icon": "target",
     "desc": "Finish a reading plan"},

    {"key": "week_streak", "name": "A Steady Week", "icon": "sunrise",
     "desc": "Seven days in a row"},
    {"key": "month_active", "name": "A Full Month", "icon": "sunrise",
     "desc": "Twenty days in a single month"},

    {"key": "played_game", "name": "Good Sport", "icon": "gamepad",
     "desc": "Play any game"},
    {"key": "all_games", "name": "Tried Everything", "icon": "trophy",
     "desc": "Play every game at least once"},
]

BADGES_BY_KEY = {b["key"]: b for b in BADGES}


# ---------------------------------------------------------------- schema

def ensure_tables(db):
    """Create the tables if they aren't there. Safe to call on every start."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS member_activity (
            member_id INTEGER NOT NULL,
            day TEXT NOT NULL,              -- YYYY-MM-DD, local date
            sources TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (member_id, day),
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS member_badges (
            member_id INTEGER NOT NULL,
            badge_key TEXT NOT NULL,
            earned_at TEXT NOT NULL,
            PRIMARY KEY (member_id, badge_key),
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
        )
    """)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_member_day "
        "ON member_activity(member_id, day DESC)"
    )


# ---------------------------------------------------------------- recording

def record(db, member_id, source, today=None):
    """Note that this member did something today. Idempotent per day/source."""
    if not member_id or source not in ACTIVITY_SOURCES:
        return
    day = (today or date.today()).isoformat()

    row = db.execute(
        "SELECT sources FROM member_activity WHERE member_id=? AND day=?",
        (member_id, day),
    ).fetchone()

    if row is None:
        db.execute(
            "INSERT INTO member_activity (member_id, day, sources) VALUES (?,?,?)",
            (member_id, day, source),
        )
        return

    existing = [s for s in (row["sources"] or "").split(",") if s]
    if source in existing:
        return
    existing.append(source)
    db.execute(
        "UPDATE member_activity SET sources=? WHERE member_id=? AND day=?",
        (",".join(existing), member_id, day),
    )


# ---------------------------------------------------------------- streaks

def _active_days(db, member_id, limit=400):
    rows = db.execute(
        "SELECT day FROM member_activity WHERE member_id=? "
        "ORDER BY day DESC LIMIT ?",
        (member_id, limit),
    ).fetchall()
    out = []
    for r in rows:
        try:
            out.append(date.fromisoformat(r["day"]))
        except ValueError:
            continue
    return out


def current_streak(db, member_id, today=None):
    """Consecutive active days, allowing GRACE_DAYS missed days inside a run.

    Returns (streak_length, is_active_today).
    """
    today = today or date.today()
    days = _active_days(db, member_id)
    if not days:
        return 0, False

    day_set = set(days)
    active_today = today in day_set

    # A run may end today or, if today isn't done yet, yesterday. Anything
    # older than the grace window means the run is over.
    start = None
    for offset in range(0, GRACE_DAYS + 2):
        candidate = today - timedelta(days=offset)
        if candidate in day_set:
            start = candidate
            break
    if start is None:
        return 0, False

    # Walk backwards. A gap is tolerated while it stays within grace.
    streak = 1
    cursor = start
    while True:
        gap = 0
        found = None
        for step in range(1, GRACE_DAYS + 2):
            probe = cursor - timedelta(days=step)
            if probe in day_set:
                found = probe
                gap = step - 1
                break
        if found is None or gap > GRACE_DAYS:
            break
        streak += 1
        cursor = found

    return streak, active_today


def longest_streak(db, member_id):
    """Best run ever, same grace rule."""
    days = sorted(set(_active_days(db, member_id)))
    if not days:
        return 0
    best = run = 1
    for i in range(1, len(days)):
        gap = (days[i] - days[i - 1]).days - 1
        if gap <= GRACE_DAYS:
            run += 1
        else:
            run = 1
        best = max(best, run)
    return best


def days_this_month(db, member_id, today=None):
    """A number that never resets, so a broken streak isn't the only score."""
    today = today or date.today()
    prefix = today.strftime("%Y-%m")
    return db.execute(
        "SELECT COUNT(*) FROM member_activity WHERE member_id=? AND day LIKE ?",
        (member_id, prefix + "%"),
    ).fetchone()[0]


# ---------------------------------------------------------------- badges

def earned(db, member_id):
    rows = db.execute(
        "SELECT badge_key, earned_at FROM member_badges WHERE member_id=?",
        (member_id,),
    ).fetchall()
    return {r["badge_key"]: r["earned_at"] for r in rows}


def _award(db, member_id, key, now=None):
    """Give a badge if it isn't already held. Returns True if newly given."""
    if key not in BADGES_BY_KEY:
        return False
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    cur = db.execute(
        "INSERT OR IGNORE INTO member_badges (member_id, badge_key, earned_at) "
        "VALUES (?,?,?)",
        (member_id, key, stamp),
    )
    return cur.rowcount > 0


def evaluate(db, member_id, total_games=None, today=None):
    """Work out which badges this member has now qualified for.

    Returns a list of newly-earned badge dicts, so the caller can show a
    "you've earned this" note. Existing badges are never removed.
    """
    if not member_id:
        return []

    counts = {}
    for kind in ("verse", "journal", "plan"):
        counts[kind] = db.execute(
            "SELECT COUNT(*) FROM member_data WHERE member_id=? AND kind=?",
            (member_id, kind),
        ).fetchone()[0]

    chapters = db.execute(
        "SELECT COUNT(*) FROM member_data WHERE member_id=? AND kind='read'",
        (member_id,),
    ).fetchone()[0]

    games_played = db.execute(
        "SELECT COUNT(DISTINCT game_key) FROM game_scores WHERE member_id=?",
        (member_id,),
    ).fetchone()[0]

    finished_plans = db.execute(
        "SELECT COUNT(*) FROM member_data WHERE member_id=? AND kind='plan' "
        "AND payload LIKE '%\"finished\": true%'",
        (member_id,),
    ).fetchone()[0]

    streak, _ = current_streak(db, member_id, today=today)
    month = days_this_month(db, member_id, today=today)

    rules = [
        ("first_chapter", chapters >= 1),
        ("ten_chapters", chapters >= 10),
        ("fifty_chapters", chapters >= 50),
        ("first_verse", counts["verse"] >= 1),
        ("twenty_verses", counts["verse"] >= 20),
        ("first_journal", counts["journal"] >= 1),
        ("ten_journal", counts["journal"] >= 10),
        ("plan_started", counts["plan"] >= 1),
        ("plan_finished", finished_plans >= 1),
        ("week_streak", streak >= 7),
        ("month_active", month >= 20),
        ("played_game", games_played >= 1),
        ("all_games", total_games is not None and games_played >= total_games),
    ]

    new = []
    for key, qualified in rules:
        if qualified and _award(db, member_id, key):
            new.append(BADGES_BY_KEY[key])
    return new


def summary(db, member_id, total_games=None, today=None):
    """Everything the badges page needs, in one call."""
    held = earned(db, member_id)
    streak, active_today = current_streak(db, member_id, today=today)
    return {
        "streak": streak,
        "active_today": active_today,
        "longest": longest_streak(db, member_id),
        "month": days_this_month(db, member_id, today=today),
        "earned_count": len(held),
        "total_count": len(BADGES),
        "badges": [
            {**b, "earned": b["key"] in held, "earned_at": held.get(b["key"])}
            for b in BADGES
        ],
    }
