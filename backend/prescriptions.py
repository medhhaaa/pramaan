"""In-app prescriptions and the medicine reminders they create. (Medha)

    create_prescription(conn, "p8", doctor_id, [{"medicine": "Metformin", "dose": "500mg",
                        "frequency": "BD", "duration_days": 30}], start_date=date(2026, 11, 1))
        -> prescription id. Each item gets reminders at its dose times from start to end date.

An item is ACTIVE while its status is 'active' and its end date is today or later. Renewing an
item (refill approval) makes a new prescription version that starts the day after the old one
ends, marks the old item 'renewed', and moves its reminders to the new item's dates.
"""
import json
from datetime import date, timedelta

# reminder times for common Indian prescription abbreviations; anything else: once, 08:00
DOSE_TIMES = {
    "OD": ["08:00"], "ONCE DAILY": ["08:00"], "HS": ["21:00"], "AT NIGHT": ["21:00"],
    "BD": ["08:00", "20:00"], "BID": ["08:00", "20:00"], "TWICE DAILY": ["08:00", "20:00"],
    "TDS": ["08:00", "14:00", "20:00"], "TID": ["08:00", "14:00", "20:00"],
    "QID": ["08:00", "12:00", "16:00", "20:00"],
}


def dose_times(frequency):
    return DOSE_TIMES.get((frequency or "").strip().upper(), ["08:00"])


def add_item(conn, prescription_id, patient_id, item, start, previous_item_id=None):
    end = start + timedelta(days=int(item["duration_days"]) - 1)
    times = item.get("dose_times") or dose_times(item.get("frequency"))
    cur = conn.execute(
        """INSERT INTO prescription_items (prescription_id, patient_id, medicine, dose, frequency,
               duration_days, start_date, end_date, dose_times, status, previous_item_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
        (prescription_id, patient_id, item["medicine"], item.get("dose"), item.get("frequency"),
         int(item["duration_days"]), start.isoformat(), end.isoformat(), json.dumps(times), previous_item_id),
    )
    for t in times:
        conn.execute(
            "INSERT INTO reminders (patient_id, prescription_item_id, time_of_day, start_date, end_date)"
            " VALUES (?, ?, ?, ?, ?)",
            (patient_id, cur.lastrowid, t, start.isoformat(), end.isoformat()),
        )
    return cur.lastrowid


def create_prescription(conn, patient_id, doctor_id, items, start_date, previous_id=None, created_at=None):
    cur = conn.execute(
        "INSERT INTO prescriptions (patient_id, doctor_id, previous_id, created_at)"
        " VALUES (?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))",
        (patient_id, doctor_id, previous_id, created_at),
    )
    for item in items:
        add_item(conn, cur.lastrowid, patient_id, item, start_date)
    return cur.lastrowid


def is_active(item, today):
    return item["status"] == "active" and item["end_date"] >= today.isoformat()


def renew_item(conn, item, doctor_id, today):
    """Refill approval: a new prescription version with the same medicine, dose and duration,
    starting the day after the old item ends (or today if it already ended). The old item's
    reminders are extended to the new end date and point at the new item.
    Returns (new prescription id, new item id)."""
    start = max(date.fromisoformat(item["end_date"]) + timedelta(days=1), today)
    pres = conn.execute(
        "INSERT INTO prescriptions (patient_id, doctor_id, previous_id) VALUES (?, ?, ?)",
        (item["patient_id"], doctor_id, item["prescription_id"]),
    )
    end = start + timedelta(days=int(item["duration_days"]) - 1)
    new = conn.execute(
        """INSERT INTO prescription_items (prescription_id, patient_id, medicine, dose, frequency,
               duration_days, start_date, end_date, dose_times, status, previous_item_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
        (pres.lastrowid, item["patient_id"], item["medicine"], item["dose"], item["frequency"],
         item["duration_days"], start.isoformat(), end.isoformat(), item["dose_times"], item["id"]),
    )
    conn.execute("UPDATE prescription_items SET status = 'renewed' WHERE id = ?", (item["id"],))
    # same reminder rows (so past Taken / Skipped taps stay attached), now running to the new end
    conn.execute("UPDATE reminders SET end_date = ?, prescription_item_id = ? WHERE prescription_item_id = ?",
                 (end.isoformat(), new.lastrowid, item["id"]))
    return pres.lastrowid, new.lastrowid
