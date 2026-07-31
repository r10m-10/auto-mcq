# AutoMCQ — Agent Rules

## What this repo is
AutoMCQ is a Chrome/Firefox extension that auto-clicks MCQ answers in online
test-prep classes (JEE/NEET style platforms). Students spend in-app "credits"
to arm a click (Normal = 5s deliberate delay, Fast = instant), and earn
credits by watching rewarded ads (offerwall). Backend is FastAPI + SQLite,
deployed on a Hack Club Nest VPS behind Caddy at automcq.reyaanshsharma.com.

## Repo layout
- `extension/` — the browser extension (popup UI, content scripts). DO NOT TOUCH.
- `backend/main.py` — the entire current backend: all live endpoints
  (POST /link-device, GET /balance, POST /consume-click, POST /grant,
  GET /history) plus grant/consume logic, defined directly as route
  handlers in this one file. This is deployed and running in production
  via systemd on r10. Treat it as entirely read-only — do not edit it,
  even additively. There is no `backend/app/` package, despite what an
  earlier version of this file said.
- `backend/routers/` — NEW. Where new routers/endpoints get added, as
  separate files that import and call functions from `main.py` rather
  than duplicating them. Wiring a new router into production requires
  adding one line (`app.include_router(...)`) to `main.py` — since that
  file is off-limits to you, write the router fully, then stop and tell
  me it's ready to wire; I'll add that one line myself.
- `backend/tests/` — NEW. `pytest` and `httpx` are not yet installed in
  the venv — installing them there is fine; do not touch
  `requirements.txt` without asking first.
- `website/` — NEW. Companion website (claim page, landing page). This is
  primarily your workspace for this phase.

If anything else in this repo doesn't match what this file describes,
stop and tell me the discrepancy before working around it — don't guess
and proceed.

## Hard rules — do not break these
1. **Never edit anything under `extension/`.** Not even formatting, not even
   a typo fix. If the extension needs a change, stop and tell me — I'll do
   it myself or open a separate session for it.
2. **Never edit `backend/main.py`.** It is the entire deployed backend:
   the live endpoints (POST /link-device, GET /balance,
   POST /consume-click, POST /grant, GET /history) and the grant/consume
   credit ledger logic, defined directly as route handlers in this one
   file. Treat it as read-only reference — do not edit it, even additively.
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