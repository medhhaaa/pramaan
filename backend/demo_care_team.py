"""Demo data for the doctor features: Dr. Rao's care team. (Medha)  Synthetic data only.

    python -m backend.demo_care_team     rebuild it (dates relative to today; run on demo day)

backend/load_demo.py runs this after loading the documents. Dr. Rao (drrao / drrao123) has
5 care-team patients, one per My Patients tag, in this order:

    Meena  (p7)  refill_request    Metformin 500mg BD, an in-app prescription from Dr. Rao.
                                   Evening doses: 8 of the last 14 taken (~55%), mornings all
                                   taken. Sulfa allergy on record. Pending refill request.
                                   Scope: diabetes only.
    Sunita (p1)  new_report        a report uploaded after Dr. Rao last opened her records
    Iqbal  (p2)  missed_doses      Telmisartan 40mg OD from Dr. Rao: 8 of 14 doses taken (57%)
                                   Scope: hypertension only.
    Lakshmi(p3)  followup_overdue  follow-up date 5 days ago, no consult since it was set
    Arjun  (p4)  stable

Also: Dr. Suresh Kotian (drkotian / drkotian123) has been on Sunita's care team for 220 days
with no consult record, so Sunita sees "Keep Dr. Suresh Kotian on your care team?".
"""
import os
import sys
from datetime import date, datetime, timedelta, timezone

from backend.db import get_conn
from backend.prescriptions import create_prescription
from backend.routes.consult_records import build_snapshot, create_consult_record

DEMO_PATIENTS = ["p1", "p2", "p3", "p4", "p7"]
DEMO_DOCTORS = ["drrao", "drkotian"]


def at(days_ago, hour=10):
    """UTC timestamp string, `days_ago` days before now, at `hour`:00."""
    day = datetime.now(timezone.utc).date() - timedelta(days=days_ago)
    return f"{day.isoformat()} {hour:02d}:00:00"


def day(days_ago):
    return datetime.now(timezone.utc).date() - timedelta(days=days_ago)


def user_id(conn, username):
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    return row["id"] if row else None


def clear(conn, doctor_ids):
    q = ",".join("?" for _ in DEMO_PATIENTS)
    for table in ("care_team", "refill_requests", "dose_logs", "reminders", "prescription_items",
                  "prescriptions", "notifications", "consult_records"):
        conn.execute(f"DELETE FROM {table} WHERE patient_id IN ({q})", DEMO_PATIENTS)
    d = ",".join("?" for _ in doctor_ids)
    conn.execute(f"DELETE FROM audit_log WHERE user_id IN ({d})", doctor_ids)


def add_team(conn, patient_id, doctor_id, scope="all", days_ago=60, **extra):
    conn.execute(
        """INSERT INTO care_team (patient_id, doctor_id, scope, status, created_at, last_confirmed_at,
               followup_on, followup_set_at) VALUES (?, ?, ?, 'active', ?, ?, ?, ?)""",
        (patient_id, doctor_id, scope, at(days_ago), at(days_ago),
         extra.get("followup_on"), extra.get("followup_set_at")),
    )


def viewed(conn, doctor_id, patient_id, days_ago):
    conn.execute(
        "INSERT INTO audit_log (user_id, action, patient_id, detail, created_at) VALUES (?, 'view_brief', ?, 'demo', ?)",
        (doctor_id, patient_id, at(days_ago, 11)),
    )


def log_doses(conn, patient_id, reminder_id, days, taken_days, skipped_days=()):
    """Taps for the last `days` days (1 = yesterday). Days in neither list get no tap (missed)."""
    for n in range(1, days + 1):
        status = "taken" if n in taken_days else "skipped" if n in skipped_days else None
        if status:
            conn.execute(
                "INSERT INTO dose_logs (patient_id, reminder_id, dose_date, status, logged_at) VALUES (?, ?, ?, ?, ?)",
                (patient_id, reminder_id, day(n).isoformat(), status, at(n, 21)),
            )


def reminder_ids(conn, prescription_id):
    return {r["time_of_day"]: r["id"] for r in conn.execute(
        """SELECT r.id, r.time_of_day FROM reminders r JOIN prescription_items i ON i.id = r.prescription_item_id
           WHERE i.prescription_id = ?""", (prescription_id,))}


def prescribed(conn, doctor_id, patient_id, scope, prescription_id, days_ago):
    """The consult record every prescription gets (snapshot of the brief as of today's data)."""
    items = [dict(r) for r in conn.execute(
        "SELECT medicine, dose, frequency, duration_days FROM prescription_items WHERE prescription_id = ?",
        (prescription_id,))]
    conn.commit()  # the brief syncs questions on its own connection: let it see (and not wait on) our writes
    snapshot = build_snapshot(patient_id, {"kind": "care_team", "scope": scope})
    create_consult_record(conn, doctor_id, patient_id, "prescription", snapshot,
                          {"action": "prescribe", "prescription_id": prescription_id, "items": items},
                          created_at=at(days_ago))


def build():
    with get_conn() as conn:
        rao, kotian = user_id(conn, "drrao"), user_id(conn, "drkotian")
        have = {r["id"] for r in conn.execute("SELECT id FROM patients")}
        if not rao or not kotian or not set(DEMO_PATIENTS) <= have:
            print("demo_care_team: run python -m backend.seed first (needs drrao, drkotian and p1-p4, p7)")
            return
        clear(conn, [rao, kotian])

        # every demo document counts as uploaded 30 days ago...
        q = ",".join("?" for _ in DEMO_PATIENTS)
        conn.execute(f"UPDATE documents SET uploaded_at = ? WHERE patient_id IN ({q})", [at(30), *DEMO_PATIENTS])
        # ...except Sunita's latest report, uploaded yesterday (after Dr. Rao last looked)
        latest = conn.execute(
            "SELECT id FROM documents WHERE patient_id = 'p1' AND held_back = 0 ORDER BY document_date DESC, id DESC"
        ).fetchone()
        if latest:
            conn.execute("UPDATE documents SET uploaded_at = ? WHERE id = ?", (at(1), latest["id"]))

        # Meena: refill request
        add_team(conn, "p7", rao, '["diabetes"]', days_ago=90)
        pres = create_prescription(conn, "p7", rao, [
            {"medicine": "Metformin", "dose": "500mg", "frequency": "BD", "duration_days": 30}],
            start_date=day(26), created_at=at(26))
        prescribed(conn, rao, "p7", ["diabetes"], pres, 26)
        times = reminder_ids(conn, pres)
        log_doses(conn, "p7", times["08:00"], 26, taken_days=range(1, 27))
        evening_taken = {1, 2, 4, 5, 7, 9, 12, 13} | set(range(15, 27))   # 8 of the last 14
        log_doses(conn, "p7", times["20:00"], 26, taken_days=evening_taken, skipped_days={3, 8, 10, 14})
        item = conn.execute("SELECT id FROM prescription_items WHERE prescription_id = ?", (pres,)).fetchone()
        conn.execute(
            """INSERT INTO refill_requests (patient_id, doctor_id, prescription_item_id, status, patient_note, created_at)
               VALUES ('p7', ?, ?, 'pending', 'My tablets finish in 4 days.', ?)""",
            (rao, item["id"], at(0, 8)),
        )
        viewed(conn, rao, "p7", 3)

        # Sunita: new report (Dr. Rao last looked 5 days ago; a report came in yesterday)
        add_team(conn, "p1", rao, "all", days_ago=120)
        viewed(conn, rao, "p1", 5)
        # Dr. Kotian: on Sunita's care team for 220 days, no consult record -> review prompt
        add_team(conn, "p1", kotian, '["hypertension"]', days_ago=220)
        viewed(conn, kotian, "p1", 200)

        # Iqbal: missed doses
        add_team(conn, "p2", rao, '["hypertension"]', days_ago=100)
        pres = create_prescription(conn, "p2", rao, [
            {"medicine": "Telmisartan", "dose": "40mg", "frequency": "OD", "duration_days": 90}],
            start_date=day(40), created_at=at(40))
        prescribed(conn, rao, "p2", ["hypertension"], pres, 40)
        log_doses(conn, "p2", reminder_ids(conn, pres)["08:00"], 14,
                  taken_days={1, 3, 4, 6, 8, 9, 12, 13}, skipped_days={2, 7})
        viewed(conn, rao, "p2", 4)

        # Lakshmi: follow-up overdue (set 35 days ago for 5 days ago; no consult since)
        add_team(conn, "p3", rao, "all", days_ago=150,
                 followup_on=day(5).isoformat(), followup_set_at=at(35))
        viewed(conn, rao, "p3", 20)

        # Arjun: stable
        add_team(conn, "p4", rao, "all", days_ago=80)
        viewed(conn, rao, "p4", 2)
    print("demo_care_team: Dr. Rao's 5 care-team patients ready (log in as drrao / drrao123)")


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    build()
