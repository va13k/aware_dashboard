"""Tests for the two scripts a researcher runs, held to one deployment between them.

`setup.sh` and `setup.bat` are the same deployment written twice, for a researcher
on a Mac or a Linux server and a researcher on Windows. Everything either one knows
about the stack it brings up it knows by naming a helper in `setup/` and a container
in the compose file, so the pair is checked here on exactly those two things: the
scripts they call, and the containers whose health decides that the browser may be
redirected.

Both are read as text rather than run. What a deploy does needs Docker and a
database; what a deploy *names* is on the page, and a name that has moved is a
Windows run that stops after `compose up` with a stack of empty schemas behind it.
"""

import pathlib
import re
import sys

import pytest

PROJECT = pathlib.Path(__file__).resolve().parent.parent
SETUP = PROJECT / "setup"
sys.path.insert(0, str(SETUP))

import publish_authority  # noqa: E402

SH = (PROJECT / "setup.sh").read_text(encoding="utf-8")
BAT = (PROJECT / "setup.bat").read_text(encoding="utf-8")


def scripts_named_in(text: str) -> set[str]:
    """The `setup/` helpers a script calls, by filename, either slash accepted."""
    return set(re.findall(r"setup[/\\]([A-Za-z0-9_]+\.py)", text))


def health_lists_in(text: str) -> set[frozenset[str]]:
    """The container groups a script waits on, one group per database placement."""
    return {
        frozenset(line.split())
        for line in re.findall(r"((?:aware_[a-z_]+ ?)+)", text)
        if "aware_nginx" in line
    }


def test_every_setup_script_named_by_the_shell_entrypoint_exists():
    for name in sorted(scripts_named_in(SH)):
        assert (SETUP / name).is_file(), f"setup.sh calls setup/{name}, which is absent"


def test_every_setup_script_named_by_the_windows_entrypoint_exists():
    for name in sorted(scripts_named_in(BAT)):
        assert (SETUP / name).is_file(), f"setup.bat calls setup/{name}, which is absent"


def test_both_entrypoints_call_the_same_setup_scripts():
    assert scripts_named_in(SH) == scripts_named_in(BAT)


def test_both_entrypoints_wait_on_the_same_containers():
    """One group per placement, and the bundled database is what separates them."""
    groups = health_lists_in(SH)

    assert groups == health_lists_in(BAT)
    assert len(groups) == 2
    smaller, larger = sorted(groups, key=len)
    assert larger - smaller == {"aware_mysql"}


class _Source:
    """A study model that answers with the database host it was given."""

    def __init__(self, host):
        self.host = host

    def __call__(self):
        return {"database": {"host": self.host}}


@pytest.fixture
def served(tmp_path, monkeypatch):
    """The config the phones fetch, wherever the test wants to put it."""
    path = tmp_path / "studyConfig.json"
    monkeypatch.setattr(publish_authority, "SERVED_CONFIG", path)
    return path


@pytest.fixture
def bundled(monkeypatch):
    """A study whose database this deployment runs."""
    from shared_config import source_store

    monkeypatch.setattr(source_store, "read_source", _Source("db.internal"))


def test_a_bundled_study_with_nothing_served_yet_is_published(served, bundled):
    assert publish_authority.study_awaits_authority() is True


def test_a_bundled_study_served_without_an_authority_is_published(served, bundled):
    served.write_text('{"database": {"host": "db.internal"}}', encoding="utf-8")

    assert publish_authority.study_awaits_authority() is True


def test_a_bundled_study_served_with_an_authority_is_left_alone(served, bundled):
    served.write_text(
        '{"database": {"database_certificate_authority": "-----BEGIN CERTIFICATE-----"}}',
        encoding="utf-8",
    )

    assert publish_authority.study_awaits_authority() is False


def test_a_study_on_a_named_database_is_left_alone(served, monkeypatch):
    """The authority there belongs to the researcher's server, and was asked for."""
    from shared_config import source_store

    monkeypatch.setattr(source_store, "read_source", _Source("db-123.example.cloud"))

    assert publish_authority.study_awaits_authority() is False
