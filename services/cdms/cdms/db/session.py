import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import Settings

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: AsyncEngine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            connect_args={
                "server_settings": {
                    "application_name": "cdms",
                    "statement_timeout": str(settings.db_statement_timeout_ms),
                }
            },
        )
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        return self._sessionmaker

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def wait_until_ready(self) -> None:
        attempts = self._settings.db_connect_retries
        for attempt in range(1, attempts + 1):
            try:
                async with self._engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                return
            except OperationalError:
                if attempt == attempts:
                    raise
                logger.warning(
                    "database not ready (attempt %d/%d), retrying in %.1fs",
                    attempt,
                    attempts,
                    self._settings.db_connect_retry_delay,
                )
                await asyncio.sleep(self._settings.db_connect_retry_delay)

    async def ping(self) -> bool:
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except OperationalError:
            return False
        return True

    async def dispose(self) -> None:
        await self._engine.dispose()
