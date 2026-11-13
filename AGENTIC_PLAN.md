# Agentic AI: plan and work split

Two people build this on top of what Pramaan already has. **Akanksha (core backend)** builds the
document agent and the question loop (points 1–11). **Ashil** builds the two assistants, the insurance
help and the disease search (points 12–15). Read CLAUDE.md first; every rule there still applies.

## What already exists (reuse, don't rebuild)

| # | Point | Status | Existing code |
|---|---|---|---|
| 1 | Read PDF / OCR | Built | `pipeline/read_pdf.py`, `pipeline/ocr.py`, `pipeline/handwriting.py` |
| 2 | Classify document | Built | `pipeline/doc_type.py` (incl. bills) |
| 3 | Remove personal details before any AI call | Built | `pipeline/privacy_layer.py` (fail closed), `pipeline/deidentify.py` |
| 4 | Extract facts | Built | `pipeline/extract.py` |
| 5 | Self-check, retry, "App not sure" | Partly | quote check in `pipeline/verify.py` (Akanksha adds retry + stored list) |
| 6 | Merge + flags | Built | `backend/recompute.py`, `backend/logic/` |
| 7–11 | Route, word, send, remind, escalate, update | Partly | `backend/routes/questions.py`, `notifications` table (Akanksha) |
| 12 | Access only to what the user allows | Foundation built | `backend/auth.require_patient_access`, `backend/scope.py` (partial sharing) |
| 13 | Insurance documents | Partly | `backend/routes/claims.py` (checklist, claim-pack zip) |
| 14 | Disease search | Partly | `backend/search.py` (synonyms, optional embeddings) |
| 15 | Doctor and patient assistants | Partly | only `POST /patients/{id}/ask` (one Q&A, hidden behind `ASK_ON`) |

## The rule that keeps this explainable

CLAUDE.md says the AI does only two jobs (extract facts, answer from stored facts). The assistants
stretch that slightly, so we keep it tight:

- The AI may only **pick a tool from a fixed list** and **write the answer** from the tool results.
- **Our code** runs every tool, with the logged-in user's own access. The AI never touches the database.
- Every tool result goes through `privacy_layer.protect()` before the AI sees it; `restore()` puts real
  values back in the answer. `llm.call_llm` refuses to run without that receipt.
- Anything that **changes data** (save to a claim pack, send a question) is never done by the AI: it
  becomes a **confirm card** the user taps.
- Every answer cites `fact_id`s, or says "The records don't mention this." No diagnosis or dose advice.

---

## Ashil: everything to build (points 12–15)

### A. Agreed interfaces with Akanksha (don't change without telling her)

1. **`backend/agent/context.py` (Akanksha delivers this first):**
   ```python
   agent_context(user, patient_id) -> AgentContext   # raises 403 like require_patient_access
   # AgentContext: user, patient_id, role ("doctor" | "patient"), access (from require_patient_access,
   #   includes the partial-sharing scope), identity (name, dob, phone, address for the privacy layer),
   #   lang ("en" | "kn" | "hi")
   ```
   Until it exists, build it yourself as a thin wrapper around `require_patient_access` +
   `backend.routes.privacy.identity_for` + `backend.routes.language.user_language`.
2. **Tool shape:** `def tool(ctx, args: dict) -> {"data": ..., "fact_ids": [...]}`.
   Write tools return `{"proposal": {"action", "args", "summary"}}` instead of doing anything.
3. **Question statuses** (Akanksha adds `to_doctor`, meaning sent straight to the doctor): read them, don't change them.
4. **New tables** go through Akanksha (she owns the database). Agreed here: `claim_pack_items`
   (stay_id, document_id, added_by, created_at) and `assistant_actions` (id, user_id, patient_id,
   action, args JSON, status `proposed|done|cancelled`, created_at).

### B. Point 12: access only to what the user allows

- Every tool gets `ctx` and only uses functions that already take `access`:
  `scope.scoped(facts, ctx.access)`, `brief.build_brief(patient_id, access, lang)`,
  `check_medicine.medicine_warnings(...)`, `claims.checklist_for(conn, patient_id, stay)`.
- A doctor with partial sharing must only get in-scope facts, and the answer says something is hidden
  (reuse the hidden-items message from Ashil's share-scope work).
- Shared access stays read-only: write tools are refused for shared doctors (auth already blocks
  non-GET writes; check it for the confirm endpoint).
- **Tests:** an out-of-scope fact never appears in a tool result, in the prompt, or in the answer;
  another patient's id gives 403.

### C. Point 15: two assistants

**Files:** `backend/agent/tools.py` (registry), `backend/agent/chat.py` (loop), `backend/routes/assistant.py`.

**Tool registry** (`TOOLS = {"patient": {...}, "doctor": {...}}`, each with name, one-line description
for the prompt, args):

| Patient tools | Doctor tools |
|---|---|
| `explain_records(topic)`: facts about a topic, with dates and sources | `brief()`: the 60-second brief |
| `my_medicines()`: current and stopped medicines | `flags(kind?)`: contradictions, duplicates, units, gaps |
| `things_to_check()`: open questions for the patient | `disease_search(disease)`: section D |
| `claim_checklist(stay?)`: section E | `check_medicine(drug)`: allergy / duplicate warnings |
| `save_to_claim_pack(stay, document_ids)`: **write tool, needs confirm** | `open_questions()`: the doctor's Open Questions |
| `who_can_see()`: active shares and care team | `timeline(from?, to?)`: facts in a date range |

**Chat loop (`chat.py`)**, at most 3 tool steps per message:
1. Build the prompt: persona rules + tool list + the user's message (through `protect()`).
2. The AI replies with JSON, either `{"tool": "...", "args": {...}}` or `{"answer": "...", "fact_ids": [...]}`.
   Plain JSON, no provider function-calling, so free.ai / Groq / Ollama all work.
3. Run the tool with `ctx`, `protect()` its result, add it to the prompt, repeat.
4. Final answer: drop made-up `fact_id`s, no citation means "The records don't mention this", `restore()`.
5. Language: answer in `ctx.lang`; medicine names, doses and values stay as written (same rule as `/ask`).

**Routes:**
```
POST /patients/{id}/assistant          {"message", "history": [...]}
  -> {"answer", "fact_ids", "citations", "tools_used": [...], "pending_action": {...} | null}
  422 with {"found": [...]} if the privacy layer blocks the message (show it like the privacy preview)
POST /patients/{id}/assistant/confirm  {"action_id"}   -> runs the proposed action, logs it
POST /patients/{id}/assistant/cancel   {"action_id"}
```
Every route calls `log_action` (the security scorecard checks this).

**Frontend:** `components/AssistantChat.jsx` (shared, `persona` prop), a patient page and a doctor page,
confirm cards for proposals, and "what will be sent" from `POST /patients/{id}/privacy-preview` before
sending. Put it behind a feature switch `ASSISTANT_ON` like `ASK_ON`.

### D. Point 14: disease search for doctors

- **`data/disease_map.json`**: for each disease, its synonyms (reuse `data/synonyms.json`), the drug
  classes / generics that treat it (reuse `check_medicine.DRUGS` classes), its lab tests (e.g. diabetes:
  HbA1c, fasting glucose, PPBS; CKD: creatinine, eGFR, urea), and related events and complications.
- **`GET /patients/{id}/disease-search?q=diabetes`** (doctor; respects scope):
  `{"disease", "matched_terms", "conditions", "medicines", "labs", "events", "documents", "hidden_count"}`,
  each item with `fact_id`, date and source line (click-to-proof works).
- Typing a synonym or brand finds the disease ("sugar", "T2DM", "Glycomet" all lead to diabetes).
  Embeddings from `backend/search.py` are optional; the map must work without them.
- Doctor tool `disease_search` calls the same function.

### E. Point 13: insurance help

- Reuse `claims.py` (checklist, claim pack). Keep Medha's wording rule: "commonly needed", "saved",
  "not saved yet"; never "eligible", "approved" or "guaranteed".
- Patient says e.g. "save my discharge summary and bills for the March hospital stay": the assistant
  finds the stay and documents with tools and returns a **proposal**. On confirm, rows go into
  `claim_pack_items`, and the claim pack zip includes them.
- Tool `claim_checklist` explains what is saved and what is not saved yet, citing documents.

### F. Order (for the demo)

1. `context.py` wrapper (if Akanksha's isn't ready), tool registry, doctor assistant with 4 tools
   (`brief`, `flags`, `disease_search`, `check_medicine`), and `disease_map.json`.
2. Disease search page.
3. Patient assistant + confirm flow + `save_to_claim_pack`.
4. Kannada / Hindi answers, polish.

### G. Done means

- `tests/test_assistant.py` with `call_llm` mocked: picks the right tool, out-of-scope facts never reach
  the prompt, no citation means "not mentioned", a write tool only acts after confirm, a shared doctor
  can't confirm writes.
- `tests/test_disease_search.py`: "diabetes", "sugar" and "Glycomet" give the same results for p1;
  scope respected.
- Security scorecard stays green for audit coverage; all existing tests pass.
- Work on a branch (`ashil/assistants`), small commits, PR into `main`. No AI co-author lines.

---

## Akanksha: what she builds (points 1–11), for reference

- `backend/agent/document_agent.py`: one runner for read → classify → protect → extract → check →
  retry → merge → flag → route question, with every step written to an `agent_steps` table
  ("What the agent did" per document).
- Retry (5): failed quotes are retried with a higher-resolution re-read / the vision model, then a
  stronger model; what still fails goes to a stored **"App not sure"** list.
- Routing (7): clinical conflicts (allergy / medicine contradictions, wrong patient, impossible values)
  go straight to the doctor (`to_doctor`); everything else asks the patient first.
- Hindi question templates (8).
- Reminder after 48 h and escalation to the doctor's Open Questions (9–10), with a background job and a
  demo switch to jump ahead 48 hours.
- A typed **value** answer also saves a correction (11).
- `agent_context()` for point 12.
