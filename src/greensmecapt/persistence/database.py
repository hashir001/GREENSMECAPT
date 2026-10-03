"""Database engine and session management."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

class Database:
    """Manage one SQLModel-compatible database."""

    def __init__(
        self,
        database_url: str | None = None,
    ) -> None:
        configured_url = (
            database_url
            or os.environ.get("GREENSMECAPT_DATABASE_URL")
            or "sqlite:///./greensmecapt.db"
        )
        self.url = _normalize_database_url(configured_url)

        connect_args = {}

        if self.url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        self.engine = create_engine(
            self.url,
            connect_args=connect_args,
            pool_pre_ping=True,
        )

    def create_schema(self) -> None:
        """Create currently registered application tables."""

        SQLModel.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a session and always close it."""

        with Session(self.engine) as session:
            yield session


def _normalize_database_url(value: str) -> str:
    """Select Psycopg 3 for PostgreSQL-style URLs."""

    if value.startswith("postgres://"):
        return value.replace(
            "postgres://",
            "postgresql+psycopg://",
            1,
        )

    if value.startswith("postgresql://"):
        return value.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    return value
