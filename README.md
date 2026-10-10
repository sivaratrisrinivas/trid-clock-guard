# TRID Clock Guard

A guard for a Penny-style mortgage intake agent (built with Copperlane's stack: Python/FastAPI, Postgres). It watches the borrower chat, stamps the moment the 6th Reg Z application item lands, computes the Loan Estimate due date on the lender's own calendar, and blocks fee-taking tools until the borrower has the LE and has said to proceed.

**Live demo:** https://trid-clock-guard.onrender.com (free tier, first load can take ~30 s) · **Walkthrough video:** [trid-clock-guard.onrender.com/static/walkthrough.mp4](https://trid-clock-guard.onrender.com/static/walkthrough.mp4) ([repo copy](static/walkthrough.mp4))

## Problem
An agent that collects intake info piecemeal can create a Reg Z "application" mid-chat without anyone noticing. That starts a 3-business-day Loan Estimate clock and locks most fees. If the agent can also take fees, it needs to know which of its own steps start clocks and which tools are off limits.

## Evidence (12 CFR 1026, read from the CFPB's eRegs text and official commentary)
| Rule | What the guard does |
|---|---|
| [1026.2(a)(3)(ii)](https://www.consumerfinance.gov/rules-policy/regulations/1026/2/#a-3-ii) + comment 2(a)(3)-1, -2: name, income, SSN (or the ID used for credit, e.g. ITIN), property address, estimated value, loan amount. Six items = application, even if more is required. A written record of an oral application counts. | Tracks the six items with the source message, time and quote for each. Stamps `application_received_at` once, when the 6th lands. Later amendments do not move it. |
| [1026.19(e)(1)(iii)(A)](https://www.consumerfinance.gov/rules-policy/regulations/1026/19/#e-1-iii) + comment 19(e)(1)(iii)-1: deliver or mail the LE by the 3rd business day after receipt, using the **general** business-day definition in [1026.2(a)(6)](https://www.consumerfinance.gov/rules-policy/regulations/1026/2/#a-6) (days the creditor's offices are open for substantially all business functions). | LE due date counts each lender's open days (tenant config: Saturday open or closed, closed on federal holidays and observed days). |
| 1026.2(a)(6) **specific** definition (all days except Sundays and 5 U.S.C. 6103(a) holidays, incl. Juneteenth) + comment 2(a)(6)-2 (an observed Friday holiday is still a business day). | Used for the mailbox rule and the 7-day waiting period, never for the LE due date. |
| [1026.19(e)(1)(iv)](https://www.consumerfinance.gov/rules-policy/regulations/1026/19/#e-1-iv) + comments -1, -2: mailed or emailed LE is considered received 3 specific business days later, unless there is evidence of earlier receipt. | Computes deemed receipt; logs a borrower's "got the LE" message as earlier receipt evidence. |
| 1026.19(e)(1)(iii)(B) + comment 19(e)(1)(iii)-2: LE at least 7 specific business days before consummation. | Shows the earliest consummation date. |
| [1026.19(e)(2)(i)(A)](https://www.consumerfinance.gov/rules-policy/regulations/1026/19/#e-2-i) + comments -1, -2, -5; (e)(2)(i)(B): no fee before the LE is received and intent to proceed is shown, except a credit report fee. Silence is not intent. Taking a card or check counts as imposing a fee. | Every `charge_fee` / `collect_payment_method` call goes through a gate that allows or blocks it and writes the reason and citation to an audit table. |
| Comment 19(e)(1)(iii)-3: withdrawn within the 3 days means no LE is needed. | Withdrawal stops the clock and keeps fees blocked. |

Judgment calls, flagged: Reg Z sets no time-of-day cutoff, so the receipt day is read in the lender's local time zone. When a holiday falls on Sunday and is observed Monday, the specific rule here counts the Monday (only the actual 6103(a) date is excluded); the commentary only spells out the Saturday case. Worth confirming with compliance counsel.

## Built vs simulated
- **Built:** business-day calendars and deadline math (10 unit tests in `tests/`, incl. the commentary's own examples, Columbus Day, the July 3 2026 observed holiday, Juneteenth 2027, Thanksgiving, Christmas, Saturday open vs closed, after-hours and Sunday receipt, mailbox rule, 7-day wait), rules-based item extraction with provenance, the trigger state machine, the tool gate and audit log, FastAPI + SQLAlchemy schema (`loan_file`, `intake_event`, `app_item`, `clock`, `tool_call_audit`), tested on Postgres 17.
- **Simulated:** three borrower chats and Penny's turns are scripted and synthetic, the two lenders are fictional, the fee tools and LE delivery are stubs (no LOS, no payments, no LE generation), and there is a simulated clock. The live demo runs on the embedded SQLite fallback because the free Render Postgres slot is in use. Optional LLM normalization (`USE_LLM=1`, free-tier Groq or Gemini key) is off by default and not used in the demo. Nothing here describes how Copperlane works internally.

## Run it (under 5 minutes)
```bash
git clone https://github.com/sivaratrisrinivas/trid-clock-guard && cd trid-clock-guard
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
pytest -q && uvicorn app.main:app --port 8000   # open http://localhost:8000
```
Postgres: set `DATABASE_URL=postgresql://user@host:5432/db` before starting. Without it, SQLite is used.

## Next steps
Consume a real intake event stream (chat, voice transcripts, doc extractions) instead of scripted turns; emit `application_received` to the LOS; per-lender calendars with a compliance-officer override; extend to revised LE and Closing Disclosure timing (1026.19(e)(4), 1026.19(f)).

Prototype by Srinivas Sivaratri. Not legal advice.
