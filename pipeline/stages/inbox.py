import email
import imaplib
from dataclasses import dataclass
from email.header import decode_header, make_header

from pipeline.config import (
    MAIL_FOLDER,
    MAIL_HOST,
    MAIL_IMAP_PORT,
    MAIL_PASSWORD,
    MAIL_PROCESSED_FOLDER,
    MAIL_USERNAME,
)
from pipeline.stages.extract import html_to_text

ORDER_SUBJECT_MARKERS = ("new order",)
ORDER_SEARCH_SUBJECT = "new order"
NOTIFICATION_SUBJECT_PREFIXES = ("fishbowl order entered", "fishbowl entry failed")


@dataclass
class InboxMessage:
    uid: str
    subject: str
    body: str
    sender: str
    received: str
    has_pdf_attachment: bool = False


def is_order_email(subject: str) -> bool:
    text = (subject or "").strip().lower()
    if any(text.startswith(prefix) for prefix in NOTIFICATION_SUBJECT_PREFIXES):
        return False
    return "#" in text and any(marker in text for marker in ORDER_SUBJECT_MARKERS)


def _decode(value) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _body_text(message) -> str:
    parts = message.walk() if message.is_multipart() else [message]
    for wanted in ("text/plain", "text/html"):
        for part in parts:
            if part.get_content_type() != wanted:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            return html_to_text(text) if wanted == "text/html" else text
    return ""


def has_pdf_attachment(message) -> bool:
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        filename = part.get_filename()
        if filename:
            name = _decode(filename).strip().lower()
            if name.endswith(".pdf"):
                return True
        if part.get_content_type() == "application/pdf":
            return True
    return False


def _mailbox_name(name: str) -> str:
    if " " in name and not name.startswith('"'):
        return f'"{name}"'
    return name


class Mailbox:
    def __init__(self, folder: str = MAIL_FOLDER):
        self.folder = folder
        self._client = None

    def connect(self) -> "Mailbox":
        self._client = imaplib.IMAP4_SSL(MAIL_HOST, MAIL_IMAP_PORT)
        self._client.login(MAIL_USERNAME, MAIL_PASSWORD)
        return self

    def close(self) -> None:
        if self._client is None:
            return
        try:
            self._client.logout()
        finally:
            self._client = None

    def __enter__(self) -> "Mailbox":
        return self.connect()

    def __exit__(self, *exc_info) -> None:
        self.close()

    def ensure_folders(self, names) -> None:
        for name in names:
            try:
                self._client.create(_mailbox_name(name))
            except imaplib.IMAP4.error:
                pass

    def _select(self) -> None:
        status, _ = self._client.select(_mailbox_name(self.folder))
        if status != "OK":
            raise RuntimeError(f"cannot open mail folder: {self.folder}")

    def list_unread_orders(self, limit: int = 50) -> list[InboxMessage]:
        self._select()
        status, data = self._client.uid(
            "SEARCH", None, "UNSEEN", "SUBJECT", f'"{ORDER_SEARCH_SUBJECT}"'
        )
        if status != "OK" or not data or not data[0]:
            return []

        messages = []
        for uid in reversed(data[0].split()):
            status, parts = self._client.uid("FETCH", uid, "(BODY.PEEK[])")
            if status != "OK" or not parts or not isinstance(parts[0], tuple):
                continue
            message = email.message_from_bytes(parts[0][1])
            subject = _decode(message.get("Subject"))
            if not is_order_email(subject):
                continue
            messages.append(
                InboxMessage(
                    uid=uid.decode() if isinstance(uid, bytes) else str(uid),
                    subject=subject,
                    body=_body_text(message),
                    sender=_decode(message.get("From")),
                    received=_decode(message.get("Date")),
                    has_pdf_attachment=has_pdf_attachment(message),
                )
            )
            if len(messages) >= limit:
                break
        return messages

    def move(self, uid: str, destination: str) -> None:
        self._select()
        self._client.uid("STORE", uid, "+FLAGS", "(\\Seen)")
        target = _mailbox_name(destination)
        for attempt in (1, 2):
            try:
                status, _ = self._client.uid("MOVE", uid, target)
                if status == "OK":
                    return
            except imaplib.IMAP4.error:
                pass
            try:
                status, _ = self._client.uid("COPY", uid, target)
            except imaplib.IMAP4.error:
                status = "NO"
            if status == "OK":
                self._client.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
                self._client.expunge()
                return
            if attempt == 1:
                self._client.create(target)
                self._select()
        raise RuntimeError(f"could not move uid {uid} to {target}")

    def move_to_processed(self, uid: str) -> None:
        self.move(uid, MAIL_PROCESSED_FOLDER)

    def mark_seen(self, uid: str) -> None:
        self._select()
        self._client.uid("STORE", uid, "+FLAGS", "(\\Seen)")
