"""Domain database — async SQLAlchemy engine and session factory for AncoraMind Core.

Separate from Agno's runtime DB. Uses parameterized queries exclusively.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_database(database_url: str, echo: bool = False) -> None:
    """Initialize the async SQLAlchemy engine and session factory.

    Must be called once at application startup before any repository operations.

    Args:
        database_url: Async PostgreSQL URL (postgresql+asyncpg://...).
        echo: If True, log all SQL statements (debug mode).
    """
    global _engine, _session_factory

    _engine = create_async_engine(
        database_url,
        echo=echo,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_session() -> AsyncSession:
    """Get a new async database session.

    Returns:
        AsyncSession ready for queries.

    Raises:
        RuntimeError: If init_database() has not been called.
    """
    if _session_factory is None:
        raise RuntimeError(
            "Database not initialized. Call init_database() first."
        )
    return _session_factory()


async def close_database() -> None:
    """Close the database engine and release all connections."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None