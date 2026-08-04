"""The models have to match the SQL the database was created from.

There are no migrations here - schema changes land by recreating the database
from `db/`, so a model that drifts from the DDL fails at query time against a
real deployment rather than at import.
"""

import pathlib
import re

import pytest

from app.models import AndroidAwareStudy

SCHEMA_FILES = ("db/android-tables.sql", "db/init_all.sql")


def _ddl_columns(sql: str, table: str) -> list[str]:
    body = re.search(
        rf"CREATE TABLE IF NOT EXISTS `{table}`\s*\((.*?)\n\)",
        sql,
        re.DOTALL,
    )
    assert body, f"{table} is not declared in this schema file"

    columns = []
    for line in body.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("`"):
            columns.append(stripped.split("`")[1])
    return columns


@pytest.mark.parametrize("schema_file", SCHEMA_FILES)
def test_aware_study_model_matches_the_schema(
    project_root: pathlib.Path, schema_file: str
):
    ddl_columns = _ddl_columns(
        (project_root / schema_file).read_text(encoding="utf-8"), "aware_studies"
    )
    model_columns = [column.name for column in AndroidAwareStudy.__table__.columns]

    assert model_columns == ddl_columns


def test_aware_study_model_points_at_the_study_table():
    assert AndroidAwareStudy.__tablename__ == "aware_studies"
