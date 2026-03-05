"""CLI wrapper around Alembic migrations.

Usage:
    python migrate.py upgrade [revision]   Apply migrations (default: head)
    python migrate.py downgrade <revision> Rollback to a revision
    python migrate.py current              Show current DB revision
    python migrate.py history              Show migration history
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import argparse
import logging
import os
import sys

from alembic import command
from alembic.config import Config as AlembicConfig

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATABASE_URL

logging.basicConfig(level=logging.INFO, format="%(levelname)-5s %(message)s")
logger = logging.getLogger(__name__)

def _get_alembic_cfg() -> AlembicConfig:
    ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
    cfg = AlembicConfig(ini_path)
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    return cfg


def cmd_upgrade(args: argparse.Namespace) -> None:
    cfg = _get_alembic_cfg()
    revision = args.revision or "head"
    logger.info("Upgrading database to revision: %s", revision)
    command.upgrade(cfg, revision)
    logger.info("Upgrade complete")


def cmd_downgrade(args: argparse.Namespace) -> None:
    cfg = _get_alembic_cfg()
    if not args.revision:
        logger.error("downgrade requires a target revision (e.g. -1, base, or a revision id)")
        sys.exit(1)
    logger.info("Downgrading database to revision: %s", args.revision)
    command.downgrade(cfg, args.revision)
    logger.info("Downgrade complete")


def cmd_current(args: argparse.Namespace) -> None:
    cfg = _get_alembic_cfg()
    command.current(cfg, verbose=True)


def cmd_history(args: argparse.Namespace) -> None:
    cfg = _get_alembic_cfg()
    command.history(cfg, verbose=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Database migration tool")
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("upgrade", help="Apply migrations (default: head)")
    up.add_argument("revision", nargs="?", default="head")
    up.set_defaults(func=cmd_upgrade)

    down = sub.add_parser("downgrade", help="Rollback to a target revision")
    down.add_argument("revision", help="Target revision (e.g. -1, base, or revision id)")
    down.set_defaults(func=cmd_downgrade)

    cur = sub.add_parser("current", help="Show current DB revision")
    cur.set_defaults(func=cmd_current)

    hist = sub.add_parser("history", help="Show migration history")
    hist.set_defaults(func=cmd_history)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
