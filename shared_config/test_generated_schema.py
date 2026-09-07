"""Tests for the schema MySQL applies, held to the sources it is built from.

`db/init_all.sql` is the whole schema in one file, because `--init-file` is read
server-side and cannot `SOURCE` another. It is also a build product, and the two
facts together are what make it worth a test: a hand edit lands in the deployed
schema and in nothing else, so the file and its sources say different things about
the same database until somebody regenerates. That is how `bluetooth` came to lose
rows to a column the client declared and the server did not have.

`db/build_init_all.py --check` is the guard, and this runs it under the suite so a
regeneration is asked for by a test rather than remembered.
"""

import pathlib
import sys

DB = pathlib.Path(__file__).resolve().parent.parent / "db"
sys.path.insert(0, str(DB))

import build_init_all  # noqa: E402


def test_the_generated_schema_matches_its_sources():
    """What `db/build_init_all.py --check` asks, asked here as well."""
    assert build_init_all.GENERATED.read_text(encoding="utf-8") == build_init_all.render(), (
        "db/init_all.sql is stale - run db/build_init_all.py"
    )


def test_every_script_the_schema_names_is_there():
    """A comment that points at a neighbouring script points at one that exists.

    The bootstrap hands its seeded passwords to a script that runs after it, and
    names it where it explains the seed. A name that has moved is a reader sent to
    a file that is not there.
    """
    for source in sorted(DB.glob("*.sql")):
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.lstrip().startswith("--"):
                continue
            for word in line.split():
                if word.endswith(".sh"):
                    assert (DB / word).is_file(), f"{source.name} names {word}, which is absent"
