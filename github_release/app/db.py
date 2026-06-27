from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional

from .product_names import choose_preferred_display_name, is_noise_name, normalize_product_name, product_name_key


def sqlite_path_from_url(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(f"Unsupported database url: {database_url}")
    return Path(database_url[len(prefix):])


class Database:
    def __init__(self, database_url: str) -> None:
        self.path = sqlite_path_from_url(database_url)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    name_key TEXT,
                    inception_date TEXT,
                    last_source TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS nav_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    nav_date TEXT NOT NULL,
                    nav_value REAL NOT NULL,
                    source_type TEXT NOT NULL,
                    source_ref TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(product_id, nav_date),
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS email_sync_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_uid INTEGER DEFAULT 0,
                    last_message_id TEXT,
                    last_synced_at TEXT
                );

                CREATE TABLE IF NOT EXISTS portfolios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    weight_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS product_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias_name TEXT NOT NULL UNIQUE,
                    alias_key TEXT NOT NULL,
                    product_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS processed_emails (
                    uid INTEGER PRIMARY KEY,
                    message_id TEXT,
                    subject TEXT,
                    inserted_records INTEGER DEFAULT 0,
                    processed_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            product_columns = {row["name"] for row in conn.execute("PRAGMA table_info(products)")}
            if "name_key" not in product_columns:
                conn.execute("ALTER TABLE products ADD COLUMN name_key TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_name_key ON products(name_key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_product_aliases_alias_key ON product_aliases(alias_key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_processed_emails_message_id ON processed_emails(message_id)")
            rows = conn.execute("SELECT id, name FROM products").fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE products SET name_key = COALESCE(name_key, ?) WHERE id = ?",
                    (product_name_key(row["name"]), row["id"]),
                )
            existing_products = conn.execute("SELECT id, name, display_name FROM products").fetchall()
            for row in existing_products:
                alias_candidates = {
                    normalize_product_name(row["name"]),
                    normalize_product_name(row["display_name"]),
                }
                for alias_name in {item for item in alias_candidates if item and not is_noise_name(item)}:
                    conn.execute(
                        """
                        INSERT INTO product_aliases (alias_name, alias_key, product_id)
                        VALUES (?, ?, ?)
                        ON CONFLICT(alias_name) DO UPDATE SET
                            alias_key = excluded.alias_key,
                            product_id = excluded.product_id
                        """,
                        (alias_name, product_name_key(alias_name), row["id"]),
                    )
            conn.execute(
                """
                INSERT INTO email_sync_state (id, last_uid, last_message_id, last_synced_at)
                VALUES (1, 0, '', '')
                ON CONFLICT(id) DO NOTHING
                """
            )

    def fetchall(self, query: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute(query, tuple(params)))

    def fetchone(self, query: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(query, tuple(params)).fetchone()

    def execute(self, query: str, params: Iterable[Any] = ()) -> None:
        with self.connect() as conn:
            conn.execute(query, tuple(params))

    def executemany(self, query: str, params: Iterable[Iterable[Any]]) -> None:
        with self.connect() as conn:
            conn.executemany(query, [tuple(row) for row in params])

    def upsert_product(self, name: str, display_name: Optional[str] = None, source: str = "") -> int:
        name = normalize_product_name(name)
        display_name = normalize_product_name(display_name or name)
        name_key = product_name_key(display_name or name)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, display_name
                FROM products
                WHERE name = ? OR display_name = ?
                LIMIT 1
                """,
                (name, display_name),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT p.id, p.name, p.display_name
                    FROM product_aliases a
                    JOIN products p ON p.id = a.product_id
                    WHERE a.alias_name = ?
                    LIMIT 1
                    """,
                    (name,),
                ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT id, name, display_name
                    FROM products
                    WHERE name_key = ?
                    ORDER BY LENGTH(display_name) DESC, id ASC
                    LIMIT 1
                    """,
                    (name_key,),
                ).fetchone()

            if row is None:
                conn.execute(
                    """
                    INSERT INTO products (name, display_name, name_key, last_source, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (name, display_name, name_key, source),
                )
                row = conn.execute("SELECT id, name, display_name FROM products WHERE name = ?", (name,)).fetchone()
            else:
                preferred_display_name = choose_preferred_display_name(row["display_name"], display_name)
                conn.execute(
                    """
                    UPDATE products
                    SET display_name = ?, name_key = ?, last_source = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (preferred_display_name, name_key, source, row["id"]),
                )

            product_id = int(row["id"])
            canonical = conn.execute("SELECT name, display_name FROM products WHERE id = ?", (product_id,)).fetchone()
            alias_candidates = {
                normalize_product_name(name),
                normalize_product_name(display_name),
                normalize_product_name(canonical["name"]),
                normalize_product_name(canonical["display_name"]),
            }
            for alias_name in {item for item in alias_candidates if item and not is_noise_name(item)}:
                conn.execute(
                    """
                    INSERT INTO product_aliases (alias_name, alias_key, product_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT(alias_name) DO UPDATE SET
                        alias_key = excluded.alias_key,
                        product_id = excluded.product_id
                    """,
                    (alias_name, product_name_key(alias_name), product_id),
                )
            return product_id

    def insert_nav_records(
        self,
        product_id: int,
        records: Iterable[tuple[str, float, str, str]],
    ) -> int:
        rows = [(product_id, nav_date, nav_value, source_type, source_ref) for nav_date, nav_value, source_type, source_ref in records]
        inserted = 0
        with self.connect() as conn:
            for row in rows:
                cursor = conn.execute(
                    """
                    INSERT INTO nav_records (product_id, nav_date, nav_value, source_type, source_ref)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(product_id, nav_date) DO UPDATE SET
                        nav_value = excluded.nav_value,
                        source_type = excluded.source_type,
                        source_ref = excluded.source_ref
                    """,
                    row,
                )
                inserted += cursor.rowcount
            conn.execute(
                """
                UPDATE products
                SET inception_date = (
                    SELECT MIN(nav_date) FROM nav_records WHERE product_id = ?
                ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (product_id, product_id),
            )
        return inserted

    def get_sync_state(self) -> Dict[str, Any]:
        row = self.fetchone("SELECT * FROM email_sync_state WHERE id = 1")
        if row is None:
            return {"last_uid": 0, "last_message_id": "", "last_synced_at": ""}
        return dict(row)

    def update_sync_state(self, last_uid: int, last_message_id: str, last_synced_at: str) -> None:
        self.execute(
            """
            UPDATE email_sync_state
            SET last_uid = ?, last_message_id = ?, last_synced_at = ?
            WHERE id = 1
            """,
            (last_uid, last_message_id, last_synced_at),
        )

    def save_portfolio(self, name: str, weights: Dict[str, Any]) -> None:
        weight_json = json.dumps(weights, ensure_ascii=False, sort_keys=True)
        self.execute(
            """
            INSERT INTO portfolios (name, weight_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET
                weight_json = excluded.weight_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (name, weight_json),
        )

    def load_portfolio(self, name: str) -> Optional[Dict[str, Any]]:
        row = self.fetchone("SELECT weight_json FROM portfolios WHERE name = ?", (name,))
        if row is None:
            return None
        return json.loads(row["weight_json"])

    def get_processed_uids(self, uids: Iterable[int]) -> set[int]:
        uid_list = [int(uid) for uid in uids]
        if not uid_list:
            return set()
        placeholders = ",".join("?" for _ in uid_list)
        rows = self.fetchall(f"SELECT uid FROM processed_emails WHERE uid IN ({placeholders})", uid_list)
        return {int(row["uid"]) for row in rows}

    def mark_email_processed(self, uid: int, message_id: str, subject: str, inserted_records: int) -> None:
        self.execute(
            """
            INSERT INTO processed_emails (uid, message_id, subject, inserted_records, processed_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(uid) DO UPDATE SET
                message_id = excluded.message_id,
                subject = excluded.subject,
                inserted_records = excluded.inserted_records,
                processed_at = CURRENT_TIMESTAMP
            """,
            (uid, message_id, subject, inserted_records),
        )

    def delete_nav_records_before(self, cutoff_date: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM nav_records WHERE nav_date < ?", (cutoff_date,))
            return int(cursor.rowcount)

    def delete_products_by_names(self, names: Iterable[str]) -> int:
        target_names = [str(name) for name in names if str(name).strip()]
        if not target_names:
            return 0
        placeholders = ",".join("?" for _ in target_names)
        with self.connect() as conn:
            cursor = conn.execute(f"DELETE FROM products WHERE name IN ({placeholders})", target_names)
            return int(cursor.rowcount)
