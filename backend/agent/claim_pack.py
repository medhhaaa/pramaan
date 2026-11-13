"""Claim pack: the documents a patient chose to add to a hospital stay's pack. (Ashil, AGENTIC_PLAN E)

    propose_save(ctx, stay_id, document_ids) -> {"proposal": {...}} or {"data": {"error"}, "fact_ids": []}
    apply_save(ctx, args)                    -> {"added": [...], "already": [...]}   (only after confirm)
    pack_items(conn, stay_id)                -> [document_id, ...]

The assistant never writes: save_to_claim_pack only builds a proposal whose summary OUR code writes
from the database (never the AI's words). apply_save checks everything again when the patient
confirms. Wording follows claims.py: "saved", "not saved yet"; never "eligible" or "approved".
"""
from fastapi import HTTPException

from backend.db import get_conn
from backend.routes.claims import load_stay


def pack_items(conn, stay_id):
    rows = conn.execute("SELECT document_id FROM claim_pack_items WHERE stay_id = ? ORDER BY created_at, document_id",
                        (stay_id,)).fetchall()
    return [r["document_id"] for r in rows]


def _stay_label(stay):
    if stay["admitted_on"] or stay["discharged_on"]:
        return f"the hospital stay {stay['admitted_on'] or 'date not known'} to {stay['discharged_on'] or 'date not known'}"
    return "your hospital stay (dates not known)"


def _check(conn, ctx, stay_id, document_ids):
    """(stay, [document rows]) or raise ValueError with a plain reason."""
    try:
        stay = load_stay(conn, ctx.patient_id, int(stay_id))
    except (HTTPException, TypeError, ValueError):
        raise ValueError("no such hospital stay for this patient")
    ids = list(dict.fromkeys(str(d) for d in (document_ids or []) if d))
    if not ids:
        raise ValueError("no documents given")
    rows = conn.execute(
        f"SELECT id, filename, doc_type, document_date, held_back FROM documents WHERE patient_id = ? "
        f"AND id IN ({','.join('?' * len(ids))})", (ctx.patient_id, *ids),
    ).fetchall()
    found = {r["id"]: dict(r) for r in rows}
    missing = [d for d in ids if d not in found]
    if missing:
        raise ValueError(f"not this patient's documents: {', '.join(missing)}")
    held = [d for d in ids if found[d]["held_back"]]
    if held:
        raise ValueError(f"held back for review (may belong to someone else): {', '.join(held)}")
    return stay, [found[d] for d in ids]


def propose_save(ctx, stay_id, document_ids):
    if ctx.role != "patient" or ctx.read_only:
        return {"data": {"error": "only the patient can change their claim pack"}, "fact_ids": []}
    with get_conn() as conn:
        try:
            stay, docs = _check(conn, ctx, stay_id, document_ids)
        except ValueError as err:
            return {"data": {"error": str(err)}, "fact_ids": []}
        already = set(pack_items(conn, stay["id"]))
    new = [d for d in docs if d["id"] not in already]
    if not new:
        return {"data": {"note": "these documents are already in this claim pack"}, "fact_ids": [],
                "source_ids": [d["id"] for d in docs]}
    names = ", ".join(f"{(d['doc_type'] or 'document').replace('_', ' ')} {d['document_date'] or ''}".strip() for d in new)
    return {"proposal": {
        "action": "save_to_claim_pack",
        "args": {"stay_id": stay["id"], "document_ids": [d["id"] for d in new]},
        "summary": f"Add {len(new)} document(s) to the claim pack for {_stay_label(stay)}: {names}.",
    }}


def apply_save(ctx, args):
    with get_conn() as conn:
        stay, docs = _check(conn, ctx, args.get("stay_id"), args.get("document_ids"))
        already = set(pack_items(conn, stay["id"]))
        added = [d["id"] for d in docs if d["id"] not in already]
        conn.executemany("INSERT OR IGNORE INTO claim_pack_items (stay_id, document_id, added_by) VALUES (?, ?, ?)",
                         [(stay["id"], d, ctx.user["id"]) for d in added])
    return {"stay_id": stay["id"], "added": added, "already": sorted(already & {d["id"] for d in docs})}
