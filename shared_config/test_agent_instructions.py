"""Tests for the instructions an agent reads before touching this repository.

Two files carry them, because two conventions exist for where an agent looks:
`CLAUDE.md` and `AGENTS.md`. A reader gets whichever its own tool reads, so the
two saying different things is the one failure that cannot be noticed from
inside either of them.
"""
import pathlib
import re

import pytest

PROJECT = pathlib.Path(__file__).resolve().parent.parent
INSTRUCTIONS = ("AGENTS.md", "CLAUDE.md")


def read(name: str) -> str:
    return (PROJECT / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", INSTRUCTIONS)
def test_the_instructions_are_where_an_agent_looks(name):
    assert (PROJECT / name).is_file(), f"{name} is missing"


def test_both_files_say_the_same_thing():
    first, second = (read(name) for name in INSTRUCTIONS)
    assert first == second, (
        f"{INSTRUCTIONS[0]} and {INSTRUCTIONS[1]} differ; copy one over the other"
    )


@pytest.mark.parametrize("name", INSTRUCTIONS)
def test_no_instruction_points_outside_the_repository(name):
    #: Every markdown link target, the anchor dropped.
    for href in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", read(name)):
        if href.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = PROJECT / href.partition("#")[0]
        assert target.exists(), f"{name} links to {href}, which does not exist"
