"""
Upgraded SQLite persistence layer — Jamaica Procurement OS
Schema v2: full category intelligence, supplier profiling,
competition metrics, compliance vault prep, watchlists.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String,
    Float, DateTime, Boolean, Text, UniqueConstraint,
    text, inspect as sa_inspect,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "procurement.db")
DB_URL  = f"sqlite:///{DB_PATH}"
metadata = MetaData()

awards_table = Table(
    "contract_awards", metadata,
    Column("id",                   Integer, primary_key=True, autoincrement=True),
    Column("procurement_method",   String),
    Column("procuring_entity",     String, index=True),
    Column("title",                String),
    Column("contract_amount_jmd",  Float),
    Column("publication_date",     String),
    Column("notice_pdf_url",       String),
    Column("source_url",           String),
    Column("normalized_category",  String, index=True),
    Column("category_confidence",  Float),
    Column("supplier_name",        String),
    Column("scraped_at",           DateTime),
    Column("data_hash",            String),
    UniqueConstraint("data_hash", name="uq_award_hash"),
)

bids_table = Table(
    "opened_bids", metadata,
    Column("id",                   Integer, primary_key=True, autoincrement=True),
    Column("cft_title",            String),
    Column("reference_number",     String),
    Column("procuring_entity",     String, index=True),
    Column("submission_deadline",  String),
    Column("award_date",           String),
    Column("procurement_method",   String),
    Column("status",               String),
    Column("opened_bids_url",      String),
    Column("source_url",           String),
    Column("normalized_category",  String, index=True),
    Column("category_confidence",  Float),
    Column("bidder_count",         Integer),
    Column("scraped_at",           DateTime),
    Column("data_hash",            String),
    UniqueConstraint("data_hash", name="uq_bid_hash"),
)

suppliers_table = Table(
    "suppliers", metadata,
    Column("id",                Integer, primary_key=True, autoincrement=True),
    Column("supplier_name",     String, unique=True, index=True),
    Column("award_count",       Integer, default=0),
    Column("total_award_value", Float,   default=0.0),
    Column("avg_award_value",   Float,   default=0.0),
    Column("categories",        Text),
    Column("buyers",            Text),
    Column("first_seen",        String),
    Column("last_seen",         String),
    Column("last_updated",      DateTime),
)

competition_table = Table(
    "competition_metrics", metadata,
    Column("id",                Integer, primary_key=True, autoincrement=True),
    Column("category",          String, index=True),
    Column("procuring_entity",  String, index=True),
    Column("avg_bidders",       Float),
    Column("median_bidders",    Float),
    Column("min_bidders",       Integer),
    Column("max_bidders",       Integer),
    Column("total_tenders",     Integer),
    Column("last_updated",      DateTime),
)

supplier_profiles_table = Table(
    "supplier_profiles", metadata,
    Column("id",                     Integer, primary_key=True, autoincrement=True),
    Column("company_name",           String, unique=True, index=True),
    Column("trn",                    String),
    Column("tcc_expiry",             String),
    Column("ncc_status",             String),
    Column("insurance_expiry",       String),
    Column("reference_letters_count",Integer, default=0),
    Column("categories",             Text),
    Column("document_urls",          Text),
    Column("created_at",             DateTime),
    Column("updated_at",             DateTime),
)

watchlists_table = Table(
    "watchlists", metadata,
    Column("id",          Integer, primary_key=True, autoincrement=True),
    Column("watch_type",  String),
    Column("watch_value", String),
    Column("created_at",  DateTime),
    UniqueConstraint("watch_type", "watch_value", name="uq_watchlist"),
)

audit_log_table = Table(
    "audit_log", metadata,
    Column("id",            Integer, primary_key=True, autoincrement=True),
    Column("run_at",        DateTime),
    Column("awards_total",  Integer),
    Column("bids_total",    Integer),
    Column("awards_dupes",  Integer),
    Column("bids_dupes",    Integer),
    Column("null_issues",   Integer),
    Column("date_errors",   Integer),
    Column("amount_errors", Integer),
    Column("notes",         Text),
)

_engine = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
    return _engine


def init_db():
    engine = get_engine()
    metadata.create_all(engine)
    _run_migrations(engine)
    logger.info("DB initialised at %s", DB_PATH)


def _run_migrations(engine):
    inspector = sa_inspect(engine)
    with engine.begin() as conn:
        for table_name, new_cols in [
            ("contract_awards", [
                ("normalized_category", "TEXT"),
                ("category_confidence",  "REAL"),
                ("supplier_name",        "TEXT"),
                ("data_hash",            "TEXT"),
            ]),
            ("opened_bids", [
                ("normalized_category", "TEXT"),
                ("category_confidence",  "REAL"),
                ("bidder_count",         "INTEGER"),
                ("award_date",           "TEXT"),
                ("data_hash",            "TEXT"),
            ]),
        ]:
            if table_name not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table_name)}
            for col_name, col_type in new_cols:
                if col_name not in existing:
                    conn.execute(text(
                        f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"
                    ))


def upsert_award(conn, row: dict):
    stmt = sqlite_insert(awards_table).values(**row)
    stmt = stmt.on_conflict_do_nothing(index_elements=["data_hash"])
    conn.execute(stmt)


def upsert_bid(conn, row: dict):
    stmt = sqlite_insert(bids_table).values(**row)
    stmt = stmt.on_conflict_do_nothing(index_elements=["data_hash"])
    conn.execute(stmt)


def upsert_supplier(conn, row: dict):
    stmt = sqlite_insert(suppliers_table).values(**row)
    stmt = stmt.on_conflict_do_update(
        index_elements=["supplier_name"],
        set_={k: v for k, v in row.items() if k != "supplier_name"},
    )
    conn.execute(stmt)


def add_watchlist(conn, watch_type: str, watch_value: str):
    stmt = sqlite_insert(watchlists_table).values(
        watch_type=watch_type,
        watch_value=watch_value,
        created_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["watch_type", "watch_value"]
    )
    conn.execute(stmt)


def remove_watchlist(conn, watch_type: str, watch_value: str):
    conn.execute(
        watchlists_table.delete().where(
            (watchlists_table.c.watch_type  == watch_type) &
            (watchlists_table.c.watch_value == watch_value)
        )
    )

