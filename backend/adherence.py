"""Medicine adherence from reminders and the patient's Taken / Skipped taps. (Medha)

A dose is DUE for each reminder on each day between its start and end date. The window ends
yesterday (today's doses may not be due yet). A due dose with no tap counts as missed.

    adherence(conn, "p8", days=14)                    -> {"due", "taken", "skipped", "missed", "percent"}
    adherence(conn, "p8", days=30, item_ids=[3, 9])   only these prescription items (one medicine)

percent is None when nothing was due. Plain counting, no AI, no judgement: the app shows the
number; what it means is the doctor's call.
"""
from datetime import date, datetime, timedelta, timezone


def today_utc():
    return datetime.now(timezone.utc).date()


def adherence(conn, patient_id, days=14, item_ids=None, today=None):
    today = today or today_utc()
    first, last = today - timedelta(days=days), today - timedelta(days=1)
    sql = "SELECT * FROM reminders WHERE patient_id = ?"
    args = [patient_id]
    if item_ids is not None:
        if not item_ids:
            return {"due": 0, "taken": 0, "skipped": 0, "missed": 0, "percent": None}
        sql += f" AND prescription_item_id IN ({','.join('?' for _ in item_ids)})"
        args += list(item_ids)
    reminders = conn.execute(sql, args).fetchall()

    due = set()
    for r in reminders:
        start = max(date.fromisoformat(r["start_date"]), first)
        end = min(date.fromisoformat(r["end_date"]), last)
        day = start
        while day <= end:
            due.add((r["id"], day.isoformat()))
            day += timedelta(days=1)

    taken = skipped = 0
    if due:
        ids = sorted({rid for rid, _ in due})
        logs = conn.execute(
            f"""SELECT reminder_id, dose_date, status FROM dose_logs
                WHERE reminder_id IN ({','.join('?' for _ in ids)}) AND dose_date BETWEEN ? AND ?""",
            [*ids, first.isoformat(), last.isoformat()],
        ).fetchall()
        for log in logs:
            if (log["reminder_id"], log["dose_date"]) in due:
                taken += log["status"] == "taken"
                skipped += log["status"] == "skipped"
    n = len(due)
    return {"due": n, "taken": taken, "skipped": skipped, "missed": n - taken - skipped,
            "percent": round(100 * taken / n) if n else None}


def daily(conn, patient_id, item_ids, days=30, today=None):
    """[{date, due, taken, skipped}] for each of the last `days` days (oldest first), for the
    reminders of these prescription items: the bars on the refill review screen."""
    today = today or today_utc()
    if not item_ids:
        return []
    q = ",".join("?" for _ in item_ids)
    reminders = conn.execute(f"SELECT * FROM reminders WHERE prescription_item_id IN ({q})", list(item_ids)).fetchall()
    logs = {(r["reminder_id"], r["dose_date"]): r["status"] for r in conn.execute(
        f"""SELECT l.reminder_id, l.dose_date, l.status FROM dose_logs l
            JOIN reminders r ON r.id = l.reminder_id WHERE r.prescription_item_id IN ({q})""", list(item_ids))}
    out = []
    for n in range(days, 0, -1):
        day = (today - timedelta(days=n)).isoformat()
        due = [r for r in reminders if r["start_date"] <= day <= r["end_date"]]
        statuses = [logs.get((r["id"], day)) for r in due]
        out.append({"date": day, "due": len(due), "taken": statuses.count("taken"), "skipped": statuses.count("skipped")})
    return out
