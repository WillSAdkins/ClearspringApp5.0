from datetime import datetime


def escape_ics(text):
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


def build_vevent(event_row):
    dtstart = datetime.strptime(
        f"{event_row['event_date']} {event_row['event_time']}", "%Y-%m-%d %H:%M"
    ).strftime("%Y%m%dT%H%M%S")
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VEVENT",
        f"UID:event-{event_row['id']}@church-app",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{dtstart}",
        f"SUMMARY:{escape_ics(event_row['title'])}",
    ]
    if event_row["location"]:
        lines.append(f"LOCATION:{escape_ics(event_row['location'])}")
    if event_row["description"]:
        lines.append(f"DESCRIPTION:{escape_ics(event_row['description'])}")
    if event_row["recurring"] == "weekly":
        lines.append("RRULE:FREQ=WEEKLY")
    elif event_row["recurring"] == "monthly":
        lines.append("RRULE:FREQ=MONTHLY")
    lines.append("END:VEVENT")
    return lines


def build_calendar(event_rows, cal_name="Church Calendar"):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Church App//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{escape_ics(cal_name)}",
    ]
    for row in event_rows:
        lines.extend(build_vevent(row))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)
