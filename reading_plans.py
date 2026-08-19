"""Reading plans: each is a list of days, each day a list of passage references.
References use the same 'Book Chapter' format the Bible reader understands, and are
resolved to reader links at render time. Purely structural — no copyrighted text."""

READING_PLANS = {
    "life-of-jesus": {
        "title": "The Life of Jesus",
        "subtitle": "Walk through the Gospels in 21 days",
        "emoji": "✝️",
        "days": [
            ["Luke 1"], ["Luke 2"], ["Matthew 3"], ["Matthew 4"],
            ["John 1"], ["John 2"], ["John 3"], ["Matthew 5"],
            ["Matthew 6"], ["Matthew 7"], ["Luke 10"], ["Luke 15"],
            ["John 6"], ["John 11"], ["Matthew 21"], ["John 13"],
            ["John 14"], ["John 17"], ["Matthew 26"], ["Matthew 27"],
            ["Matthew 28"],
        ],
    },
    "psalms-30": {
        "title": "Psalms in 30 Days",
        "subtitle": "A month of prayer and praise",
        "emoji": "🎵",
        "days": [
            ["Psalms 1", "Psalms 2"], ["Psalms 8", "Psalms 15"], ["Psalms 16", "Psalms 19"],
            ["Psalms 23", "Psalms 24"], ["Psalms 27"], ["Psalms 32", "Psalms 34"],
            ["Psalms 37"], ["Psalms 40", "Psalms 42"], ["Psalms 46", "Psalms 47"],
            ["Psalms 51"], ["Psalms 55"], ["Psalms 62", "Psalms 63"],
            ["Psalms 66", "Psalms 67"], ["Psalms 71"], ["Psalms 73"],
            ["Psalms 84", "Psalms 86"], ["Psalms 90", "Psalms 91"], ["Psalms 95", "Psalms 96"],
            ["Psalms 100", "Psalms 103"], ["Psalms 104"], ["Psalms 107"],
            ["Psalms 111", "Psalms 112"], ["Psalms 116", "Psalms 118"], ["Psalms 119"],
            ["Psalms 121", "Psalms 122", "Psalms 123"], ["Psalms 126", "Psalms 127", "Psalms 128"],
            ["Psalms 130", "Psalms 131", "Psalms 133"], ["Psalms 136", "Psalms 138"],
            ["Psalms 139"], ["Psalms 145", "Psalms 148", "Psalms 150"],
        ],
    },
    "proverbs-31": {
        "title": "A Proverb a Day",
        "subtitle": "One chapter of wisdom for each day of the month",
        "emoji": "📜",
        "days": [[f"Proverbs {n}"] for n in range(1, 32)],
    },
    "new-believer": {
        "title": "Starting with Jesus",
        "subtitle": "7 days for anyone new to faith",
        "emoji": "🌱",
        "days": [
            ["John 3"], ["Romans 3"], ["Romans 5"], ["Romans 8"],
            ["Ephesians 2"], ["Philippians 4"], ["Romans 12"],
        ],
    },
}


def get_plan(slug):
    return READING_PLANS.get(slug)


def plan_summary():
    """Lightweight list for the index page."""
    return [
        {
            "slug": slug,
            "title": p["title"],
            "subtitle": p["subtitle"],
            "emoji": p["emoji"],
            "length": len(p["days"]),
            "has_video": bool(p.get("video_url")),
        }
        for slug, p in READING_PLANS.items()
    ]
