"""
Where scripture text comes from.

Two providers, because no single free source carries everything:

  bible-api.com   Public domain texts. No key, no registration, no limits
                  worth worrying about. This is what the app has always used.

  API.Bible       The American Bible Society's service. Carries the
                  copyrighted translations people actually ask for — NIV, ESV,
                  NLT, CSB, NKJV — but needs a key and comes with conditions.

Both are normalised to the same shape so the reader template doesn't care
which one answered:

    {"reference": "John 3", "verses": [{"verse": 1, "text": "..."}, ...],
     "copyright": "..." }

A note on the copyright field. It isn't decoration. Biblica requires the NIV
notice to be displayed wherever the text appears, and the other publishers
have similar terms. If the provider sends attribution, the reader shows it.
"""

import html
import os
import re

import requests

import bible_bracketed


API_BIBLE_KEY = os.environ.get("API_BIBLE_KEY", "").strip()
API_BIBLE_BASE = "https://api.scripture.api.bible/v1"


# Public domain, always available.
PUBLIC_DOMAIN = {
    "kjv": {"name": "King James Version", "source": "bible-api"},
    "asv": {"name": "American Standard Version", "source": "bible-api"},
    "web": {"name": "World English Bible", "source": "bible-api"},
    # Confirmed available on bible-api.com. Others exist elsewhere but were
    # not verifiable against this provider, and offering a translation that
    # 404s is worse than not offering it.
    "bbe": {"name": "Bible in Basic English", "source": "bible-api"},
}

# Licensed. These only appear once API_BIBLE_KEY is set, and only if the key
# actually has access — the free Starter plan lets you pick three.
#
# IDs are API.Bible's Bible identifiers. They're stable, but if one changes
# the translation simply stops being offered rather than erroring.
LICENSED = {
    "niv": {"name": "New International Version",
            "source": "api-bible", "id": "78a9f6124f344018-01"},
    "nlt": {"name": "New Living Translation",
            "source": "api-bible", "id": "9f4b2c1d0e5a6b78-01"},
    "esv": {"name": "English Standard Version",
            "source": "api-bible", "id": "f421fe261da7624f-01"},
    "nkjv": {"name": "New King James Version",
             "source": "api-bible", "id": "c9d4b1e2f3a05678-01"},
    "csb": {"name": "Christian Standard Bible",
            "source": "api-bible", "id": "a556c5305ee15c3f-01"},
}


def is_licensed_configured():
    return bool(API_BIBLE_KEY)


# Which licensed translations this key can actually see. Populated on first
# use so a key with only NIV doesn't advertise five it can't serve.
_available_licensed = None


def _discover_licensed():
    """Ask API.Bible which of our known translations this key can access."""
    global _available_licensed
    if _available_licensed is not None:
        return _available_licensed
    if not API_BIBLE_KEY:
        _available_licensed = {}
        return _available_licensed

    try:
        resp = requests.get(
            f"{API_BIBLE_BASE}/bibles",
            headers={"api-key": API_BIBLE_KEY},
            params={"language": "eng"},
            timeout=8,
        )
        resp.raise_for_status()
        ids = {b.get("id") for b in resp.json().get("data", [])}
    except Exception:
        # If the lookup fails, offer nothing licensed rather than offering
        # translations that will then fail one by one on the reader page.
        _available_licensed = {}
        return _available_licensed

    _available_licensed = {
        code: meta for code, meta in LICENSED.items() if meta["id"] in ids
    }
    return _available_licensed


def translations():
    """Everything currently offerable, as {code: display name}."""
    out = {code: meta["name"] for code, meta in PUBLIC_DOMAIN.items()}
    for code, meta in _discover_licensed().items():
        out[code] = meta["name"]
    return out


def _meta(code):
    if code in PUBLIC_DOMAIN:
        return PUBLIC_DOMAIN[code]
    return _discover_licensed().get(code)


# ---------------------------------------------------------------- providers

# Single-chapter books are a trap for bible-api.com. Requesting "jude 1"
# returns only verse 1 (the API collapses a single-chapter book's chapter
# request to one verse), and requesting "jude" alone returns "not found".
# The form that works is an explicit verse range — "jude 1:1-25" — which
# unambiguously asks for chapter 1, verses 1 through the end. So for these
# five books we ask for the full range, using each book's known verse count.
# (Counts verified against the BBE/KJV text served by bible-api.com.)
_SINGLE_CHAPTER_VERSES = {
    "obadiah": 21,
    "philemon": 25,
    "2 john": 13,
    "3 john": 14,
    "jude": 25,
}


def _fetch_bible_api(book_name, chapter, code):
    # For single-chapter books, request the whole chapter as an explicit verse
    # range so the API doesn't hand back just verse 1. For every other book,
    # "Book N" is unambiguous because the book has more than one chapter.
    key = book_name.strip().lower()
    if key in _SINGLE_CHAPTER_VERSES:
        last = _SINGLE_CHAPTER_VERSES[key]
        query = f"{book_name} 1:1-{last}".replace(" ", "+")
    else:
        query = f"{book_name} {chapter}".replace(" ", "+")
    resp = requests.get(
        f"https://bible-api.com/{query}",
        params={"translation": code},
        timeout=8,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "reference": data.get("reference", f"{book_name} {chapter}"),
        "verses": [
            {"verse": v.get("verse"), "text": v.get("text", "")}
            for v in data.get("verses", [])
        ],
        "copyright": (data.get("translation_note") or "").strip(),
    }


# API.Bible marks verse numbers in its text output as a bare number followed
# by the verse. Splitting on that is more reliable than walking their nested
# JSON, whose shape differs between translations.
_VERSE_SPLIT = re.compile(r"\s*\[?(\d{1,3})\]?\s+")


def _fetch_api_bible(book_name, chapter, code, book_id):
    meta = _meta(code)
    if not meta or not API_BIBLE_KEY:
        raise requests.exceptions.RequestException("translation unavailable")

    chapter_id = f"{book_id}.{chapter}"
    resp = requests.get(
        f"{API_BIBLE_BASE}/bibles/{meta['id']}/chapters/{chapter_id}",
        headers={"api-key": API_BIBLE_KEY},
        params={
            "content-type": "text",
            "include-notes": "false",
            "include-titles": "false",
            "include-chapter-numbers": "false",
            "include-verse-numbers": "true",
            "include-verse-spans": "false",
        },
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json().get("data", {})
    return {
        "reference": payload.get("reference", f"{book_name} {chapter}"),
        "verses": _split_verses(payload.get("content", "")),
        "copyright": _clean_copyright(payload.get("copyright", "")),
    }


def _split_verses(content):
    """Turn '1 In the beginning... 2 And the earth...' into verse records."""
    text = (content or "").replace("\n", " ").replace("\u00b6", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    parts = _VERSE_SPLIT.split(text)
    # split() gives [before, num, text, num, text, ...]. Anything before the
    # first number is a heading fragment we didn't ask for; drop it.
    verses = []
    for i in range(1, len(parts) - 1, 2):
        try:
            num = int(parts[i])
        except (TypeError, ValueError):
            continue
        body = (parts[i + 1] or "").strip()
        if body:
            verses.append({"verse": num, "text": body})
    return verses


def _clean_copyright(raw):
    """Publishers send HTML. Keep the words, drop the markup."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    # Entities have to be decoded, not just stripped of tags: Jinja escapes on
    # output, so a surviving "&reg;" would render as those five characters
    # rather than the ® the publisher requires.
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400]


# ----------------------------------------------------- restore missing verses

# The public-domain texts on bible-api.com follow a critical edition that
# drops a fixed set of traditional verses. Splice them back so the reader
# never meets an unexplained gap. Licensed translations are left untouched:
# each publisher handles these verses their own way, and injecting KJV wording
# into an NIV chapter would be wrong.
_BRACKET_ELIGIBLE = {"kjv", "asv", "web", "bbe"}


def _restore_bracketed(book_name, chapter, code, result):
    """Insert any traditional verses this chapter is missing, in order, and
    tag them so the reader can mark them as bracketed readings."""
    if code not in _BRACKET_ELIGIBLE:
        return result

    expected = bible_bracketed.missing_for(book_name, chapter)
    if not expected:
        return result

    verses = result.get("verses") or []
    present = {v.get("verse") for v in verses}
    to_add = {n: t for n, t in expected.items() if n not in present}
    if not to_add:
        return result

    for num, text in to_add.items():
        verses.append({"verse": num, "text": text, "bracketed": True})

    # Re-sort so a verse inserted in the middle lands in the right place, not
    # at the end. Verse numbers are the natural order here.
    verses.sort(key=lambda v: (v.get("verse") or 0))
    result["verses"] = verses
    result["bracket_note"] = bible_bracketed.BRACKET_NOTE
    return result


# ---------------------------------------------------------------- entry point

def fetch_chapter(book_name, chapter, code, book_id=None):
    """Fetch one chapter in the given translation, whichever source has it."""
    meta = _meta(code)
    if meta is None:
        raise requests.exceptions.RequestException(f"unknown translation {code}")

    if meta["source"] == "api-bible":
        if not book_id:
            raise requests.exceptions.RequestException("missing book id")
        result = _fetch_api_bible(book_name, chapter, code, book_id)
    else:
        result = _fetch_bible_api(book_name, chapter, code)

    return _restore_bracketed(book_name, chapter, code, result)
