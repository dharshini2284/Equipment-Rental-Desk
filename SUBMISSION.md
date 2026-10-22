# SUBMISSION: Problem 1, Equipment Rental Desk

## A. What I built

Rental Desk is a small web app for the volunteer desk of a tool library: staff find an item, reserve it for a member, hand it over, take it back and collect any late fee. All seven rules from the brief are enforced in the FastAPI backend: the state machine, 48-hour holds, 7-day loans with capped fees, the 3-loan limit, the ₹100 and 14-day blocks, fee-on-return and reversible suspension. Complete: every Core API operation (members, items, reserve, check out, return, cancel, payments, overdue list, statement) and every Core screen (item search and status filter, item actions valid for the current state, member page with a "why can't they borrow" explanation, overdue dashboard, reviewer clock), plus the three Stretch items (waitlist, SMS-stub outbox, PDF statement). It is live on Netlify and Render, with 295 backend tests passing on SQLite and PostgreSQL, 100% coverage on the rules, and 12 browser tests. Partial: the Netlify UI is deployed by hand rather than on every push, and the reviewer clock can still build out-of-order history across different loans.

## B. Three design decisions

**1. The balance is calculated, not stored.** *Decision:* a member's balance is always fees charged minus payments, worked out in SQL, with no balance column. *Alternative:* keep a running balance and update it on every return and payment. *Why:* it can never drift, and the statement always adds up. *Cost:* each eligibility check runs two sum queries, and I still needed a row lock on the member so two payments arriving together can't overpay.

**2. "Overdue" and "expired" come from the clock.** *Decision:* both are worked out from `now` on every read, with a matching SQL `CASE` so the list filters work; a lapsed hold is written as `expired` only when the next write touches that item. *Alternative:* a background job that updates statuses. *Why:* the brief rules out a cron, and the reviewer clock then just works. *Cost:* the rule exists in both Python and SQL, so a test checks they agree.

**3. Lock first, with the database as a backstop.** *Decision:* each action is one transaction that locks member, then item, then loan (`FOR UPDATE` on PostgreSQL, `BEGIN IMMEDIATE` on SQLite), and a partial unique index allows only one open loan per item. *Alternative:* version columns and retries. *Why:* desk traffic is low and a clear 409 is easier to understand than a retry loop. *Cost:* on SQLite every request waits its turn, reads included.

## C. The hardest part

Time. Once "now" became something a request could set, every rule had to make sense at any instant, not just today. I noticed it in the seed script, which builds history by calling the real services at past times: one member was refused a loan "50 days ago" because a late fee from "28 days ago" already counted against him. The balance query adds up every stored row, not just the ones before `now`. I reordered the seed so events happen in time order (`4df67c7`) and added a guard that refuses to collect or return a loan at a time before its previous step, `CLOCK_BEFORE_PREVIOUS_EVENT` (`5048bd0`). Making every query time-aware felt like too big a change this late, so the remaining cross-loan case is listed as a known limitation instead.

## D. How I handle failure

| Failure | Where it starts | What the user sees | What is logged |
|---|---|---|---|
| Bad request | Pydantic schemas (strict ints, no unknown fields, length and range limits) | 400 `VALIDATION_ERROR`, with each bad field listed | INFO `request.invalid` with the field names |
| Rule violation | `domain/` raises `BusinessRuleViolation` or `InvalidTransitionError`; the transaction rolls back | 422 or 409 with a specific code; the UI lists every reason | WARNING `request.rejected` with the code and member/item/loan ids |
| Database error | `IntegrityError` (a race caught by a constraint) or `OperationalError` | 409 `CONCURRENT_UPDATE`, or 503 | WARNING, or ERROR with the trace |
| Unexpected exception | anywhere | 500 with a plain message and the request id, never the trace | ERROR `request.unhandled_exception` with the trace |

A response and its log lines share one request id.

## E. Milestone log

| Milestone | Date completed | Commit |
|---|---|---|
| M0: Scaffold | 20 Oct 2026 | `de8827b` |
| M1: Domain model | 20 Oct 2026 | `4df67c7` |
| M2: Business rules | 20 Oct 2026 | `5048bd0` |
| M3: API | 20 Oct 2026 | `2bb8cbb` |
| M4: UI | 20 Oct 2026 | `0313261` |
| M5: Deployment | 21 Oct 2026 (live) | `c592287` |
| M6: Documentation | 22 Oct 2026 | `5850467` (tag `v1.0`) |

## F. If I had two more days

I've ordered these by what would hurt most during the review if left as is.

1. **Deploy the UI on every push** by connecting Netlify to GitHub. A live site that silently falls behind the code is the worst thing a reviewer could hit, and it takes an hour.
2. **Make balance and loan-count queries respect `now`.** It is the one correctness gap left (section C), and reviewers will move the clock.
3. **A simple staff login.** Right now anyone with the link can change data and move the clock; that matters once the site is shared, but it doesn't affect the rules.
4. **Lock the waiting member before the item during waitlist promotion.** It removes a rare PostgreSQL deadlock that is unlikely at desk traffic, so it comes after the visible issues.
5. **A real SMS gateway behind the outbox.** Messages are already stored correctly, so this adds polish rather than fixing anything wrong.

## G. Self-assessment

| Criterion | Score (1–5) | Justification |
|---|---|---|
| Business logic correctness | 4 | Every Core rule is in the backend with boundary and race tests on two databases; marked down because the clock override can still create out-of-order history across loans. |
| Code clarity and structure | 4 | Clear domain / services / persistence / API layers and linters on both apps; a few service modules are long and the view-to-schema mapping repeats itself. |
| Error and exception handling | 5 | Separate error types, one response shape, no traces sent to clients, a transaction around every write, readable messages in the UI. |
| Logging and observability | 4 | JSON logs with request ids and the ids involved, a health check, logs visible on Render; no metrics. |
| Data modelling and persistence | 4 | CHECK constraints and partial unique indexes, migrations tested against the models, balance and status choices written down. |
| API design | 4 | Predictable paths, correct status codes, pagination and OpenAPI; actions are POST sub-resources rather than strict REST. |
| UI usability | 4 | Only valid actions shown, blocked members explained, works on a phone; not yet tried by actual desk volunteers. |
| Testing | 5 | 295 backend tests with a boundary test for every number in the brief, races and rollback, plus 12 browser tests; no component-level UI tests. |
| Deployment and operability | 4 | Live on Render and Netlify, Dockerfiles, Compose, Blueprint, migrate-and-seed and CI all in the repo; the UI deploy is still a manual step. |
