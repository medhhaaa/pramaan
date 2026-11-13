"""Demo helpers for the document agent (the demo documents never fail the quote check).

    python -m backend.agent.demo not-sure    add one sample 'App not sure' item to Sunita's 2019
                                             prescription: a medicine the AI 'remembered' that is
                                             not in the document (Glimepiride 2mg OD)
"""
import sys

from backend.db import get_conn
from backend.routes.not_sure import save_not_sure

SAMPLE = {"type": "medication", "name": "Glimepiride", "dose": "2mg", "frequency": "OD", "action": "started",
          "status": "documented", "event_date": "2019-03-12", "quote": "Tab. Glimepiride 2mg OD",
          "drop_reason": "quote not found in document"}

if __name__ == "__main__":
    if sys.argv[1:] != ["not-sure"]:
        sys.exit(__doc__)
    with get_conn() as conn:
        save_not_sure(conn, "p1", "p1_d1", [SAMPLE])
    print("Added a sample 'App not sure' item for p1 (Sunita): open her Timeline.")
