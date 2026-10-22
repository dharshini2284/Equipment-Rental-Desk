# Rental Desk

**Problem 1: Equipment Rental Desk.** A web app for the volunteer desk of a community tool library: staff reserve, lend and take back equipment, late fees are worked out automatically, and the API refuses the mistakes the desk used to make on paper (lending an item that's already out, lending to someone with unpaid fees or a long-overdue loan).

## 2. Live links

| What | URL |
|---|---|
| UI | https://rental-desk-dharshini.netlify.app |
| API docs (Swagger UI) | https://rental-desk-api-tuwe.onrender.com/docs |
| Health | https://rental-desk-api-tuwe.onrender.com/health |

Deployed 21 Oct 2026: API and PostgreSQL on Render (from `render.yaml`), UI on Netlify (see 5a).

- No login: there is no authentication (optional in the brief), so no test credentials.
- Render's free web services sleep after about 15 minutes without traffic. The first request after that can take up to a minute while the container starts; the UI shows a "could not reach the server" message with a retry button if that request times out.

## 3. Tech stack

| Layer | Choice | Hosting |
|---|---|---|
| Backend | Python 3.11, FastAPI 0.115, SQLAlchemy 2.0, Alembic, Pydantic 2 | Render web service (Docker), free plan |
| Database | PostgreSQL 16 in Docker Compose and on Render; SQLite for quick local runs and the default test run | Render PostgreSQL, free plan |
| Frontend | TypeScript, React 18, React Router 6, Vite 5, plain CSS | Netlify, free plan (a Render static site is also defined in `render.yaml`) |
| Tests | pytest + pytest-cov (backend), Vitest (frontend helpers), Playwright (browser end-to-end) | GitHub Actions |
| PDF statements | reportlab 4.2 (pure Python) | part of the API |
| Lint/format | ruff (backend), ESLint + Prettier + `tsc` (frontend) | GitHub Actions |

All choices are from the recommended list.

## 4. Architecture

```
  Browser: React single-page app
     │  JSON over HTTPS; optional X-Test-Clock header (reviewer clock)
     ▼
  FastAPI  (backend/app/main.py)
     │  middleware: request id → JSON request log → unexpected error ⇒ 500 envelope
     │
     ├── api/routes/*      parse + validate input (api/schemas.py), call one service, shape the response
     │        │            api/errors.py maps error types to HTTP codes and one JSON shape
     │        ▼
     ├── services/*        one transaction per use case; row locks; orchestration and logging
     │        │
     │        ├──► domain/*        pure rules, no I/O: state machine, expiry, fees, eligibility
     │        │
     │        └──► persistence/*   SQLAlchemy models, queries, UTC datetime column type
     ▼
  PostgreSQL (Compose, Render)  or  SQLite (local default, tests)
  schema managed by Alembic migrations (backend/migrations)
```

A request like `POST /api/v1/loans/7/checkout` goes: route → `services/loans.check_out` (locks member, item, loan) → `domain/item_state.ensure_loan_action_allowed`, `domain/timing.ensure_not_before`, `services/borrowing.ensure_member_can_borrow` (which uses `domain/eligibility.borrowing_blocks`) → writes → commit → `LoanOut` JSON.

### Folder structure

| Folder | What is in it |
|---|---|
| `backend/app/domain/` | The business rules as pure functions and constants (`policy.py` has every number from the brief). No database or HTTP imports, so they are unit-tested directly. |
| `backend/app/services/` | Use cases (reserve, check out, return, pay, suspend…). Each runs in one transaction, loads and locks rows, calls the domain rules, writes, and returns a read model. |
| `backend/app/reports/` | The member statement rendered as a PDF (layout only; the numbers come from the same service as the JSON statement). |
| `backend/app/persistence/` | SQLAlchemy models with constraints, all queries, the engine/session setup and the `UTCDateTime` column type. |
| `backend/app/api/` | FastAPI routes, request/response schemas, dependencies (session, clock) and error mapping. |
| `backend/migrations/` | Alembic migration(s). `0001_initial_schema.py` creates every table, constraint and index. |
| `backend/tests/` | `unit/` (pure rules), `integration/` (services against a real database, including race tests), `api/` (HTTP-level tests). |
| `backend/scripts/` | `migrate_and_seed.sh` and the container entry point `start.sh`. |
| `frontend/e2e/` | Playwright browser tests that drive the real UI and API end to end. |
| `frontend/src/` | `api/` (typed fetch client), `pages/` (Dashboard, Items, Item detail, Members, Member detail, Overdue, Outbox), `components/` (layout, inline SVG icons, badges, cards, tables), `hooks/`, `lib/` (money, IST time and clock helpers). |
| `.github/workflows/` | CI: backend lint + tests on SQLite with coverage, backend tests on PostgreSQL, and frontend lint, typecheck, tests and build. |

### Where the business rules live, and why

Every rule is in `backend/app/domain/` as a plain function: `timing.py` (48 h hold, 7-day loan, days overdue), `fees.py` (₹10/day, ₹200 cap, replacement-value cap), `eligibility.py` (suspension, ₹100 balance, 14-day overdue, 3 active loans) and `item_state.py` (allowed transitions). Keeping them free of I/O means each boundary can be tested in microseconds with exact timestamps, and the services can't skip one by accident: every write path calls them. The UI only displays what the API returns (for example, it renders the `allowed_actions` list rather than working out what is allowed itself).

## 5. Running locally

### Prerequisites

| Tool | Version used | Needed for |
|---|---|---|
| Python | 3.11 (3.11.2 tested) | backend |
| Node.js / npm | Node 20 (20.20.0 tested), npm 10 | frontend |
| Docker + Compose | Docker 29.1 tested | only for the one-command option |

### Environment variables

Each app has a committed `.env.example`. Every backend variable has a working default, so `.env` files are optional for local runs.

**`backend/.env`**

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./rental_desk.db` | SQLAlchemy URL. `postgres://` / `postgresql://` URLs are accepted and get the psycopg driver automatically. |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated UI origins allowed to call the API. |
| `ALLOW_TEST_CLOCK` | `true` | Whether the `X-Test-Clock` header is honoured (see section 10). |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `SEED_ON_START` | `true` | Container only: run the seed (if the DB is empty) before starting. |
| `PORT` | `8000` | Container only: port uvicorn listens on. |

**`frontend/.env`**

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Public URL of the API, baked in at build time. Leave empty in development. |
| `DEV_API_PROXY_TARGET` | `http://localhost:8000` | Where the Vite dev server forwards `/api` and `/health`. |

### Option A: two terminals (SQLite)

Backend (macOS/Linux shown; on Windows use `.venv\Scripts\activate` and `copy` instead of `cp`):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # optional
python -m alembic upgrade head    # create the schema
python -m app.seed                # load sample data (skips if data already exists)
uvicorn app.main:app --reload --port 8000
```

API on http://localhost:8000, docs on http://localhost:8000/docs.

UI:

```bash
cd frontend
npm ci
npm run dev
```

UI on http://localhost:5173. The dev server proxies `/api` to the backend, so no URL configuration is needed.

### Option B: one command (PostgreSQL + API + UI)

```bash
docker compose up --build
```

UI on http://localhost:8080, API on http://localhost:8000. The backend container migrates and seeds on start. If a port is already taken (the error says `ports are not available … 8080`), pick other host ports; CORS and the UI's API URL follow the variables:

```bash
UI_PORT=8081 API_PORT=8001 docker compose up --build              # bash / zsh
```

```powershell
$env:UI_PORT = "8081"; $env:API_PORT = "8001"; docker compose up --build   # PowerShell
```

Stop with `docker compose down`; add `-v` to delete the database volume.

## 5a. Deployment

**What is actually hosted:** the API and database come from the Render Blueprint below; the UI is on Netlify. The Blueprint also creates a Render static site for the UI, but the `rental-desk-api` name was already taken on Render by another account, so the API got the address `rental-desk-api-tuwe`. The UI was then deployed to Netlify with that address built in. The UI deploy steps are:

```bash
cd frontend
VITE_API_BASE_URL=https://rental-desk-api-tuwe.onrender.com npm run build
printf '/*    /index.html   200\n' > dist/_redirects     # client-side routes serve the app
npx netlify-cli login                                    # once, in a browser
npx netlify-cli deploy --prod --dir=dist --site <netlify site id>
```

Then set the API's `CORS_ORIGINS` on Render to `https://rental-desk-dharshini.netlify.app,https://rental-desk-ui.onrender.com`. To redeploy the UI after a change, repeat the build and deploy commands. The API redeploys on Render automatically on every push to `main`.

**Manual steps done in dashboards:** creating the Blueprint on Render; deleting an older free Render database from another project (Render allows one free database per account); adding `CORS_ORIGINS` to the API by hand (the value typed during Blueprint creation was lost because the first API deploy was cancelled); authorising the Netlify CLI and creating the Netlify site.

### The Render Blueprint

The hosted setup is described by `render.yaml` (a Render Blueprint) and uses the same Dockerfile as Compose.

**What the files do**

| File | Role |
|---|---|
| `render.yaml` | Declares a free PostgreSQL database, the API as a Docker web service with `/health` as its health check, and the UI as a static site with an SPA rewrite rule. |
| `backend/Dockerfile` | Python 3.11 slim image running as a non-root user; entry point `scripts/start.sh`. |
| `backend/scripts/start.sh` | `alembic upgrade head`, then the seed (only loads data into an empty DB), then uvicorn on `$PORT`. |
| `backend/scripts/migrate_and_seed.sh` | Migrate, then seed. `--reset` wipes all data and reseeds. |
| `frontend/Dockerfile` + `nginx.conf` | Used by Compose; Render builds the static site with `npm ci && npm run build` instead. |
| `.github/workflows/ci.yml` | Runs on every push and pull request. |

**Steps (the manual ones are in a provider dashboard)**

1. Push the repository to GitHub.
2. *(Manual, Render dashboard)* New → Blueprint → choose the repository. Render reads `render.yaml` and proposes `rental-desk-db`, `rental-desk-api` and `rental-desk-ui`.
3. *(Manual)* Render asks for the two values marked `sync: false`:
   - `CORS_ORIGINS` on the API = the UI's URL, e.g. `https://rental-desk-ui.onrender.com`
   - `VITE_API_BASE_URL` on the UI = the API's URL, e.g. `https://rental-desk-api.onrender.com`

   Render names services `https://<name>.onrender.com` unless the name is taken, in which case it adds a suffix. If the real URLs differ, correct both variables under each service's Environment tab and redeploy both (the UI needs a rebuild because Vite bakes the URL into the bundle).
4. Apply. On first start the API container runs the migration and loads the seed data.
5. Check `https://<api>/health` returns `{"status":"ok","database":"ok"}` and the UI lists 20 items.

**Redeploying after a code change:** push to the deployed branch; Render auto-deploys both services. Migrations run on every container start, so a new Alembic revision is applied automatically.

**Re-seeding the hosted database.** Render's free plan has no shell, so run the seed from your machine against the database's *External Database URL* (Render dashboard → `rental-desk-db` → Connect):

```bash
cd backend
DATABASE_URL='<external database url>' python -m app.seed --reset
```

This deletes all data and reloads the sample set with timestamps relative to the moment you run it (ids restart at 1).

**Free-tier caveats:** the API sleeps when idle (cold start up to about a minute), and Render's free PostgreSQL databases expire 30 days after creation unless upgraded. Check Render's current free-tier terms before relying on these numbers. To move to another Postgres host (e.g. Neon), set `DATABASE_URL` on the API service to that URL; nothing else changes.

## 6. Running tests and coverage

```bash
cd backend
python -m pytest                                        # all 295 tests (SQLite)
python -m pytest --cov=app --cov-report=term-missing --cov-report=html   # with coverage (HTML in htmlcov/)
python -m coverage report > coverage.txt                # refresh the committed summary
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/test_db python -m pytest   # same suite on PostgreSQL
```

The PostgreSQL run drops and recreates the tables in the database you point it at, so use a throwaway database.

```bash
cd frontend
npm test            # Vitest: money parsing/formatting and IST clock helpers (17 tests)
npm run lint && npm run typecheck && npm run build
```

**Browser tests (Playwright, 12 scenarios).** They drive the real UI against a running API on freshly seeded data, and change that data as they go:

```bash
cd backend && python -m app.seed --reset && uvicorn app.main:app --port 8000   # terminal 1
cd frontend && npm run dev                                                     # terminal 2
cd frontend && npx playwright install chromium && npm run test:e2e             # terminal 3
```

`E2E_BASE_URL` points them at another UI (default `http://localhost:5173`). `PW_CHANNEL=msedge` uses an installed Edge instead of downloading Chromium: all scenarios pass, but Edge reports a "browser has been closed" error after the final (PDF download) test and the run exits with 1. With Playwright's Chromium the run is clean, and that is what CI uses. Reseed before every run.

**Coverage (backend, last run):** committed summary in [`backend/coverage.txt`](backend/coverage.txt).

| Scope | Statements | Coverage |
|---|---|---|
| Whole backend (`app/`) | 1751 | **99%** |
| Business-rules layer: `app/domain/` | 165 | **100%** |
| Business rules + use cases: `app/domain/` + `app/services/` | 717 | **99%** |

All 295 backend tests passed on SQLite and on PostgreSQL 16, and all 12 browser scenarios passed in Chromium, in the last local runs.

**What is covered:** every rule and boundary in the brief (47 h 59 m / 48 h 00 m / 48 h 01 m, fee at 0 s / 1 s / 1 day / 1 day + 1 s late, ₹200 cap at 20 vs 21 days, replacement-value cap, ₹100.00 vs ₹100.01, 14 vs 15 days overdue, 2 vs 3 active loans); every valid and invalid state transition (generated from the transition table); returns twice; suspension and reinstatement; payments up to and over the balance; rollback of a refused reservation; races (three simultaneous check-outs, four members reserving one item, six parallel reservations against the 3-loan limit, two parallel payments against one balance); malformed JSON, wrong types, out-of-range ids, unknown fields; the error envelope; the clock header; CORS; JSON log output; migration/model drift; the seed scenarios; waitlist joining, ordering, promotion on return / cancel / lapse / return-to-service, skipping ineligible members, and races on joining and returning; every outbox message type, no message for a refused action, and the once-a-day reminder window; the PDF statement. The browser tests cover the main desk flows, including waitlist promotion, the outbox, member edit/delete and the PDF download.

**What is not covered, on purpose:** the `python -m app.seed` command-line wrapper (the seeding logic itself is tested); the PostgreSQL-only branches in `database.py` and `seed.py`, which only run in the PostgreSQL job; one fallback in `api/errors.py` for a domain error subclass that doesn't exist. Four lines of the PDF renderer (the fee cell for a loan that is reserved but not yet out). React components have no unit tests; they are exercised through the browser tests instead.

## 7. API overview

Base path `/api/v1`. Interactive docs at `/docs`. All bodies are JSON; money is integer **paise**; timestamps are UTC ISO-8601.

| Method | Path | Purpose | Main errors |
|---|---|---|---|
| GET | `/health` (also `/api/v1/health`) | Liveness + database check | 503 |
| GET | `/clock` | The "now" the server is using (honours `X-Test-Clock`) | 400 |
| GET | `/members?q=&status=&limit=&offset=` | List/search members, with fee balance | 400 |
| POST | `/members` | Register a member | 400, 409 `PHONE_IN_USE`, 422 `JOIN_DATE_IN_FUTURE` |
| GET | `/members/{id}` | Member + balance + active loans + **why they can't borrow** + suspension history | 404 |
| PATCH | `/members/{id}` | Edit name / phone / join date | 400, 404, 409 |
| DELETE | `/members/{id}` | Delete a member with no history | 404, 409 `MEMBER_HAS_HISTORY` |
| POST | `/members/{id}/suspend` · `/reinstate` | Change status (reason required, kept in history) | 404, 409 `ALREADY_SUSPENDED` / `ALREADY_ACTIVE` |
| GET | `/members/{id}/statement` | Loans, fees, payments, balance, fees accruing | 404 |
| POST | `/members/{id}/payments` | Record a payment | 400, 404, 422 `PAYMENT_EXCEEDS_BALANCE` |
| GET | `/items?q=&status=&category=&limit=&offset=` | List/search; `status` filters on the live status (incl. `overdue`) | 400 |
| GET | `/items/categories` | Distinct categories | — |
| POST | `/items` | Add an item | 400 |
| GET | `/items/{id}` | Item + live status + current loan + `allowed_actions` | 404 |
| PATCH | `/items/{id}` | Edit name / category / replacement value / note (not status) | 400, 404 |
| DELETE | `/items/{id}` | Delete an item that was never loaned | 404, 409 `ITEM_HAS_HISTORY` |
| POST | `/items/{id}/send-to-maintenance` | Available/Reserved → Maintenance (cancels a reservation) | 404, 409 `INVALID_TRANSITION` |
| POST | `/items/{id}/return-to-service` | Maintenance → Available | 404, 409 |
| GET | `/loans?member_id=&item_id=&limit=&offset=` | Loan history, newest first | 400 |
| GET | `/loans/overdue?limit=&offset=` | Overdue loans, most overdue first, with days late and fee so far | 400 |
| POST | `/loans` | **Reserve**: `{member_id, item_id}` → 48 h hold | 404, 409 `INVALID_TRANSITION`, 422 (borrowing blocks) |
| GET | `/loans/{id}` | One loan | 404 |
| POST | `/loans/{id}/checkout` | Reserved → Checked out, due in 7 days | 409 `RESERVATION_EXPIRED` / `INVALID_TRANSITION`, 422 |
| POST | `/loans/{id}/return` | Checked out/Overdue → returned; charges fee. Optional `{send_to_maintenance, condition_note}` | 409 `INVALID_TRANSITION` |
| POST | `/loans/{id}/cancel` | Cancel a reservation | 409 |
| GET | `/members/{id}/statement.pdf` | The statement as an A4 PDF download | 404 |
| GET | `/waitlist?item_id=&member_id=&status=&limit=&offset=` | Queue entries in join order (`status=waiting` for the live queue) | 400 |
| POST | `/waitlist` | Join an item's queue: `{member_id, item_id}` | 404, 409 `INVALID_TRANSITION` / `ALREADY_ON_WAITLIST` / `ALREADY_HOLDS_ITEM`, 422 (borrowing blocks) |
| POST | `/waitlist/{id}/cancel` | Leave the queue | 404, 409 |
| GET | `/notifications?member_id=&kind=&limit=&offset=` | The SMS outbox, newest first | 400 |
| POST | `/notifications/overdue-reminders` | Queue a reminder for each overdue loan (once per loan per 24 h) | 400 |

Lists return `{items, total, limit, offset}`; `limit` is 1–100.

## 8. Business rules and assumptions

### Rules → code → tests

| # | Rule | Enforced in | Tested in |
|---|---|---|---|
| 1 | Item state machine; invalid transitions rejected | `domain/item_state.py`: `ALLOWED_ACTIONS`, `ensure_action_allowed`, `ensure_loan_action_allowed`, `effective_item_status`; called from `services/loans.py` and `services/items.py` | `tests/unit/test_item_state.py` (every status × action pair), `tests/integration/test_items.py::TestMaintenance`, `tests/api/test_members_items_api.py::TestItems` |
| 1 | Overdue is computed, not a cron | `domain/timing.py::is_overdue`, `effective_item_status`, SQL twin `persistence/queries.py::effective_item_status_expression` | `test_item_state.py::TestEffectiveItemStatus`, `test_loan_flow.py::test_overdue_is_derived_from_the_clock`, `test_items.py::TestListing::test_filters_by_live_status` |
| 2 | 48 h reservation, enforced at read **and** write time | read: `effective_item_status` / `effective_loan_status`; write: `services/holds.py::settle_lapsed_reservation` (reserve, waitlist, maintenance) and `ensure_loan_action_allowed` → `RESERVATION_EXPIRED` (check out, cancel) | `test_timing.py::TestReservationExpiry`, `tests/integration/test_reservations.py::TestExpiry`, `tests/api/test_loans_api.py::test_checkout_at_47h59m_and_48h01m` |
| 3 | 7-day loan; ₹10/day rounded up; cap ₹200; cap replacement value | `domain/timing.py::due_at_for`, `days_overdue`; `domain/fees.py::late_fee_paise` | `tests/unit/test_fees.py`, `test_timing.py::TestDueDateAndOverdue`, `test_loan_flow.py::TestReturn`, `test_loans_api.py::test_fee_capped_at_replacement_value` |
| 4 | Max 3 active loans (reserved, checked out, overdue) | `domain/eligibility.py::borrowing_blocks` + `queries.count_active_loans`; enforced in `services/loans.py::reserve_item` | `test_eligibility.py::TestActiveLoanLimit`, `test_reservations.py::TestActiveLoanLimit`, `test_concurrency_and_transactions.py::test_parallel_reservations_cannot_exceed_the_loan_limit` |
| 5 | Balance > ₹100 or a loan > 14 days overdue blocks reserve and check-out | `domain/eligibility.py`; `services/borrowing.py::ensure_member_can_borrow` (reserve and check out) | `test_eligibility.py::TestFeeBalance`/`TestOverdueBlock`, `test_members_and_payments.py::TestBalanceThreshold`, `test_reservations.py::TestOverdueBlock`, `test_loans_api.py::test_member_exactly_at_100_rupees_can_still_reserve` |
| 6 | Return records the fee on the loan and the member's balance; return of a non-checked-out item is an error | `services/loans.py::return_item`; balance = `queries.member_balance_paise` | `test_loan_flow.py::TestReturn` (incl. `test_returning_twice_is_an_error`), `test_loans_api.py::test_returning_twice` |
| 7 | Suspended members can't transact; reversible; history kept | `services/members.py::suspend_member` / `reinstate_member` → `member_status_changes`; `MEMBER_SUSPENDED` block | `test_members_and_payments.py::TestSuspension`, `test_members_items_api.py::test_suspend_and_reinstate_keep_history` |
| — | Payments clear fees; no overpayment | `services/payments.py::record_payment` | `TestPayments`, `test_parallel_payments_cannot_overpay`, `test_loans_api.py::test_paying_more_than_the_balance` |
| S1 | Waitlist: queue for an unavailable item; when it frees up the first eligible member is reserved it automatically | `domain/waitlist.py::ensure_can_join_waitlist`; `services/waitlist.py::promote_next_in_line` (called from return, cancel, return-to-service) and `hand_lapsed_hold_to_queue` (before reserve/join) | `tests/unit/test_waitlist_rules.py`, `tests/integration/test_waitlist_and_outbox.py::TestJoining`/`TestPromotion`, `tests/api/test_waitlist_outbox_pdf_api.py`, `frontend/e2e/desk.spec.ts` |
| S2 | Email/SMS stubs with a visible outbox | `services/notifications.py::notify` (called inside each action's transaction), `send_overdue_reminders` | `test_waitlist_and_outbox.py::TestOutbox`, `test_waitlist_outbox_pdf_api.py` |
| S3 | Member statement as PDF | `reports/statement_pdf.py::render_statement_pdf`, `GET /members/{id}/statement.pdf` | `test_waitlist_outbox_pdf_api.py::test_statement_pdf*`, `frontend/e2e/desk.spec.ts` |
| — | No double booking under concurrency | Row locks in services (lock order member → item → loan) + SQLite `BEGIN IMMEDIATE` (`persistence/database.py`) + partial unique index `uq_loans_one_open_loan_per_item` | `test_concurrency_and_transactions.py`, `test_loans_api.py::test_two_checkouts_within_seconds` |

### Assumptions

1. **Check-out needs a reservation.** The brief's state machine is Available → Reserved → Checked Out, so `checkout` acts on a reserved loan. A walk-in borrower is reserved and checked out straight away (two clicks on the item page).
2. **The hold lasts strictly less than 48 hours.** Check-out at 47:59:59 works; at exactly 48:00:00 the reservation has expired.
3. **Overdue means strictly after `due_at`.** Returning at exactly `due_at` (7 × 24 h after check-out) is on time.
4. **"Calendar days, rounded up"** = every started 24-hour period after `due_at` counts as a day, weekends included. One minute late is ₹10; 1 day and 1 second late is ₹20. I chose 24-hour periods over counting IST midnights so that a loan returned 10 minutes late just after midnight isn't charged for two days.
5. The fee caps use the item's replacement value **at the time of return**. Editing the value of an item that is out affects that loan's fee.
6. **Fees are charged on return only** (rule 6). Until then the fee building up on an overdue item is shown as "accruing" and doesn't count towards the ₹100 limit; the 14-day overdue rule is what stops a member with a long-overdue item from borrowing.
7. **₹100 exactly is allowed**; ₹100.01 blocks ("over ₹100").
8. **"Overdue by more than 14 days"** uses the same day count as fees, so it blocks from the 15th started day, i.e. once `now > due_at + 14 days`.
9. **The 3-loan limit is checked when reserving**, not again at check-out (the reservation already counts as one of the three). Suspension, balance and overdue rules are checked at both.
10. **Suspended members can't reserve or check out**, but can return items, pay fees and have reservations cancelled. Blocking returns would only keep tools away from the library. Suspending doesn't cancel existing reservations; they can't be collected and lapse after 48 hours.
11. **Overpayment is refused** (`PAYMENT_EXCEEDS_BALANCE`) instead of creating credit, because the desk has no refund process. Any payment when nothing is owed is refused for the same reason.
12. **Maintenance from Checked Out / Overdue** goes through a return (`send_to_maintenance: true`), so the late fee is still worked out and the loan is closed properly. A direct `send-to-maintenance` on a checked-out item is rejected with a message saying so. From Reserved, the reservation is cancelled.
13. A lapsed reservation is stored as `expired` the next time a write touches that item; until then the stored row still says `reserved`, but every read derives `expired`/`available` from the clock. Lapsed reservations never count as active loans.
14. **Staff are the only users** and there is no authentication (the brief makes it optional).
15. Members and items with any history can't be deleted (409). Suspend the member or send the item to maintenance instead, which keeps the records.
16. **Clock override is per request.** An action dated before the previous event on the same loan (e.g. returning "before" the check-out) is refused with `CLOCK_BEFORE_PREVIOUS_EVENT`.
17. Join date defaults to today in IST and can't be in the future. Phone numbers are stored without spaces or dashes, must be 10–15 digits with an optional `+`, and are unique.
18. A single amount (payment, replacement value) is capped at ₹1 crore to rule out integer overflow.
19. **Who can join a waitlist:** only for an item that is *not* available (otherwise reserve it). A member can't queue twice for one item, or for an item they already hold. Suspended members, members owing over ₹100 and members with a loan over 14 days late can't join. The 3-loan limit is *not* checked when joining, because they may have returned something by the time their turn comes.
20. **When the queue gets its turn:** whenever the item becomes Available again: a return (unless it goes to maintenance), a cancelled reservation, return to service, or a lapsed hold. A lapsed hold is handed on at the next write that touches the item (reserving it or joining its queue), in its own transaction, so the queue's turn is kept even if that request is then refused.
21. **Promotion order and skipping:** members are tried in the order they joined, each checked against every borrowing rule *at that moment*, including the 3-loan limit. Anyone who can't borrow is marked `skipped`, with the reasons stored and texted to them, and the next member is tried. The promoted member gets a normal 48-hour hold starting then. If the person first in line asks to reserve the item themselves, they get that hold instead of an error.
22. **Notifications are SMS stubs:** members only have a phone number, so every message is `channel = sms` to that number, and "sending" just records it. Messages are written in the same transaction as the action, so a refused or failed action leaves no message. Message text isn't logged, because it contains names and dues.
23. **Overdue reminders are sent by the desk,** not by a scheduler (in keeping with "no cron" in the brief): the Outbox button queues one per overdue loan, skipping loans reminded in the last 24 hours.
24. **PDF amounts are written "Rs."** because the PDF's built-in fonts have no ₹ glyph; the figures are the same as in the JSON statement.

## 9. Error handling and logging

### Error response shape

Every non-2xx response has the same body:

```json
{
  "error": {
    "type": "rule_violation",
    "code": "FEE_BALANCE_OVER_LIMIT",
    "message": "Unpaid fees of ₹120 exceed the ₹100 limit.",
    "details": { "member_id": 4, "blocks": [{ "code": "FEE_BALANCE_OVER_LIMIT", "message": "…" }] },
    "request_id": "8494e9f7e452454e8579d336a2c595d8"
  }
}
```

| Kind | Raised as | `type` | HTTP | Logged at |
|---|---|---|---|---|
| Malformed JSON, missing/extra fields, wrong types, out-of-range values | Pydantic → `RequestValidationError` | `validation` | 400 (`details.fields` lists each field) | INFO |
| Bad `X-Test-Clock` header | `BadRequestError` | `bad_request` | 400 | INFO |
| Unknown id | `NotFoundError` | `not_found` | 404 | INFO |
| Action not valid in the current state | `InvalidTransitionError` | `invalid_transition` | 409 | WARNING |
| Clash with existing data (phone, delete with history, race caught by a DB constraint) | `ConflictError` / `IntegrityError` | `conflict` | 409 | WARNING |
| Policy rule forbids it (limits, balance, suspension, overpayment) | `BusinessRuleViolation` | `rule_violation` | 422 | WARNING |
| Database unreachable or locked | `OperationalError` | `unavailable` | 503 | ERROR + trace |
| Anything else | any exception | `internal` | 500 (generic message, no trace) | ERROR + trace |

Domain errors live in `app/domain/errors.py` and know nothing about HTTP; `app/api/errors.py` maps them. Each service call is one transaction, so a refused or failed request writes nothing (see `test_failed_reservation_leaves_no_partial_writes`). The UI shows `message` and lists every borrowing block, with the request id as a reference.

### Logging

- One JSON object per line on stdout (`app/logging_config.py`): `ts` (UTC), `level`, `logger`, `event`, `request_id`, plus context fields.
- **Request id**: taken from an incoming `X-Request-ID` header if it is a safe token, otherwise generated. It is returned in the `X-Request-ID` response header and in every error body, and attached to every log line written during the request.
- **Per request** (INFO): `request.completed` with method, path, status, duration and whether the test clock was used. `/health` is logged at DEBUG to keep platform health checks out of the log. Request bodies are not logged.
- **Rule violations and invalid transitions** (WARNING): `request.rejected` with the error code, reason and the ids involved (`member_id`, `item_id`, `loan_id`).
- **State changes** (INFO): `loan.reserved`, `loan.checked_out`, `loan.returned` (with `fee_charged_paise`), `loan.cancelled`, `reservation.expired`, `payment.recorded`, `member.status_changed`, `item.sent_to_maintenance`, `waitlist.joined` / `waitlist.fulfilled` / `waitlist.skipped`, `notification.queued` (kind and ids only), and so on, each with its ids.
- **Unexpected errors** (ERROR) include the stack trace in the log only.
- No phone numbers, names or request bodies are logged.
- **Hosted logs:** Render dashboard → `rental-desk-api` → Logs. Search for a `request_id` to see every line from one request. Locally: the uvicorn terminal or `docker compose logs -f backend`.

## 10. Reviewer aids

### Setting the clock

- **In the UI:** the clock button in the header (it turns amber while active). Pick a date/time in IST, or use **+1 h / +1 day / +7 days**, and **Back to real time** to reset. The setting is kept in this browser's localStorage and sent with every request.
- **On the API:** send `X-Test-Clock` with an ISO-8601 timestamp that includes an offset. The response header `X-Effective-Clock` echoes the time used; `GET /api/v1/clock` shows it too. A missing header means real time; a malformed one is a 400. Set `ALLOW_TEST_CLOCK=false` to turn the override off.

```bash
API=http://localhost:8000/api/v1
curl -s $API/clock -H "X-Test-Clock: 2026-11-01T10:00:00+05:30"
curl -s -X POST $API/loans -H "Content-Type: application/json" \
     -H "X-Test-Clock: 2026-11-01T10:00:00+05:30" -d '{"member_id": 10, "item_id": 4}'
curl -s -X POST $API/loans/<id>/checkout -H "X-Test-Clock: 2026-11-03T09:59:00+05:30"   # 47h59m: 200
```

### Sample data (from `python -m app.seed`)

Timestamps are relative to when the seed runs, so the situations below hold right after seeding (re-seed with `--reset` to restore them). Ids are as created on an empty database.

| Member (id) | Situation | Try |
|---|---|---|
| Aarav Menon (1) | Reservation on *HD projector* made 47 h before seeding; a lapsed one on *Pressure washer* (reads as Available) | Check out the projector with the clock 59 min vs 61 min after seeding |
| Diya Raghavan (2) | *18V cordless drill* out (due about 5 days after seeding); *Folding tables* reserved | Return the drill with the clock +8 days → 3 days late, ₹30 |
| Kabir Sethi (3) | *Hammer drill* about 3 days overdue; Farhan and then Neha are queued for it | Return it: it is reserved for Farhan automatically, Neha moves to number 1, and the Outbox shows the "Waitlist: reserved" message |
| Meera Iyer (4) | Owes ₹120 → blocked | Member page explanation; pay ₹120.01 (refused) then ₹120 |
| Rohan Kulkarni (5) | *Petrol garden tiller* about 18 days overdue → blocked | Return it now (₹180), or with the clock +3 days (21 days late, capped at ₹200) |
| Ananya Bose (6) | Suspended, with history | Reinstate |
| Farhan Qureshi (7) | Owes **exactly ₹100** → still allowed | Reserve something |
| Lakshmi Pillai (8) | 3 active loans → blocked by the limit | Try a 4th reservation |
| Vikram Joshi (9) | Paid-off history: one fee capped at ₹200, one at the ₹150 *Stud finder*'s replacement value; queued for Rohan's tiller | Statement PDF |
| Neha Deshpande (10) | Clean record | Use her for fresh experiments |

Also: *Push lawn mower* is under maintenance; *Stud finder* has a ₹150 replacement value for testing the replacement-value cap. The Outbox already holds the messages the seeded history produced; "Send overdue reminders" queues two (Rohan, Kabir), and pressing it again queues none.

### Edge cases from the brief, and where to see them

| Edge case | Expected |
|---|---|
| Two check-outs of the same item within seconds | One 200, one 409 `INVALID_TRANSITION` |
| Returning twice | Second is 409 |
| Reserving/collecting at 47h59m vs 48h01m | 200 vs 409 `RESERVATION_EXPIRED` |
| Fee above replacement value | Capped at the replacement value (Stud finder) |
| Member exactly at ₹100 | Can borrow (Farhan) |
| Paying more than the balance | 422 `PAYMENT_EXCEEDS_BALANCE`; the UI disables the button and explains |

## 11. Known limitations

- **The UI deploy is manual.** The Netlify UI is built and uploaded from a local machine (commands in 5a), so it does not redeploy on push the way the Render API does.
- **`rental-desk-ui.onrender.com` is not the UI to use.** The Blueprint also created that Render static site, but it was built pointing at `rental-desk-api.onrender.com`, which belongs to another account. Use the Netlify URL.
- **No authentication.** Anyone who can reach the API can act as desk staff.
- **The test clock is on in the hosted configuration** so reviewers can use it. Anyone can send the header there; a real deployment would set `ALLOW_TEST_CLOCK=false`.
- **The clock is per request**, so a reviewer can build histories that are out of order *across* loans (e.g. a payment dated before the fee it pays was charged). Only ordering within one loan is checked.
- Rules evaluated at a past clock see all stored history, including rows dated "later". The seed avoids this by creating events in time order.
- **On SQLite every transaction takes the write lock** (`BEGIN IMMEDIATE`), reads included. That is what makes the race tests pass on SQLite, but it serialises all requests. PostgreSQL uses row locks instead and is what Compose and Render run.
- `GET /members/{id}/statement` returns all of a member's loans and payments without pagination; fine for a neighbourhood library, not for years of heavy use.
- The browser tests need freshly seeded data and change it as they run, so they can't run against a shared or hosted instance without reseeding first. The CI job that runs them is written but hasn't run on GitHub yet.
- Waitlist promotion takes the waiting member's row lock *after* the item's lock, the reverse of the usual order. On PostgreSQL that can, rarely, deadlock with the same member reserving that item at the same moment; PostgreSQL aborts one transaction, which the client sees as a 503 and can retry.
- A lapsed hold is passed to the waitlist only when a write touches the item (there is no background job), so a queued member's hold starts from that write, not from the moment the old hold lapsed.
- Notifications are stubs: nothing is actually sent, and there is no delivery status or retry.
- No rate limiting.
- Statement PDFs use "Rs." instead of ₹ (no glyph in the built-in fonts) and are English only.

## 12. AI and third-party usage

- **AI assistant:** Claude Code (Anthropic, model Claude Opus 5.5) in VS Code, used throughout the project. It assisted in coding, testing, Docker/CI/Render configuration and the first drafts of these documents, and ran the tests, linters and builds to check them.
- **My part:** I wrote the specification it worked from, decided the scope (the UI redesign, all three Stretch items), ran the app and reported problems, made every Git commit, and did the deployment steps on Render and Netlify. The details are in the prompt log.
- **Prompt log:** [`PROMPTS.md`](PROMPTS.md): every prompt, in order, with what I did with each answer.
- **Third-party code:** only the libraries listed in `backend/requirements*.txt` and `frontend/package.json` (including reportlab for PDFs and Playwright for browser tests). No templates, scaffolding generators or copied project code.
