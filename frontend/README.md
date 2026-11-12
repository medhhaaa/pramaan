# Pramaan frontend

React + Vite frontend for Pramaan. Runs on its own in **dummy mode** (no backend needed).

## Run

```bash
npm install
cp .env.example .env.local     # Windows: copy .env.example .env.local
npm run dev                    # http://localhost:5173
```

Logins: `doctor` / `doctor123` (doctor), `sunita` / `sunita123` (patient).
Doctor: open a patient's BRIEF, which asks for a scan first. In dummy mode use **Simulate scan (demo)**.

## Structure

```
src/
  api.js            ONLY file that talks to the backend (USE_DUMMY switch)
  dummy/data.js     synthetic p1 facts in the CLAUDE.md contract
  i18n/             en, hi, kn strings (medicine names and values are never translated)
  context/          login, role, scan session
  components/       layout, sidebar, chips, scan modal, document viewer, patient gate
  pages/            one file per screen
  styles/           theme.css (colours only), app.css (layout)
  lib/format.js     date helpers
```

## Switching to the real backend

1. Start the backend: `uvicorn backend.main:app --reload --port 8000`.
2. In `.env.local` set `VITE_USE_DUMMY=false`.
3. Check each `api.js` function against the route list in CLAUDE.md section 6.

Nothing else should need to change.

## Known gaps (to finish after merge)

- **Logo:** `src/components/Logo.jsx` is a text placeholder. Replace it with your supplied logo file.
- **PDF viewer:** `DocDrawer` shows source lines and highlights the quoted line. Render the real PDF with `react-pdf` when the backend returns `pdf_base64`.
- **Accordions:** sidebar sections are flat links, not collapsible groups yet.
- **Sign-up:** the form is demo-only. Real registration needs a backend route.
- **QR routes:** `createQR` and `scanQR` are **not in CLAUDE.md**. Agree them with the core backend owner. They are marked in `api.js`.
- **Claim Ready** (`/claim`): behind `VITE_ENABLE_CLAIM_READY`. Its PED result text is English only.
- **Upload:** sends the first selected PDF only.
- **Live camera scan:** coded with `html5-qrcode`, not tested on a device.

## Git

Work on a branch, e.g. `medha/frontend-ui`. Open a pull request into `main`. Never push to `main`. Do not add Co-Authored-By lines.
