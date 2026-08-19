"""
Verses that bible-api.com's default text leaves out.

bible-api.com serves a critical text of the KJV: several verses that appear
in the traditional Authorised Version are absent, because modern textual
scholarship judges them later additions not present in the earliest
manuscripts. When the reader fetches, say, Matthew 17, verse 21 simply isn't
in the response, and the page shows 20 -> 22 with a silent gap.

A reader shouldn't hit an unexplained hole in the chapter. So we keep the
traditional KJV wording of exactly those verses here and splice them back in
at the right position. They are marked in the reader as bracketed readings —
which is precisely what a printed KJV does: the verse is there, with a note
that the earliest manuscripts omit it. Nothing is hidden and nothing is
silently invented; the reader sees the whole traditional text and is told
which verses carry that caveat.

This list is fixed and well known. It is the standard set of "missing verses"
between the critical text and the Textus Receptus in the Gospels, Acts and
Romans. The wording below is the Authorised (King James) Version, which is
public domain.

Keyed by (book_name, chapter, verse). Book names match bible_books.py exactly.
"""

# The note shown beneath a chapter that contains any bracketed verse. Kept
# short; the per-verse marker does the pointing.
BRACKET_NOTE = (
    "Verses shown in brackets are present in the traditional King James text "
    "but omitted by most modern critical editions, which follow earlier "
    "manuscripts. They are included here so no traditional reading is missing."
)

BRACKETED_VERSES = {
    ("Matthew", 17, 21):
        "Howbeit this kind goeth not out but by prayer and fasting.",
    ("Matthew", 18, 11):
        "For the Son of man is come to save that which was lost.",
    ("Matthew", 23, 14):
        "Woe unto you, scribes and Pharisees, hypocrites! for ye devour "
        "widows' houses, and for a pretence make long prayer: therefore ye "
        "shall receive the greater damnation.",
    ("Mark", 7, 16):
        "If any man have ears to hear, let him hear.",
    ("Mark", 9, 44):
        "Where their worm dieth not, and the fire is not quenched.",
    ("Mark", 9, 46):
        "Where their worm dieth not, and the fire is not quenched.",
    ("Mark", 11, 26):
        "But if ye do not forgive, neither will your Father which is in "
        "heaven forgive your trespasses.",
    ("Mark", 15, 28):
        "And the scripture was fulfilled, which saith, And he was numbered "
        "with the transgressors.",
    ("Luke", 17, 36):
        "Two men shall be in the field; the one shall be taken, and the "
        "other left.",
    ("Luke", 23, 17):
        "(For of necessity he must release one unto them at the feast.)",
    ("John", 5, 4):
        "For an angel went down at a certain season into the pool, and "
        "troubled the water: whosoever then first after the troubling of the "
        "water stepped in was made whole of whatsoever disease he had.",
    ("Acts", 8, 37):
        "And Philip said, If thou believest with all thine heart, thou "
        "mayest. And he answered and said, I believe that Jesus Christ is the "
        "Son of God.",
    ("Acts", 15, 34):
        "Notwithstanding it pleased Silas to abide there still.",
    ("Acts", 24, 7):
        "But the chief captain Lysias came upon us, and with great violence "
        "took him away out of our hands,",
    ("Acts", 28, 29):
        "And when he had said these words, the Jews departed, and had great "
        "reasoning among themselves.",
    ("Romans", 16, 24):
        "The grace of our Lord Jesus Christ be with you all. Amen.",
}


def missing_for(book_name, chapter):
    """The bracketed verses defined for a chapter, as {verse_num: text}."""
    out = {}
    for (b, c, v), text in BRACKETED_VERSES.items():
        if b == book_name and c == chapter:
            out[v] = text
    return out
