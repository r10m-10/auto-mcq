# AutoMCQ — Agent Rules

## What this repo is
AutoMCQ is a Chrome/Firefox extension that auto-clicks MCQ answers in online
test-prep classes (JEE/NEET style platforms). Students spend in-app "credits"
to arm a click (Normal = 5s deliberate delay, Fast = instant), and earn
credits by watching rewarded ads (offerwall). Backend is FastAPI + SQLite,
deployed on a Hack Club Nest VPS behind Caddy at automcq.reyaanshsharma.com.

## Repo layout
- `extension/` — the browser extension (popup UI, content scripts). DO NOT TOUCH.
- `backend/main.py` — thin entry point only: `from app.main import app` plus a
  `__main__` uvicorn block, so `uvicorn main:app` and `python main.py` both
  work unchanged. This is what systemd runs on r10.
- `backend/app/` — the FastAPI package:
  - `app/main.py` — the `FastAPI()` app instance, `init_db()`, and the
    `include_router(...)` calls (device, credits, offerwall).
  - `app/models.py` — the Pydantic request/response models.
  - `app/db.py` — `DB_PATH`, `get_db()`, `init_db()` (schema).
  - `app/credits.py` — the `grant_credits` / `consume_click` credit ledger logic.
  - `app/routers/device.py` — link-device, balance endpoints.
  - `app/routers/credits.py` — consume-click, grant, history endpoints.
  The tested, deployed credit ledger and device-linking logic lives in these
  files; treat them as read-only reference.
- `backend/routers/` — where NEW routers/endpoints get added, as separate
  files that import and call functions from `app.credits` / `app.db` rather
  than duplicating them. Wiring a new router into production requires adding
  one line (`app.include_router(...)`) to `backend/app/main.py` — since that
  file is off-limits to you, write the router fully, then stop and tell me
  it's ready to wire; I'll add that one line myself.
- `backend/tests/` — pytest suite. `pytest` and `httpx` live in the venv
  (not in `requirements.txt` — do not touch it without asking first).
- `website/` — companion website (landing, claim, privacy pages).

If anything else in this repo doesn't match what this file describes,
stop and tell me the discrepancy before working around it — don't guess
and proceed.

## Hard rules — do not break these
1. **Never edit anything under `extension/`.** Not even formatting, not even
   a typo fix. If the extension needs a change, stop and tell me — I'll do
   it myself or open a separate session for it.
2. **Never edit the deployed backend logic or its assembly:**
   `backend/main.py`, `backend/app/main.py`, `backend/app/models.py`,
   `backend/app/db.py`, `backend/app/credits.py`,
   `backend/app/routers/device.py`, and `backend/app/routers/credits.py`.
   These are the tested, deployed credit ledger and device-linking logic.
   Treat them as read-only reference — do not edit them, even additively.
3. **New backend functionality goes in new files only** — e.g.
   `backend/routers/website.py` or `backend/routers/offerwall.py` —
   that *import and call* existing functions (like the grant/consume logic)
   rather than reimplementing or modifying them. If you find yourself
   needing to change an existing file to make a new feature work, stop and
   ask me first instead of editing it.
4. **No DB schema migrations without asking.** If a new feature seems to
   need a new table or column, propose it and wait for a yes.
5. **No real ad network / offerwall SDK integration yet.** Build against a
   sandboxed/mock offerwall (a fake "watch ad" flow that completes after a
   timer) — real AdSense/offerwall accounts are pending approval under my
   nephew's parents' account. Leave a clearly marked seam
   (e.g. `# TODO(real-offerwall):`) where the real SDK will slot in later.
6. Match the existing backend's style: FastAPI conventions, Pydantic models,
   same test setup as the existing suite (pytest). Write tests for anything
   new under `backend/tests/`.
7. Before any commit: show me a summary of changed files and run existing
   tests (`pytest backend/`) to confirm nothing outside `website/`/new files
   changed and nothing broke.
8. If genuinely unsure whether something falls inside these boundaries,
   ask — don't guess and proceed.