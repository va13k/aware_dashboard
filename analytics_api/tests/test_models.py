"""The models have to match the SQL the database was created from.

There are no migrations here - schema changes land by recreating the database
from `db/`, so a model that drifts from the DDL fails at query time against a
real deployment rather than at import.
"""

import pathlib
import re

import pytest

from app.database import AndroidBase
from app.models import AndroidAwareStudy

SCHEMA_FILES = ("db/android-tables.sql", "db/init_all.sql")
ANDROID_SCHEMA = "db/android-tables.sql"
#: Resolved at import so the models under test can be parametrised at collection.
ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Tables whose model holds a subset of the columns on purpose. `screenshot`
#: leaves `image_data` out: it is a longblob of the participant's screen, and a
#: model that named it would carry the picture into every read of the table.
PARTIAL_MODELS = {"screenshot"}


def _declared_tables(sql: str) -> set[str]:
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS `(\w+)`", sql))


def _pinned_models(project_root: pathlib.Path):
    """Every Android model whose table the Android schema declares in full.

    Derived from the mapper registry rather than listed, so a model added or a
    column added to one is covered by the pinning that already exists.
    """
    declared = _declared_tables(
        (project_root / ANDROID_SCHEMA).read_text(encoding="utf-8")
    )
    models = [
        mapper.class_
        for mapper in AndroidBase.registry.mappers
        if mapper.class_.__tablename__ in declared - PARTIAL_MODELS
    ]
    return sorted(models, key=lambda model: model.__tablename__)


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


PINNED_MODELS = _pinned_models(ROOT)


@pytest.mark.parametrize(
    "model", PINNED_MODELS, ids=[m.__tablename__ for m in PINNED_MODELS]
)
@pytest.mark.parametrize("schema_file", SCHEMA_FILES)
def test_a_model_matches_the_schema(
    project_root: pathlib.Path, schema_file: str, model
):
    ddl_columns = _ddl_columns(
        (project_root / schema_file).read_text(encoding="utf-8"), model.__tablename__
    )
    model_columns = [column.name for column in model.__table__.columns]

    assert model_columns == ddl_columns


def test_aware_study_model_points_at_the_study_table():
    assert AndroidAwareStudy.__tablename__ == "aware_studies"
