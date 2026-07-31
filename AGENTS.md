# AutoMCQ — Agent Rules

## What this repo is
AutoMCQ is a Chrome/Firefox extension that auto-clicks MCQ answers in online
test-prep classes (JEE/NEET style platforms). Students spend in-app "credits"
to arm a click (Normal = 5s deliberate delay, Fast = instant), and earn
credits by watching rewarded ads (offerwall). Backend is FastAPI + SQLite,
deployed on a Hack Club Nest VPS behind Caddy at automcq.reyaanshsharma.com.

## Repo layout
- `extension/` — the browser extension (popup UI, content scripts). DO NOT TOUCH.
- `backend/app/` — existing FastAPI app: device linking, credit ledger,
  reward config, click consumption. Endpoints already live in production.
- `backend/app/routers/` — where new routers get added.
- `website/` — NEW. Companion website (claim page, landing page). This is
  primarily your workspace for this phase.

## Hard rules — do not break these
1. **Never edit anything under `extension/`.** Not even formatting, not even
   a typo fix. If the extension needs a change, stop and tell me — I'll do
   it myself or open a separate session for it.
2. **Never edit existing files under `backend/app/models/`,
   `backend/app/core/`, or `backend/app/routers/credits.py`,
   `backend/app/routers/device.py`.** These are the tested, deployed credit
   ledger and device-linking logic. Treat them as read-only reference.
3. **New backend functionality goes in new files only** — e.g.
   `backend/app/routers/website.py` or `backend/app/routers/offerwall.py` —
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
   new under `backend/app/routers/`.
7. Before any commit: show me a summary of changed files and run existing
   tests (`pytest backend/`) to confirm nothing outside `website/`/new files
   changed and nothing broke.
8. If genuinely unsure whether something falls inside these boundaries,
   ask — don't guess and proceed.