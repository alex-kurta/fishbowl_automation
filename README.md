# Fishbowl order automation

Turns customer order emails into sales orders in Fishbowl Inventory 2020
(20.11.1.20201113) so the sales team can focus on outreach.

## Pipeline

```
orders IMAP inbox -> extract -> CSV -> quote/comment gates -> duplicate guard
                     -> ImportSalesOrder -> review email -> Processed
```

## Docs

| File | Read it for |
| --- | --- |
| `AGENTS.md` | The behavioural contract: what gets imported, what gets skipped, what counts as a duplicate vs a failure, and every Fishbowl behaviour verified against production. Start here. |
| `MIGRATION.md` | Moving to the Ubuntu VM: cron shape, scp transfer, `.env` changes, cutover order, known gaps. |
| `OPERATIONS.md` | Day-to-day runbook: health checks, log meanings, failure triage, how to void and re-drive an order. |
| `ARCHITECTURE.md` | Code map, control flow, invariants, where to change what, test coverage. |

## Running it

```
.venv/bin/python scripts/auto_order_entry.py            # one pass, then exit
.venv/bin/python scripts/auto_order_entry.py --dry-run   # parse + gates + dedupe, write nothing
.venv/bin/python scripts/auto_order_entry.py --interval 5 --quiet   # resident poller
```

Every pass reads **unread** mail whose subject matches the order pattern, imports what
is new, emails a review request back to the same inbox, and moves handled mail to
`Processed`. Log: `data/logs/auto_order_entry.log` (2 MB × 5 rotations).

Nothing is imported when:

- the email carries a PDF attachment (body has no order data) — left unread for
  manual entry
- the reference starts with `Q-` / `Quote-` — quotes are handled by hand
- the order's comments name a PO that already exists in Fishbowl (a finalized quote) —
  left for manual handling
- the customer PO already has a sales order — logged as a duplicate, mail moved to
  `Processed`

Real failures (unparseable, no line items, import error) leave the email in the inbox,
mark it read, and send a "Fishbowl entry failed" notice to the same inbox.

## Cadence

One long-lived process, not a process per tick:

```
scripts/run_order_entry.sh          # Linux: --interval 5 --quiet
scripts\run_auto_order_entry.cmd    # Windows equivalent
```

It logs into Fishbowl and IMAP **once** and holds both sessions across polls, only
reconnecting when something breaks (backoff capped at 5 minutes). Measured warm poll
on the production mailbox is ~73 ms, so a 5s tick is ~1.5% duty cycle. Anything below
about 2s is just hammering the mail server; see `MIGRATION.md` §0 for the numbers.

`--quiet` suppresses console chatter and idle "found 0" lines; imports, skips, failures
and tracebacks still reach the log. An idle mailbox adds zero bytes. Do not disable
logging entirely — that file is the only record of what was imported, skipped, or
failed.

**Cron cannot tick at 5s** (1-minute floor). On Linux the tick comes from `@reboot`
starting the resident process plus a per-minute watchdog that resurrects it if it dies;
both entries are in `MIGRATION.md` §7. On Windows, use a Task Scheduler task with
trigger "At startup", or `shell:startup`.

## Caveat: the trigger is `UNSEEN`

A poll only sees mail that is both unread and subject-matched. If someone opens an
order email before a tick, that order is never processed and never logged. A 5s tick
shrinks the window but does not close it; closing it needs a UID high-water mark
instead of the `UNSEEN` flag. Listed as gap #1 in `MIGRATION.md` §9.

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env     # then fill in credentials; chmod 600
```

Verify before the first live sweep:

```
.venv/bin/python -m unittest discover -s tests        # expect 77 OK
.venv/bin/python scripts/diagnose_db.py               # MySQL reachable
.venv/bin/python scripts/probe_fishbowl_api.py        # API login works
.venv/bin/python scripts/auto_order_entry.py --dry-run
```

On Windows the paths are `.venv\Scripts\python` and `copy` instead of `cp`.

## Layout

- `pipeline/stages/` — extract, normalize, guards, product_alerts, import_to_fishbowl, inbox, notify, verify
- `pipeline/fishbowl_api.py` — Fishbowl TCP API client (login, import, void)
- `pipeline/config.py` — reads credentials from `.env` (never commit it)
- `scripts/auto_order_entry.py` — production entry point (the scheduler runs this)
- `scripts/run_order_entry.sh` / `run_auto_order_entry.cmd` — scheduler wrappers
- `scripts/import_sales_order.py` — one saved `.msg`, `--execute` to import
- `scripts/duplication_test.py` — exercises the duplicate guard
- `scripts/probe_fishbowl_api.py`, `scripts/diagnose_db.py` — connectivity checks
- `data/output/` — generated CSVs, one per attempted import (gitignored)
