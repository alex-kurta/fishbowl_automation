import argparse
import logging
import os
import signal
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline.config
from pipeline.config import (
    DATA_DIR,
    LOG_DIR,
    MAIL_FOLDER,
    MAIL_PROCESSED_FOLDER,
    ORDER_NOTIFY_TO,
    OUTPUT_DIR,
    inbox_hold_active,
    inbox_hold_until,
)
from pipeline.fishbowl_api import FishbowlApiClient, FishbowlAuthError
from pipeline.stages.extract import extract_order_from_body
from pipeline.stages.guards import SkipMessage, comment_references, quote_reference
from pipeline.stages.import_to_fishbowl import (
    DuplicateOrderError,
    find_existing_orders,
    import_sales_order,
)
from pipeline.stages.inbox import Mailbox
from pipeline.stages.normalize import _normalize_sku, order_to_csv
from pipeline.stages.product_alerts import alert_notes, pick_ticket_code
from pipeline.stages.notify import (
    build_failure_notification,
    build_notification,
    send_notification,
)
from pipeline.stages.verify import find_sales_order, sales_order_items

log = logging.getLogger("auto_order_entry")

_hold_state = None


def _warn_on_incomplete_address(order) -> None:
    for label, addr in (("billing", order.billing), ("shipping", order.shipping)):
        missing = [
            name
            for name, value in (
                ("city", addr.city),
                ("state", addr.state),
                ("zip", addr.zip_code),
            )
            if not value
        ]
        if missing and addr.street:
            log.warning(
                "PO %s: %s address missing %s (street=%r), needs correction",
                order.order_number,
                label,
                "/".join(missing),
                addr.street,
            )


def _apply_product_notes(order) -> None:
    try:
        notes = alert_notes(_normalize_sku(line) for line in order.lines)
    except Exception:
        log.exception("product alert notes unavailable, item notes left blank")
        return

    applied = []
    for line in order.lines:
        message = notes.get(_normalize_sku(line).upper(), "")
        code = pick_ticket_code(message)
        if not code:
            continue
        line.note = code
        line.alert = " ".join(message.split())
        applied.append(f"{line.sku}={code}")
    if applied:
        log.info("PO %s: item notes %s", order.order_number, ", ".join(applied))


def process_message(message, client, args) -> str:
    order = extract_order_from_body(message.body, message.subject)
    _warn_on_incomplete_address(order)

    quote = quote_reference(message.subject, order.order_number)
    if quote:
        raise SkipMessage(f"quote reference {quote}, not an order")

    if not order.order_number:
        raise ValueError("order number not found in the email")
    if not order.lines:
        raise ValueError("no line items parsed from the email body (PDF-only order?)")

    for reference in comment_references(message.body):
        existing = find_existing_orders(reference)
        if existing:
            raise SkipMessage(
                f"comment references existing PO {reference} "
                f"(SO {existing[0]['num']}), handle manually"
            )

    _apply_product_notes(order)
    csv_path = order_to_csv(order, OUTPUT_DIR / f"order_{order.order_number}.csv")
    existing = find_existing_orders(order.order_number)
    if existing:
        so = existing[0]
        return f"duplicate skipped, already SO {so['num']} (customer PO {order.order_number})"

    if args.dry_run:
        return f"dry run, would import PO {order.order_number} with {len(order.lines)} line(s)"

    try:
        import_sales_order(csv_path, client=client)
    except DuplicateOrderError as exc:
        return f"duplicate skipped, {exc}"

    so = find_sales_order(order.order_number)
    if so is None:
        raise RuntimeError(f"import returned success but no SO found for PO {order.order_number}")

    subject, body, html_body = build_notification(order, so, sales_order_items(so["id"]))
    send_notification(subject, body, ORDER_NOTIFY_TO, html_body)
    return f"imported SO {so['num']}, review request sent to {ORDER_NOTIFY_TO}"


def setup_logging(quiet: bool = False) -> None:
    log.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    if not quiet:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        log.addHandler(console)
    handler = RotatingFileHandler(
        LOG_DIR / "auto_order_entry.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    log.addHandler(handler)


LOCK_PATH = DATA_DIR / "auto_order_entry.lock"
LOCK_STALE_SECONDS = 120


def acquire_lock():
    try:
        handle = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        age = time.time() - LOCK_PATH.stat().st_mtime
        if age < LOCK_STALE_SECONDS:
            return None
        LOCK_PATH.unlink(missing_ok=True)
        return acquire_lock()

    os.write(handle, str(os.getpid()).encode())
    os.close(handle)
    return LOCK_PATH


def refresh_lock(lock) -> None:
    try:
        os.utime(lock, None)
    except OSError:
        pass


def attempt(message, client, args) -> str:
    try:
        return process_message(message, client, args)
    except FishbowlAuthError:
        if client is None or args.dry_run:
            raise
        log.warning("Fishbowl session was rejected, logging in again")
        client.login()
        return process_message(message, client, args)


def process_pending(mailbox, client, args) -> tuple[int, int]:
    hold = inbox_hold_active()
    global _hold_state
    if hold != _hold_state:
        if hold:
            log.info(
                "INBOX hold active until %s: handled mail is marked seen and left in %s",
                inbox_hold_until().isoformat(),
                args.folder,
            )
        else:
            log.info("INBOX hold finished, handled mail moves to %s again", MAIL_PROCESSED_FOLDER)
        _hold_state = hold

    messages = mailbox.list_unread_orders(args.limit)
    if messages or not args.quiet:
        log.info("found %s unread order email(s) in %s", len(messages), args.folder)

    failures = 0
    for message in messages:
        if message.has_pdf_attachment:
            log.info(
                "%s -> skipped, PDF attachment (no order data in email body, left for manual entry)",
                message.subject,
            )
            continue

        try:
            outcome = attempt(message, client, args)
        except SkipMessage as exc:
            log.info("%s -> skipped, %s", message.subject, exc)
            continue
        except Exception as exc:
            failures += 1
            log.exception("failed to process: %s", message.subject)
            if not args.dry_run:
                mailbox.mark_seen(message.uid)
                try:
                    subject, body = build_failure_notification(message, exc)
                    send_notification(subject, body, ORDER_NOTIFY_TO)
                except Exception:
                    log.exception("could not send failure notification")
            continue

        log.info("%s -> %s", message.subject, outcome)
        if not args.dry_run:
            if hold:
                mailbox.mark_seen(message.uid)
            else:
                try:
                    mailbox.move_to_processed(message.uid)
                except Exception:
                    log.exception(
                        "could not move handled mail to %s, left in %s",
                        MAIL_PROCESSED_FOLDER,
                        args.folder,
                    )

    return len(messages), failures


def run_once(args) -> int:
    client = None
    if not args.dry_run:
        client = FishbowlApiClient.from_env()
        client.login()

    try:
        with Mailbox(args.folder) as mailbox:
            if not args.dry_run:
                mailbox.ensure_folders([MAIL_PROCESSED_FOLDER])
            found, failures = process_pending(mailbox, client, args)
    finally:
        if client is not None:
            client.logout()

    if found or failures or not args.quiet:
        log.info("done, %s email(s), %s failure(s)", found, failures)
    return 1 if failures else 0


def run_forever(lock, args) -> int:
    client = None
    mailbox = None
    iterations = 0
    backoff = 5

    try:
        while True:
            try:
                if client is None and not args.dry_run:
                    client = FishbowlApiClient.from_env()
                    client.login()
                if mailbox is None:
                    mailbox = Mailbox(args.folder).connect()
                    if not args.dry_run:
                        mailbox.ensure_folders([MAIL_PROCESSED_FOLDER])

                refresh_lock(lock)
                found, failures = process_pending(mailbox, client, args)
                if found or failures:
                    log.info("done, %s email(s), %s failure(s)", found, failures)
                backoff = 5
            except Exception:
                log.exception("run failed, reconnecting")
                if mailbox is not None:
                    try:
                        mailbox.close()
                    except Exception:
                        pass
                    mailbox = None
                if client is not None:
                    try:
                        client.logout()
                    except Exception:
                        pass
                    client = None
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
                continue

            iterations += 1
            if args.iterations and iterations >= args.iterations:
                return 0

            time.sleep(args.interval)
    except KeyboardInterrupt:
        log.info("interrupted")
        return 0
    finally:
        if mailbox is not None:
            try:
                mailbox.close()
            except Exception:
                pass
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass


def stop_on_sigterm(signum, frame):
    raise SystemExit(0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read unread order emails from the sales mailbox and enter them into Fishbowl"
    )
    parser.add_argument("--folder", default=MAIL_FOLDER, help="mail folder to read")
    parser.add_argument("--limit", type=int, default=20, help="maximum emails per pass")
    parser.add_argument("--dry-run", action="store_true", help="parse and check duplicates only")
    parser.add_argument(
        "--interval",
        type=int,
        default=0,
        help="poll every N seconds in one long-lived process (0 = run once and exit)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="stop after N polls (0 = forever), mainly for testing",
    )
    parser.add_argument("--quiet", action="store_true", help="no console output, no idle log lines")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, stop_on_sigterm)
    setup_logging(args.quiet)

    lock = acquire_lock()
    if lock is None:
        log.info("another run is still in progress, exiting")
        return 0

    try:
        if args.interval:
            return run_forever(lock, args)
        return run_once(args)
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
