"""Tests for the map in docs/, against the tree it claims to describe.

The map exists so a reader finds a file without searching for it, which it can
only do while every path it names is real. A renamed file leaves the note
reading perfectly and pointing nowhere, so the paths are checked rather than
trusted.
"""
import pathlib
import re

import pytest

PROJECT = pathlib.Path(__file__).resolve().parent.parent
DOCS = PROJECT / "docs"
INDEX = DOCS / "index.md"
MAP = DOCS / "map"

#: [text](target), the target's anchor dropped.
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def notes() -> list[pathlib.Path]:
    found = sorted(MAP.glob("*.md"))
    assert found, "docs/map holds no notes"
    return found


def note_ids() -> list[str]:
    return [p.name for p in notes()]


def links(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [
        href
        for href in LINK.findall(text)
        if not href.startswith(("http://", "https://", "mailto:", "#"))
    ]


@pytest.mark.parametrize("note", notes(), ids=note_ids())
def test_every_path_a_note_names_exists(note):
    for href in links(note):
        target = (note.parent / href.partition("#")[0]).resolve()
        assert target.exists(), f"{note.name} names {href}, which does not exist"


def test_every_path_the_index_names_exists():
    for href in links(INDEX):
        target = (INDEX.parent / href.partition("#")[0]).resolve()
        assert target.exists(), f"index.md names {href}, which does not exist"


@pytest.mark.parametrize("note", notes(), ids=note_ids())
def test_the_index_reaches_every_note(note):
    #: A note nothing links to is a note nobody finds.
    assert f"map/{note.name}" in INDEX.read_text(encoding="utf-8"), (
        f"docs/index.md does not link {note.name}"
    )
