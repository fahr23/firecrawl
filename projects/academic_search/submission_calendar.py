"""Project deadlines and calendar export for submission follow-up."""

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


def calendar_entries(store, public_submission):
    entries = []
    today = date.today()
    for section in ("submissions", "submission-tracking"):
        for item in store.all_workspace_items(section):
            data = item["data"]
            needs_recheck = False
            if section == "submissions":
                check = public_submission(item)
                data = check["data"]
                if check["display_status"] not in {"open", "upcoming"} or not data.get("deadline"):
                    continue
                kind, due = "call", data["deadline"]
                needs_recheck = check["needs_recheck"]
            else:
                if data["status"] != "revision_requested" or not data["revision_due"]:
                    continue
                kind, due = "revision", data["revision_due"]
            day = date.fromisoformat(due)
            remaining = (day - today).days
            entries.append({
                "id": item["id"], "project_id": item["project_id"], "project_name": item["project_name"],
                "title": data["title"], "kind": kind, "date": due, "days_left": remaining,
                "time": data.get("deadline_time"), "timezone": data.get("timezone"),
                "source_url": data.get("source_url"),
                "needs_recheck": needs_recheck,
            })
    return sorted(entries, key=lambda item: (item["date"], item["title"].casefold()))


def _escape(value):
    return str(value).replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace(
        "\n", "\\n",
    ).replace(",", "\\,").replace(";", "\\;")


def _fold(line):
    parts, part, width = [], [], 0
    for char in line:
        size = len(char.encode("utf-8"))
        if width + size > 75:
            parts.append("".join(part))
            part, width = [" "], 1
        part.append(char)
        width += size
    parts.append("".join(part))
    return "\r\n".join(parts)


def calendar_export(entries):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Academic Search//Submission Calendar//EN",
             "CALSCALE:GREGORIAN"]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for item in entries:
        if item["days_left"] < 0:
            continue
        day = date.fromisoformat(item["date"])
        if item["time"] and item["timezone"]:
            stamp = datetime.combine(day, time.fromisoformat(item["time"]), tzinfo=ZoneInfo(item["timezone"]))
            timing = ["DTSTART:" + stamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")]
        else:
            timing = ["DTSTART;VALUE=DATE:" + day.strftime("%Y%m%d")]
        label = "Revision due" if item["kind"] == "revision" else "Submission deadline"
        title = _escape(f"{label} · {item['title']}")
        notes = [item["project_name"], item["source_url"]]
        if item["needs_recheck"]:
            notes.append("Check the official page for changes.")
        lines.extend(["BEGIN:VEVENT", f"UID:{item['kind']}-{item['id']}@academic-search.local", f"DTSTAMP:{timestamp}",
                      *timing, f"SUMMARY:{title}", f"DESCRIPTION:{_escape(chr(10).join(filter(None, notes)))}"])
        for days in (7, 1):
            lines.extend(["BEGIN:VALARM", f"TRIGGER:-P{days}D", "ACTION:DISPLAY",
                          f"DESCRIPTION:{title}", "END:VALARM"])
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(map(_fold, lines)) + "\r\n"
