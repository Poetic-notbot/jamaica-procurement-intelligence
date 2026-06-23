"""
SQLite persistence layer using SQLAlchemy Core.
Database file: procurement.db (project root).
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String,
    Float, DateTime, text, inspect as sa_inspect,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "procurement.db")
DB_URL = f"sqlite:///{DB_PATH}"
metadata = MetaData()

awards_table = Table(
    "contract_awards", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("procurement_method", String),
    Column("procuring_entity", String),
    Column("title", String),
    Column("contract_amount_jmd", Float),
    Column("publication_date", String),
    Column("notice_pdf_url", String),
    Column("source_url", String),
    Column("category", String),
    Column("scraped_at", DateTime),
)

bids_table = Table(
    "opened_bids", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("cft_title", String),
    Column("reference_number", String),
    Column("procuring_entity", String),
    Column("submission_deadline", String),
    Column("procurement_method", String),
    Column("status", String),
    Column("opened_bids_url", String),
    Column("source_url", String),
    Column("category", String),
    Column("scraped_at", DateTime),
)

supplier_summary_table = Table(
    "supplier_summary", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("supplier_name", String),
    Column("award_count", Integer),
    Column("total_award_value", Float),
    Column("avg_award_value", Float),
    Column("categories", String),
    Column("last_updated", DateTime),
)


def get_engine():
    return create_engine(DB_URL, echo=False)


def init_db():
    engine = get_engine()
    metadata.create_all(engine)
    return engine


def _table_exists(engine, name: str) -> bool:
    return name in sa_inspect(engine).get_table_names()


def upsert_awards(records: list[dict]) -> int:
    if not records:
        return 0
    engine = init_db()
    inserted = 0
    with engine.begin() as conn:
        for rec in records:
            rec.setdefault("scraped_at", datetime.now(timezone.utc))
            stmt = sqlite_insert(awards_table).values(**rec).on_conflict_do_nothing()
            result = conn.execute(stmt)
            inserted += result.rowcount
    return inserted


def upsert_bids(records: list[dict]) -> int:
    if not records:
        return 0
    engine = init_db()
    inserted = 0
    with engine.begin() as conn:
        for rec in records:
            rec.setdefault("scraped_at", datetime.now(timezone.utc))
            stmt = sqlite_insert(bids_table).values(**rec).on_conflict_do_nothing()
            result = conn.execute(stmt)
            inserted += result.rowcount
    return inserted


def rebuild_supplier_summary(engine=None) -> int:
    if engine is None:
        engine = get_engine()
    if not _table_exists(engine, "contract_awards"):
        return 0
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT procuring_entity,
                   COUNT(*) as award_count,
                   SUM(contract_amount_jmd) as total_value,
                   AVG(contract_amount_jmd) as avg_value,
                   GROUP_CONCAT(DISTINCT category) as cats
            FROM contract_awards
            WHERE procuring_entity IS NOT NULL
            GROUP BY procuring_entity
        """)).fetchall()
        conn.execute(text("DELETE FROM supplier_summary"))
        now = datetime.now(timezone.utc)
        for row in rows:
            conn.execute(supplier_summary_table.insert().values(
                supplier_name=row[0], award_count=row[1],
                total_award_value=row[2] or 0.0, avg_award_value=row[3] or 0.0,
                categories=row[4] or "", last_updated=now,
            ))
    return len(rows)


def load_awards() -> list[dict]:
    engine = get_engine()
    if not _table_exists(engine, "contract_awards"):
        return []
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM contract_awards ORDER BY id DESC")).fetchall()
        keys = [c.key for c in awards_table.columns]
        return [dict(zip(keys, row)) for row in rows]


def load_bids() -> list[dict]:
    engine = get_engine()
    if not _table_exists(engine, "opened_bids"):
        return []
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM opened_bids ORDER BY id DESC")).fetchall()
        keys = [c.key for c in bids_table.columns]
        return [dict(zip(keys, row)) for row in rows]


def load_supplier_summary() -> list[dict]:
    engine = get_engine()
    if not _table_exists(engine, "supplier_summary"):
        return []
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM supplier_summary ORDER BY total_award_value DESC")).fetchall()
        keys = [c.key for c in supplier_summary_table.columns]
        return [dict(zip(keys, row)) for row in rows]
