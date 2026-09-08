"""Tests for the researcher's password as nginx reads it back.

The login guarding the dashboard, the Configurator and every study file is one line
in `nginx/auth/.htpasswd`, and nginx accepts Apache's `$apr1$` form there. The hash
used to be produced by calling `openssl passwd`, which is a program Windows does not
carry, so a deployment there stopped on it before writing anything.

Computed in Python instead, and held to `openssl`'s own answers: the values below
came from `openssl passwd -apr1 -salt <salt> <password>`. A hash nginx cannot verify
is a researcher locked out of their own study, so the algorithm is checked against
the tool rather than against itself.
"""

import pathlib
import re
import shutil
import subprocess
import sys

import pytest

SETUP = pathlib.Path(__file__).resolve().parent.parent / "setup"
sys.path.insert(0, str(SETUP))

import deploy_config  # noqa: E402

#: (password, salt, what `openssl passwd -apr1` answers)
OPENSSL_ANSWERS = [
    ("researcher", "abcdefgh", "$apr1$abcdefgh$HfZwSxrPjrUjUM63BDtfr0"),
    ("s3cret-pass", "Xy9.Zq2A", "$apr1$Xy9.Zq2A$l8Hb9Yba1CRu9kCJl1Bcr/"),
    ("", "00000000", "$apr1$00000000$6RcJ2QejwQuo6wYyqYPMQ1"),
    ("x" * 40, "01234567", "$apr1$01234567$JZbLcAWyfxmcrIr3vsjTp0"),
]


@pytest.mark.parametrize("password,salt,expected", OPENSSL_ANSWERS)
def test_the_hash_is_the_one_openssl_produces(password, salt, expected):
    assert deploy_config.apr1_hash(password, salt) == expected


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is not installed here")
@pytest.mark.parametrize("password", ["researcher", "a", "пароль", "sp ace", "x" * 72])
def test_openssl_still_agrees_where_it_is_installed(password):
    """The oracle, asked again on a machine that has it."""
    salt = "Sa1tSa1t"
    answered = subprocess.run(
        ["openssl", "passwd", "-apr1", "-salt", salt, password],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert deploy_config.apr1_hash(password, salt) == answered


def test_a_hash_carries_its_own_salt():
    hashed = deploy_config.apr1_hash("researcher")

    assert re.fullmatch(r"\$apr1\$[./0-9A-Za-z]{8}\$[./0-9A-Za-z]{22}", hashed), hashed


def test_two_hashes_of_one_password_differ():
    """Each carries a salt of its own, so the file never states that two match."""
    assert deploy_config.apr1_hash("researcher") != deploy_config.apr1_hash("researcher")


def test_the_salt_is_drawn_from_the_alphabet_the_form_allows():
    produced = set()
    for _ in range(200):
        produced |= set(deploy_config.apr1_hash("researcher").split("$")[2])

    assert produced <= set(deploy_config.APR1_ALPHABET)


def test_the_file_holds_the_username_and_the_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_config, "HTPASSWD_PATH", tmp_path / ".htpasswd")

    deploy_config.generate_htpasswd("researcher", "s3cret-pass")

    line = (tmp_path / ".htpasswd").read_text(encoding="utf-8")
    username, _, hashed = line.strip().partition(":")
    assert username == "researcher"
    assert hashed.startswith("$apr1$")
