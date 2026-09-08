"""Tests for the key a phone presents, against the routes that compare it.

The study key is the credential a participant's phone holds instead of a session:
it travels in the path of every request that reads a configuration, and nginx
compares it before serving one. So two things have to agree about what a key looks
like --- the generator that mints it and the patterns that match it --- and they
are written in different languages, in different files, by different hands.

They agree on letters, digits and the underscore. What separates them is the
hyphen: `secrets.token_urlsafe` draws from the URL-safe base64 alphabet, which
carries one, and `\\w` describes an alphabet that does not. A key holding a hyphen
is a phone answered 404 when it asks for its own configuration --- on the direct
dataflow, the file carrying the database account it opens --- and roughly one key
in six holds one.
"""

import pathlib
import re
import secrets
import string
import sys

PROJECT = pathlib.Path(__file__).resolve().parent.parent
NGINX = PROJECT / "nginx"
sys.path.insert(0, str(PROJECT / "setup"))

import deploy_config  # noqa: E402

#: What `secrets.token_urlsafe` emits, which is base64url without its padding.
URL_SAFE_ALPHABET = string.ascii_letters + string.digits + "-_"

#: Every path a study key travels in, as a template. The Android configuration, the
#: iOS study the micro-server answers for, and a study file read by key.
KEY_PATHS = (
    "/2/{key}",
    "/1/{key}",
    "/studies/files/{key}/studyConfig.json",
)

CONFIGS = ("http.conf", "https.conf")


def location_patterns(text: str) -> list[str]:
    """Every regex location in a config, spelled the way `re` spells one."""
    found = re.findall(r"^\s*location ~\*? (.+?) \{$", text, re.MULTILINE)
    return [re.sub(r"\(\?<", "(?P<", pattern) for pattern in found]


def test_the_study_key_is_drawn_from_the_url_safe_alphabet():
    """The premise the patterns are held to below."""
    env: dict[str, str] = {}
    produced = set()
    for _ in range(200):
        env["STUDY_KEY"] = ""
        deploy_config.ensure_study_key(env)
        produced |= set(env["STUDY_KEY"])

    assert produced <= set(URL_SAFE_ALPHABET)


def test_every_route_a_key_travels_in_accepts_that_whole_alphabet():
    key = URL_SAFE_ALPHABET

    for name in CONFIGS:
        patterns = location_patterns((NGINX / name).read_text(encoding="utf-8"))
        assert patterns, f"{name} declares no regex location"

        for template in KEY_PATHS:
            path = template.format(key=key)
            assert any(re.match(pattern, path) for pattern in patterns), (
                f"{name} matches no location for {path}, so a key holding any of "
                f"these characters is answered 404"
            )


def test_a_key_a_deployment_would_mint_reaches_its_own_configuration():
    """The same question asked of keys rather than of the alphabet behind them."""
    env: dict[str, str] = {}
    keys = []
    for _ in range(200):
        env["STUDY_KEY"] = ""
        deploy_config.ensure_study_key(env)
        keys.append(env["STUDY_KEY"])

    for name in CONFIGS:
        patterns = location_patterns((NGINX / name).read_text(encoding="utf-8"))
        for key in keys:
            path = f"/2/{key}"
            assert any(re.match(pattern, path) for pattern in patterns), (
                f"{name} answers 404 for the Android configuration at {path}"
            )
