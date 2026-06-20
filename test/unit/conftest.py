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


# Distinct module names so the two `transform` files (and the two stackexchange
# hooks) never collide in sys.modules.
@pytest.fixture(scope="session")
def pgsql():
    return _load("pgsql_transform", "mysql/scripts/pgsql/transform")


@pytest.fixture(scope="session")
def adventureworks():
    return _load("adventureworks_transform", "postgres/scripts/adventureworks/transform")


@pytest.fixture(scope="session")
def se_postgres():
    return _load("se_postgres_transform", "postgres/scripts/stackexchange/transform")


@pytest.fixture(scope="session")
def se_mysql():
    return _load("se_mysql_transform", "mysql/scripts/stackexchange/transform")
