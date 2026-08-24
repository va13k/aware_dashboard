"""Prerequisites for the study-status work (Phase 0).

These are not tests of application behaviour - they guard the three things the
later phases silently depend on: the test harness can import `app`, the schema
carries the study-state columns, and the API process can reach the deployed
study config.
"""

import pathlib
import re

import pytest
import yaml

from app.services import study_config

CONFIG_PATH_ENV = "CURRENT_STUDY_CONFIG_PATH"
CONTAINER_CONFIG_PATH = "/app/studies/studyConfig.json"
STUDIES_MOUNT = "./studies:/app/studies:ro"

SCHEMA_FILES = ("db/android-tables.sql", "db/init_all.sql")


def _aware_studies_ddl(sql: str) -> str:
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS `aware_studies`\s*\((.*?)\n\)",
        sql,
        re.DOTALL,
    )
    assert match, "aware_studies is not declared in this schema file"
    return match.group(1)


def test_app_package_imports_without_a_live_database():
    """The engines are built at import time, so this is the harness smoke test."""
    from app import models

    assert models.AndroidBase is not None


@pytest.mark.parametrize("schema_file", SCHEMA_FILES)
def test_aware_studies_schema_supports_study_state(
    project_root: pathlib.Path, schema_file: str
):
    ddl = _aware_studies_ddl(
        (project_root / schema_file).read_text(encoding="utf-8")
    )

    # double_updated pairs a re-authentication resume with the update that
    # started it; without it the pause duration cannot be derived.
    assert "`double_updated`" in ddl
    # Per-device history reads filter by device_id and sort by time. The older
    # (timestamp, device_id) index is ordered the wrong way round for that.
    assert "KEY `device_study_time` (`device_id`,`timestamp`,`_id`)" in ddl


def test_dashboard_api_can_read_the_deployed_study_config(
    project_root: pathlib.Path,
):
    compose = yaml.safe_load(
        (project_root / "docker-compose.yml").read_text(encoding="utf-8")
    )
    service = compose["services"]["dashboard-api"]

    assert service["environment"][CONFIG_PATH_ENV] == CONTAINER_CONFIG_PATH
    # Read-only on purpose: the API compares configs, it never writes them.
    assert STUDIES_MOUNT in service["volumes"]


def test_deployed_study_config_has_the_fields_later_phases_read(
    deployed_study_config: dict,
):
    config = deployed_study_config

    assert config.get("_id") is not None
    assert config.get("updatedAt")

    settings = {
        entry["setting"]: entry["value"]
        for entry in config["sensors"]
        if isinstance(entry, dict) and "setting" in entry
    }
    assert settings, "the sensors list is empty or not in {setting, value} form"
    assert "enable_config_update" in settings
    assert any(name.startswith("status_") for name in settings)


def test_deployed_study_config_carries_credentials_on_the_direct_path(
    deployed_study_config: dict,
):
    """Documents why the diff is built server-side over an allowlist.

    The dataflow decides whether there is a credential to keep out of a diff. A
    phone on the direct path opens the database itself, so its config carries the
    password and the phone's own copy is the other half of the comparison. On the
    webservice path the micro-server holds the credential and the published config
    has no database block, which is what makes a config served from a public path
    safe to serve.
    """
    declared, _ = study_config.dataflow(deployed_study_config)
    database = deployed_study_config.get("database", {})

    if declared == study_config.WEBSERVICE:
        assert "database_password" not in database
    else:
        assert "database_password" in database
