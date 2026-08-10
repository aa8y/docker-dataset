"""Shared fixtures for the Python transform unit tests.

The transform hooks are deliberately extensionless (the Dockerfile locates them
by exact path, scripts/<dataset>/<step>), so they can't be imported normally.
Each is loaded here by explicit source loader and exposed as a session fixture.
Importing a hook has no side effects: every hook guards execution with
``if __name__ == "__main__": main()``.
"""
import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name, relpath):
    """Import an extensionless transform hook as a module named ``name``."""
    path = ROOT / relpath
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# Distinct module names so the same-named `transform` files (and the four
# stackexchange hooks) never collide in sys.modules.
@pytest.fixture(scope="session")
def pgsql():
    return _load("pgsql_transform", "mysql/scripts/pgsql/transform")


@pytest.fixture(scope="session")
def sqlite_pgsql():
    return _load("sqlite_pgsql_transform", "sqlite/scripts/pgsql/transform")


@pytest.fixture(scope="session")
def adventureworks():
    return _load("adventureworks_transform", "postgres/scripts/adventureworks/transform")


@pytest.fixture(scope="session")
def se_postgres():
    return _load("se_postgres_transform", "postgres/scripts/stackexchange/transform")


@pytest.fixture(scope="session")
def se_mysql():
    return _load("se_mysql_transform", "mysql/scripts/stackexchange/transform")


@pytest.fixture(scope="session")
def se_sqlite():
    return _load("se_sqlite_transform", "sqlite/scripts/stackexchange/transform")


@pytest.fixture(scope="session")
def duckdb_chinook():
    return _load("duckdb_chinook_transform", "duckdb/scripts/chinook/transform")


@pytest.fixture(scope="session")
def duckdb_pgsql():
    return _load("duckdb_pgsql_transform", "duckdb/scripts/pgsql/transform")


@pytest.fixture(scope="session")
def se_duckdb():
    return _load("se_duckdb_transform", "duckdb/scripts/stackexchange/transform")


@pytest.fixture(scope="session")
def se_cockroach():
    # Binds CSV_DIR from $CSV_DIR at import time; tests that run main() must
    # monkeypatch.setattr(se_cockroach, "CSV_DIR", ...) -- setting the env var
    # inside a test is too late.
    return _load("se_cockroach_transform", "cockroach/scripts/stackexchange/transform")


@pytest.fixture(scope="session")
def pgfoundry():
    return _load("pgfoundry_transform", "cockroach/scripts/pgfoundry/transform")


@pytest.fixture(scope="session")
def yugabyte():
    return _load("yugabyte_transform", "cockroach/scripts/yugabyte/transform")


@pytest.fixture(scope="session")
def moma():
    # Like the cockroach stackexchange hook, CSV_DIR is bound at import; SCHEMA
    # is a fixed path constant read only inside main(). Neither is touched at
    # import, so loading is side-effect free -- but both must be patched on the
    # module object before main() runs.
    return _load("moma_transform", "cockroach/scripts/moma/transform")
