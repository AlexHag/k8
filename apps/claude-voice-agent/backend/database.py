from __future__ import annotations

import logging
import os

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import scoped_session, sessionmaker

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory

from config import DATABASE_URL, DB_TYPE
from models.tables import start_mappers

logger = logging.getLogger(__name__)


def create_engine_from_config() -> Engine:
    kwargs: dict = {}

    if DB_TYPE == "sqlite":
        kwargs["connect_args"] = {"check_same_thread": False}
        engine = create_engine(DATABASE_URL, **kwargs)

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    else:
        kwargs["pool_pre_ping"] = True
        engine = create_engine(DATABASE_URL, **kwargs)

    return engine


def create_scoped_session(engine: Engine) -> scoped_session:
    start_mappers()
    factory = sessionmaker(bind=engine)
    return scoped_session(factory)


def _alembic_cfg() -> AlembicConfig:
    ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
    cfg = AlembicConfig(ini_path)
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    return cfg


def check_migration_version(engine: Engine) -> None:
    """Verify the database is at the expected Alembic head revision.

    Raises RuntimeError if the alembic_version table is missing, empty, or
    contains a revision that doesn't match the head of the migration scripts.
    """
    cfg = _alembic_cfg()
    script = ScriptDirectory.from_config(cfg)
    expected_head = script.get_current_head()

    if expected_head is None:
        logger.warning("No Alembic migration scripts found — skipping version check")
        return

    has_table = inspect(engine).has_table("alembic_version")
    if not has_table:
        raise RuntimeError(
            f"Database has no alembic_version table. "
            f"Expected revision {expected_head!r}. "
            f"Run migrations first: python migrate.py upgrade"
        )

    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()

    if row is None:
        raise RuntimeError(
            f"alembic_version table is empty. "
            f"Expected revision {expected_head!r}. "
            f"Run migrations first: python migrate.py upgrade"
        )

    current = row[0]
    if current != expected_head:
        raise RuntimeError(
            f"Database migration version mismatch: "
            f"database is at {current!r}, app expects {expected_head!r}. "
            f"Run migrations: python migrate.py upgrade"
        )

    logger.info("Database migration version OK: %s", current)
