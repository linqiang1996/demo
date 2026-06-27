from __future__ import annotations

import email
import imaplib
import logging
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header
from email.message import Message

from .config import MailConfig
from .db import Database
from .nav_parser import parse_body_text, parse_excel_bytes


logger = logging.getLogger(__name__)


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    decoded_parts = decode_header(value)
    parts = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            preferred = encoding or "utf-8"
            try:
                parts.append(part.decode(preferred, errors="ignore"))
            except LookupError:
                parts.append(part.decode("utf-8", errors="ignore"))
        else:
            parts.append(part)
    return "".join(parts)


def _decode_bytes(payload: bytes, charset: str | None) -> str:
    candidates: list[str] = []
    if charset:
        cleaned = charset.strip().split(";")[0].split()[0].replace("\r", "").replace("\n", "")
        if cleaned:
            candidates.append(cleaned)
    candidates.extend(["utf-8", "gb18030", "gbk", "gb2312", "big5"])
    for candidate in candidates:
        try:
            return payload.decode(candidate, errors="ignore")
        except LookupError:
            continue
        except Exception:
            continue
    return payload.decode("utf-8", errors="ignore")


def _extract_text_part(message: Message) -> str:
    if message.is_multipart():
        chunks: list[str] = []
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = part.get_content_disposition()
            if disposition == "attachment":
                continue
            if content_type in {"text/plain", "text/html"}:
                payload = part.get_payload(decode=True) or b""
                chunks.append(_decode_bytes(payload, part.get_content_charset()))
        return "\n".join(chunks)
    payload = message.get_payload(decode=True) or b""
    return _decode_bytes(payload, message.get_content_charset())


@dataclass
class SyncResult:
    searched_messages: int
    synced_messages: int
    skipped_processed_messages: int
    inserted_records: int
    last_uid: int
    last_message_id: str
    last_synced_at: str


class MailSyncService:
    def __init__(self, db: Database, config: MailConfig) -> None:
        self.db = db
        self.config = config

    def sync(self, full_rescan: bool = False, reprocess_existing: bool = False) -> SyncResult:
        state = self.db.get_sync_state()
        if not self.config.configured:
            return SyncResult(
                searched_messages=0,
                synced_messages=0,
                skipped_processed_messages=0,
                inserted_records=0,
                last_uid=int(state.get("last_uid", 0) or 0),
                last_message_id=str(state.get("last_message_id", "") or ""),
                last_synced_at=str(state.get("last_synced_at", "") or ""),
            )

        last_uid = int(state.get("last_uid", 0) or 0)
        searched_messages = 0
        inserted_records = 0
        synced_messages = 0
        skipped_processed_messages = 0
        newest_uid = last_uid
        newest_message_id = str(state.get("last_message_id", "") or "")

        client_class = imaplib.IMAP4_SSL if self.config.use_ssl else imaplib.IMAP4
        with client_class(self.config.imap_host, self.config.imap_port) as client:
            client.login(self.config.email_address, self.config.password)
            client.select(self.config.folder)
            search_start_uid = 1 if full_rescan else (max(1, last_uid - self.config.overlap_uids + 1) if last_uid > 0 else 1)
            if not full_rescan and last_uid == 0 and self.config.initial_sync_limit > 0:
                status, status_data = client.status(self.config.folder, "(UIDNEXT)")
                if status == "OK" and status_data:
                    raw_text = status_data[0].decode("utf-8", errors="ignore")
                    marker = "UIDNEXT "
                    if marker in raw_text:
                        try:
                            uid_next = int(raw_text.split(marker, 1)[1].split()[0].rstrip(")"))
                            search_start_uid = max(1, uid_next - self.config.initial_sync_limit)
                        except ValueError:
                            search_start_uid = 1
            status, data = client.uid("SEARCH", None, "UID", f"{search_start_uid}:*")
            if status != "OK":
                raise RuntimeError("Unable to search mailbox")

            uid_list = [int(item) for item in data[0].split() if item]
            searched_messages = len(uid_list)
            processed_uids = set() if reprocess_existing else self.db.get_processed_uids(uid_list)
            for uid in uid_list:
                newest_uid = max(newest_uid, uid)
                if uid in processed_uids:
                    skipped_processed_messages += 1
                    continue
                status, msg_data = client.uid("FETCH", str(uid), "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw_email = msg_data[0][1]
                message = email.message_from_bytes(raw_email)
                subject = _decode_header_value(message.get("Subject"))
                message_id = _decode_header_value(message.get("Message-Id"))

                inserted = self._ingest_message(message, subject=subject, message_id=message_id)
                inserted_records += inserted
                synced_messages += 1
                newest_message_id = message_id or newest_message_id
                self.db.mark_email_processed(uid, message_id, subject, inserted)

        synced_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.update_sync_state(newest_uid, newest_message_id, synced_at)
        return SyncResult(
            searched_messages=searched_messages,
            synced_messages=synced_messages,
            skipped_processed_messages=skipped_processed_messages,
            inserted_records=inserted_records,
            last_uid=newest_uid,
            last_message_id=newest_message_id,
            last_synced_at=synced_at,
        )

    def _ingest_message(self, message: Message, subject: str, message_id: str) -> int:
        inserted = 0
        source_ref = message_id or subject

        body_text = _extract_text_part(message)
        for parsed in parse_body_text(body_text):
            product_id = self.db.upsert_product(parsed.product_name, parsed.product_name, source="mail-body")
            inserted += self.db.insert_nav_records(
                product_id,
                [(nav_date, nav_value, "mail-body", source_ref) for nav_date, nav_value in parsed.records],
            )

        for part in message.walk():
            disposition = part.get_content_disposition()
            filename = part.get_filename()
            if disposition != "attachment" or not filename:
                continue
            decoded_filename = _decode_header_value(filename)
            lower_name = decoded_filename.lower()
            if not lower_name.endswith((".xlsx", ".xls")):
                continue
            payload = part.get_payload(decode=True) or b""
            for parsed in parse_excel_bytes(payload, decoded_filename, extra_name_hints=[subject, decoded_filename]):
                product_id = self.db.upsert_product(parsed.product_name, parsed.product_name, source="mail-attachment")
                inserted += self.db.insert_nav_records(
                    product_id,
                    [(nav_date, nav_value, "mail-attachment", source_ref) for nav_date, nav_value in parsed.records],
                )
        return inserted
