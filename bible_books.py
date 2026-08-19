import re


def _slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


_OLD_TESTAMENT = [
    ("Genesis", 50), ("Exodus", 40), ("Leviticus", 27), ("Numbers", 36),
    ("Deuteronomy", 34), ("Joshua", 24), ("Judges", 21), ("Ruth", 4),
    ("1 Samuel", 31), ("2 Samuel", 24), ("1 Kings", 22), ("2 Kings", 25),
    ("1 Chronicles", 29), ("2 Chronicles", 36), ("Ezra", 10), ("Nehemiah", 13),
    ("Esther", 10), ("Job", 42), ("Psalms", 150), ("Proverbs", 31),
    ("Ecclesiastes", 12), ("Song of Solomon", 8), ("Isaiah", 66), ("Jeremiah", 52),
    ("Lamentations", 5), ("Ezekiel", 48), ("Daniel", 12), ("Hosea", 14),
    ("Joel", 3), ("Amos", 9), ("Obadiah", 1), ("Jonah", 4),
    ("Micah", 7), ("Nahum", 3), ("Habakkuk", 3), ("Zephaniah", 3),
    ("Haggai", 2), ("Zechariah", 14), ("Malachi", 4),
]

_NEW_TESTAMENT = [
    ("Matthew", 28), ("Mark", 16), ("Luke", 24), ("John", 21),
    ("Acts", 28), ("Romans", 16), ("1 Corinthians", 16), ("2 Corinthians", 13),
    ("Galatians", 6), ("Ephesians", 6), ("Philippians", 4), ("Colossians", 4),
    ("1 Thessalonians", 5), ("2 Thessalonians", 3), ("1 Timothy", 6), ("2 Timothy", 4),
    ("Titus", 3), ("Philemon", 1), ("Hebrews", 13), ("James", 5),
    ("1 Peter", 5), ("2 Peter", 3), ("1 John", 5), ("2 John", 1),
    ("3 John", 1), ("Jude", 1), ("Revelation", 22),
]

OLD_TESTAMENT = [{"name": n, "slug": _slugify(n), "chapters": c} for n, c in _OLD_TESTAMENT]
NEW_TESTAMENT = [{"name": n, "slug": _slugify(n), "chapters": c} for n, c in _NEW_TESTAMENT]
ALL_BOOKS = OLD_TESTAMENT + NEW_TESTAMENT

# USFM book codes, the standard identifiers used by API.Bible and most
# scripture data formats. Listed in canonical order so they zip onto the
# book lists above without needing a name-matching step, which would break
# on spelling variations like "Psalms" vs "Psalm".
_USFM_OT = [
    "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT", "1SA", "2SA",
    "1KI", "2KI", "1CH", "2CH", "EZR", "NEH", "EST", "JOB", "PSA", "PRO",
    "ECC", "SNG", "ISA", "JER", "LAM", "EZK", "DAN", "HOS", "JOL", "AMO",
    "OBA", "JON", "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL",
]
_USFM_NT = [
    "MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH",
    "PHP", "COL", "1TH", "2TH", "1TI", "2TI", "TIT", "PHM", "HEB", "JAS",
    "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV",
]

assert len(_USFM_OT) == len(OLD_TESTAMENT), "USFM/OT length mismatch"
assert len(_USFM_NT) == len(NEW_TESTAMENT), "USFM/NT length mismatch"

for _book, _code in zip(OLD_TESTAMENT, _USFM_OT):
    _book["usfm"] = _code
for _book, _code in zip(NEW_TESTAMENT, _USFM_NT):
    _book["usfm"] = _code

BOOKS_BY_SLUG = {b["slug"]: b for b in ALL_BOOKS}

# Map lowercased book names to slugs for reference parsing
_NAME_TO_SLUG = {b["name"].lower(): b["slug"] for b in ALL_BOOKS}


def parse_reference(ref):
    """Turn a reference like 'Psalms 23' or '1 Corinthians 13' into
    (book_slug, chapter) or None if it can't be parsed."""
    ref = ref.strip()
    parts = ref.rsplit(" ", 1)
    if len(parts) != 2:
        return None
    book_name, chapter_str = parts
    try:
        chapter = int(chapter_str)
    except ValueError:
        return None
    slug = _NAME_TO_SLUG.get(book_name.lower())
    if not slug:
        return None
    return (slug, chapter)
