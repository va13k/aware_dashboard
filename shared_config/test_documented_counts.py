"""Tests for the counts the documents state, against the code that decides them.

A document that says "seven jobs" where there are eight is wrong in the way that is
hardest to notice: the sentence still reads correctly, nothing fails, and the number
is only checkable by counting something in another file. Each claim below names the
phrase as it is written and the thing that decides it, so a change to either has to
be made in both.

The claims are listed rather than discovered. A number found by pattern would drag
in every "two answers" and "three ways" in the prose, none of which counts anything;
what belongs here is the handful that do.
"""

import pathlib
import re

import pytest
import yaml

PROJECT = pathlib.Path(__file__).resolve().parent.parent

UNITS = [
    "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def spelled(number: int) -> str:
    """A count as a document writes it, up to ninety-nine."""
    if number < 20:
        return UNITS[number]
    tens, units = divmod(number, 10)
    return TENS[tens] + (f"-{UNITS[units]}" if units else "")


#: Every count a claim could be stated as, so a stale one is found rather than missed.
WORDS = {n: spelled(n) for n in range(1, 100)}


def read(*parts: str) -> str:
    return (PROJECT.joinpath(*parts)).read_text(encoding="utf-8")


def workflow_jobs() -> int:
    """Jobs in the check workflow, the matrix counting as the one job it is."""
    workflow = yaml.safe_load(read(".github", "workflows", "check.yml"))
    return len(workflow["jobs"])


def compose_containers() -> int:
    """Containers the compose file declares, the setup profile's included."""
    compose = yaml.safe_load(read("docker-compose.yml"))
    return len(compose["services"])


def stack_table_rows() -> int:
    """Rows in the README's own table of what the stack comprises."""
    readme = read("README.md")
    table = readme.split("The full stack comprises", 1)[1].split("\n\n")
    rows = [line for line in table[1].splitlines() if line.startswith("|")]
    # The header and its rule are not services.
    return len(rows) - 2


def numbered_steps() -> int:
    """Steps the README numbers, from opening a terminal to a running study."""
    return len(re.findall(r"^### \d+\. ", read("README.md"), re.MULTILINE))


def wizard_steps() -> int:
    """Cards the setup form shows, each carrying one step title."""
    return read("setup", "setup.html").count('class="step-title"')


def wizard_awaited_services() -> int:
    """Containers the wizard page waits for before it redirects a browser."""
    server = read("setup", "server.py")
    names = set()
    for constant in (
        "_HEALTH_CHECKED",
        "_RUNNING_ONLY",
        "_BUNDLED_HEALTH_CHECKED",
        "_BUNDLED_RUNNING_ONLY",
    ):
        block = re.search(rf"^{constant} = frozenset\((.*?)\)\n", server, re.S | re.M)
        assert block, f"{constant} is not declared as a frozenset literal"
        names |= set(re.findall(r'"([^"]+)"', block.group(1)))
    return len(names)


def micro_server_tests() -> int:
    """Tests the micro-server declares, one `@Test` being one of them."""
    tests = PROJECT / "aware-micro-server" / "src" / "test" / "kotlin"
    files = sorted(tests.rglob("*.kt"))
    assert files, "no Kotlin test sources found"
    # None of these parametrise, so an annotation is a case. A parametrised test
    # added here would make this count low, and this is where that shows up.
    for path in files:
        source = path.read_text(encoding="utf-8")
        assert "ParameterizedTest" not in source, f"{path.name} parametrises"
    return sum(f.read_text(encoding="utf-8").count("@Test") for f in files)


#: (the file, the sentence with the number left out, what decides the number)
CLAIMS = [
    ("README.md", "{} CI jobs", workflow_jobs),
    ("docs/dev/checks.md", "{} jobs, run on every push", workflow_jobs),
    ("README.md", "{} services, running as", stack_table_rows),
    ("README.md", "running as {} containers", compose_containers),
    ("docs/dev/architecture.md", "{} containers, one public port", compose_containers),
    ("README.md", "{} numbered steps", numbered_steps),
    ("README.md", "The wizard has {} steps", wizard_steps),
    ("README.md", "Starts all {} services", wizard_awaited_services),
    (
        "aware-micro-server/README.md",
        "{} tests across five classes",
        micro_server_tests,
    ),
]


def states(text: str, claim: str) -> bool:
    """Whether the document makes this claim, the number being a word of its own.

    A plain substring finds "two tests" inside "thirty-two tests", which would
    report every compound count as a stale one.
    """
    return re.search(rf"(?<![\w-]){re.escape(claim)}", text, re.IGNORECASE) is not None


def claim_ids():
    return [f"{name}: {template}" for name, template, _ in CLAIMS]


@pytest.mark.parametrize("name,template,counter", CLAIMS, ids=claim_ids())
def test_the_document_states_the_count_the_code_decides(name, template, counter):
    text = read(*name.split("/"))
    actual = counter()
    assert actual in WORDS, f"{actual} is outside the range this spells"

    expected = template.format(WORDS[actual])
    assert states(text, expected), (
        f"{name} does not say {expected!r}, and {actual} is what the code decides"
    )

    for number, word in WORDS.items():
        if number == actual:
            continue
        stale = template.format(word)
        assert not states(text, stale), f"{name} says {stale!r}, and it is {actual}"
