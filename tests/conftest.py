import pytest

from mars.core.config import Settings
from mars.workflow.service import ResearchService


@pytest.fixture
def settings() -> Settings:
    return Settings(
        provider="mock",
        search_provider="mock",
        api_keys="",
        rate_limit_per_min=0,
        checkpoint_db="",
        log_level="WARNING",
    )


@pytest.fixture
def service(settings) -> ResearchService:
    return ResearchService(settings)


async def collect(events):
    return [ev async for ev in events]


@pytest.fixture(scope="session")
def pg_server(tmp_path_factory):
    """A real, embedded PostgreSQL with pgvector (skipped if pgserver is not installed)."""
    pgserver = pytest.importorskip("pgserver")
    server = pgserver.get_server(tmp_path_factory.mktemp("pg"))
    yield server
    server.cleanup()


@pytest.fixture
def pg_url(pg_server) -> str:
    pg_server.psql(
        "DROP TABLE IF EXISTS mars_chunks, mars_reports, mars_meta CASCADE;"
        "DROP TABLE IF EXISTS checkpoint_writes, checkpoint_blobs, checkpoints, checkpoint_migrations CASCADE;"
    )
    return pg_server.get_uri()
