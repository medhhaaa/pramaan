# Pramaan

Turns a patient's scattered medical PDFs into a verified, dated health timeline.
Every fact links to the exact line in its source document. Read [CLAUDE.md](CLAUDE.md) first.

## One-time setup (everyone)

Needs Python 3.11+, Node 20+, Git.

```bash
git clone https://github.com/medhhaaa/pramaan.git
cd pramaan

# Python (backend + pipeline)
python -m venv .venv
.venv\Scripts\activate          # Windows   (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt

# secrets: copy the example and fill in your values (never commit .env)
copy .env.example .env          # Mac/Linux: cp .env.example .env

# Frontend
cd frontend
npm install
cd ..
```

## Run

```bash
# 1. reset the database: demo users + patients p1-p5, plus p1's sample facts (no AI calls)
python -m backend.seed
#    OR build the REAL demo from every synthetic PDF, through the same steps as upload:
python -m backend.load_demo --saved    # uses Ashil's saved AI results: no AI calls, takes seconds
python -m backend.load_demo            # calls the AI for every PDF (~8 min, ~100k Groq tokens)
#    Groq's free tier gives the WHOLE TEAM 200,000 tokens per day: use --saved for normal work.

# 2. backend on http://localhost:8000  (try routes at http://localhost:8000/docs)
uvicorn backend.main:app --reload --port 8000

# 3. frontend on http://localhost:5173
cd frontend && npm run dev

# check the AI key works (needs LLM_API_KEY in .env)
python -m pipeline.llm
```

Demo logins: `doctor` / `doctor123`, `sunita` / `sunita123`, `guestdoctor` / `guest123` (a doctor at another clinic: sees nobody until a patient shares by QR / code).

## What works right now

| Part | State |
|---|---|
| `POST /login`, `GET /patients`, `GET /patients/{id}/timeline` | Working on sample data |
| All other API routes | Stubs that return 501, ready to fill in |
| `pipeline/llm.py` (`call_llm`) | Working: anthropic / openai / ollama |
| `pipeline/read_pdf.py` | Working |
| Other pipeline files, `backend/logic/` | Stubs with agreed function names |
| Frontend | Vite + React, `USE_DUMMY = true` in `src/api.js`, shows the p1 timeline |

## Who owns what

| Person | Folders |
|---|---|
| Ashil | `data/`, `pipeline/` |
| Core backend (setup lead) | `backend/db.py`, `auth.py`, `seed.py`, `main.py`, `recompute.py`, routes patients, upload, timeline, documents, corrections, `logic/wrong_patient.py` |
| Deeksha | `backend/logic/` flags, echo, badges; routes medications, flags; later styling + slides |
| Medha | `frontend/`, `backend/routes/` ask, questions, brief, check_medicine, metrics, audit, delete |

Shared, change only after telling the team: `CLAUDE.md`, `shared/sample_facts.json`, the fact format, the API list, database tables.

## Git workflow

```bash
git checkout main && git pull
git checkout -b ashil/extraction        # name/what-you-are-doing
# ...work, commit small and often...
git push -u origin ashil/extraction
# open a Pull Request into main on GitHub, merge it, then start the next branch from fresh main
```

- **Never push directly to `main`.** Every change goes through a branch + pull request.
- **No AI co-authors:** don't add Claude as a collaborator, and remove any `Co-Authored-By: Claude` line from commits or PRs.
- Never commit `.env`, API keys, `backend/pramaan.db` or files in `storage/`.
- Pull `main` into your branch every few hours (`git pull origin main`) to catch conflicts early.
