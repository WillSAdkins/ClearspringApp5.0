import calendar
from datetime import date, timedelta, datetime


def _add_month(d):
    month = d.month + 1
    year = d.year
    if month > 12:
        month = 1
        year += 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def occurrences(event_row, range_start, range_end):
    """Yield date objects where this event occurs, between range_start and
    range_end (inclusive). Handles 'none', 'weekly', and 'monthly' recurrence."""
    base = datetime.strptime(event_row["event_date"], "%Y-%m-%d").date()
    recurring = event_row["recurring"] or "none"

    if recurring == "none":
        if range_start <= base <= range_end:
            yield base
        return

    if recurring == "weekly":
        cur = base
        if cur < range_start:
            weeks_ahead = (range_start - cur).days // 7
            cur = cur + timedelta(days=weeks_ahead * 7)
            while cur < range_start:
                cur += timedelta(days=7)
        while cur <= range_end:
            if cur >= base:
                yield cur
            cur += timedelta(days=7)
        return

    if recurring == "monthly":
        cur = base
        while cur <= range_end:
            if cur >= range_start and cur >= base:
                yield cur
            cur = _add_month(cur)
        return
