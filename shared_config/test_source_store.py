"""Tests for the study model as a file, read and written from either platform.

One file, reached by two processes: this deploy on the host, and the Configurator in
its container. A read is taken under a lock where the platform offers one, and a
write is atomic on both.

The lock is the half the platforms spell differently. `fcntl`, and a directory a
process may open, are Unix's. A deployment on Windows runs the same host scripts
against the same file --- the deploy that creates the schema, the one that publishes
the database's own authority, and both checks all read it --- so a lock written one
way only is every one of those stopping before it does anything.
"""

import json
import pathlib
import sys

import pytest

PROJECT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from shared_config import source_store  # noqa: E402

TEMPLATE = {"version": 1, "study": {"title": "the one in the template"}}


@pytest.fixture
def study(tmp_path, monkeypatch):
    """A study model of this test's own, so none of them reads the deployment's."""
    monkeypatch.setattr(source_store, "SOURCE_PATH", tmp_path / "source.json")
    monkeypatch.setattr(source_store, "TEMPLATE_PATH", tmp_path / "source.example.json")
    (tmp_path / "source.example.json").write_text(
        json.dumps(TEMPLATE, indent=2) + "\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def without_a_lock(monkeypatch):
    """The platform Windows presents: no advisory lock module of any kind."""
    monkeypatch.setattr(source_store, "fcntl", None)


def test_the_model_is_read_where_the_platform_locks(study):
    assert source_store.read_source() == TEMPLATE


def test_the_model_is_read_where_the_platform_does_not(study, without_a_lock):
    """What every host script on Windows asks for first."""
    assert source_store.read_source() == TEMPLATE


def test_the_template_becomes_the_model_on_the_first_read(study, without_a_lock):
    assert not (study / "source.json").exists()

    source_store.read_source()

    assert json.loads((study / "source.json").read_text(encoding="utf-8")) == TEMPLATE


def test_an_edit_survives_the_next_read(study, without_a_lock):
    """The Configurator's saves are what a later deploy must not write over."""
    source_store.update_source(
        lambda model: {**model, "study": {"title": "what the researcher typed"}}
    )

    assert source_store.read_source()["study"]["title"] == "what the researcher typed"


def test_a_write_lands_whole(study, without_a_lock):
    """The guarantee that stands without a lock: a reader sees one version or the other."""
    source_store.write_source({"version": 2, "study": {"title": "written outright"}})
    text = (study / "source.json").read_text(encoding="utf-8")

    assert json.loads(text)["version"] == 2
    assert text.endswith("\n")


def test_the_module_loads_where_fcntl_cannot_be_imported(monkeypatch):
    """The failure a Windows host meets on the first script that reads the study.

    Simulated at the import rather than at the attribute, because that is where the
    platform answers: `import fcntl` is what Windows has nothing for, and every
    module reaching the study model goes through this one.
    """
    import importlib

    monkeypatch.setitem(sys.modules, "fcntl", None)
    monkeypatch.delitem(sys.modules, "shared_config.source_store", raising=False)

    reloaded = importlib.import_module("shared_config.source_store")

    assert reloaded.fcntl is None
    with reloaded.source_lock():
        pass
