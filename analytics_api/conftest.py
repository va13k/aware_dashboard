"""Shared test wiring for the analytics API.

Two things have to happen before any test module is imported.

`app` is a top-level package that lives inside `analytics_api/`, so it is not
importable when pytest is invoked from the repository root - the directory has
to go on `sys.path` first.

Importing anything from `app` also pulls in `app.database`, which builds both
async engines at import time from ANDROID_DATABASE_URL and IOS_DATABASE_URL.
Neither is set outside Docker, and `create_async_engine(None)` raises, so the
import fails before a single test runs. Placeholder URLs fix that: engines
connect lazily, so a URL that points nowhere is harmless for tests over pure
functions. `load_dotenv()` does not override variables that already exist, so a
real `.env` still wins when there is one.
"""

import json
import os
import pathlib
import sys

import pytest

API_ROOT = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = API_ROOT.parent

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault(
    "ANDROID_DATABASE_URL",
    "mysql+aiomysql://test:test@127.0.0.1:3306/aware_android",
)
os.environ.setdefault(
    "IOS_DATABASE_URL",
    "mysql+aiomysql://test:test@127.0.0.1:3306/aware_ios",
)


@pytest.fixture(scope="session")
def project_root() -> pathlib.Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def deployed_study_config_path() -> pathlib.Path:
    """Path to the deployed study config on the host.

    `studies/` is generated at deployment time and is gitignored, so this file
    is absent in a fresh checkout. Tests that need it skip rather than fail.
    """
    return PROJECT_ROOT / "studies" / "studyConfig.json"


@pytest.fixture(scope="session")
def deployed_study_config(deployed_study_config_path: pathlib.Path) -> dict:
    if not deployed_study_config_path.exists():
        pytest.skip("studies/studyConfig.json is only present after deployment")
    return json.loads(deployed_study_config_path.read_text(encoding="utf-8"))
