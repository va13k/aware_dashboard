"""Tests for shared_config/dataflow.py and what it makes the Android config say.

A dataflow is several settings that have to agree, so these check the derived
config rather than the field on its own: whether the phone is handed database
coordinates, what address it is given, and whether the webservice channel is on.

The Android webservice case is tested for its *refusal* as much as its output. The
client can upload over HTTP; what it cannot yet do is be received --- the study URL
serves a QR page rather than a config, and the micro-server writes the iOS row shape
into a single schema. A config telling a phone to use that path would leave it
collecting and delivering nowhere, so the refusal exists to keep it from being
configured by accident, and its wording has to point at this side rather than the
client.
"""

import copy
import json
import pathlib

import pytest

from shared_config import dataflow
from shared_config.serializers import serialize_android_config

TEMPLATE = (
    pathlib.Path(__file__).resolve().parent.parent
    / "AWARE-Configurator"
    / "reactapp"
    / "public"
    / "study-config.json"
)

SETTINGS = {
    "android_database_host": "db.example.org",
    "protocol": "https",
    "public_host": "study.example.org",
    "public_port": 443,
}


@pytest.fixture
def source():
    example = (
        pathlib.Path(__file__).resolve().parent.parent / "source.example.json"
    )
    return json.loads(example.read_text())


def android_config(source, choice):
    """The config a phone would receive under this dataflow."""
    study = "https://study.example.org/1/KEY"
    config_url = "https://study.example.org/studies/files/studyConfig.json"
    return serialize_android_config(
        source,
        SETTINGS,
        TEMPLATE,
        "study-id",
        dataflow.webservice_server(choice, study_url=study, config_url=config_url),
    )


def setting(config, name):
    return next(
        (s["value"] for s in config["sensors"] if s.get("setting") == name), None
    )


def test_a_study_predating_the_field_reads_as_what_it_was_doing():
    """Android was writing to MySQL directly and iOS through the micro-server, so
    an absent field has to resolve that way rather than to a neutral value."""
    assert dataflow.declared({}, "android") == dataflow.DIRECT
    assert dataflow.declared({}, "ios") == dataflow.WEBSERVICE


def test_the_declared_choice_is_read_from_the_study(source):
    source["deployment"]["dataflow"] = {"android": "webservice", "ios": "webservice"}

    assert dataflow.declared(source, "android") == dataflow.WEBSERVICE


def test_an_unrecognisable_value_falls_back_rather_than_propagating(source):
    """A typo in the field must not reach the generated config as a dataflow
    nothing knows how to apply."""
    source["deployment"]["dataflow"] = {"android": "htpp", "ios": "webservice"}

    assert dataflow.declared(source, "android") == dataflow.DIRECT


def test_android_webservice_is_refused_and_says_why():
    reason = dataflow.unsupported_reason("android", dataflow.WEBSERVICE)

    assert reason is not None
    # The reason has to name the missing piece; "unsupported" alone sends a
    # researcher hunting for a setting that does not exist. The missing piece is
    # this side's -- the client can send -- so the reason must not blame it.
    assert "The server cannot yet receive" in reason
    assert "client can" in reason


def test_ios_direct_is_refused_and_says_why():
    reason = dataflow.unsupported_reason("ios", dataflow.DIRECT)

    assert reason is not None
    assert "no direct-database client" in reason


def test_the_supported_pair_is_accepted():
    assert dataflow.unsupported_reason("android", dataflow.DIRECT) is None
    assert dataflow.unsupported_reason("ios", dataflow.WEBSERVICE) is None


def test_the_default_study_validates(source):
    """The defaults have to be a coherent study, or every generation refuses."""
    assert dataflow.validate(source) == []


def test_validate_collects_every_problem_rather_than_the_first(source):
    source["deployment"]["dataflow"] = {"android": "webservice", "ios": "direct"}

    problems = dataflow.validate(source)

    assert len(problems) == 2


def test_a_direct_study_carries_the_database_coordinates(source):
    source["deployment"]["dataflow"] = {"android": "direct", "ios": "webservice"}

    config = android_config(source, dataflow.DIRECT)

    assert config["dataflow"] == dataflow.DIRECT
    assert config["database"]["database_name"] == "aware_android"
    assert setting(config, "status_webservice") is False


def test_a_webservice_study_carries_no_database_block_at_all(source):
    """Absent rather than blanked. The phone never contacts MySQL, and this config
    is served from a public path, so an address and an account would be a
    credential handed to every participant for no reason."""
    source["deployment"]["dataflow"] = {"android": "webservice", "ios": "webservice"}

    config = android_config(source, dataflow.WEBSERVICE)

    assert "database" not in config
    assert config["dataflow"] == dataflow.WEBSERVICE
    assert setting(config, "status_webservice") is True


def test_the_channel_follows_the_dataflow_over_a_stale_setting(source):
    """A study whose settings said one thing and whose dataflow said another is
    the half-configured state the single choice exists to prevent."""
    source["deployment"]["dataflow"] = {"android": "webservice", "ios": "webservice"}
    source["android"]["settings"]["status_webservice"] = False

    assert setting(android_config(source, dataflow.WEBSERVICE), "status_webservice")


def test_the_address_means_different_things_on_the_two_paths():
    """The same key is a config-download URL on one path and the ingest endpoint on
    the other, which is why setup and the Configurator had each been writing their
    own answer into it."""
    study = "https://study.example.org/1/KEY"
    config_url = "https://study.example.org/studies/files/studyConfig.json"

    assert dataflow.webservice_server(dataflow.DIRECT, study, config_url) == config_url
    assert dataflow.webservice_server(dataflow.WEBSERVICE, study, config_url) == study


def test_only_a_direct_phone_needs_credentials():
    assert dataflow.carries_database_credentials("android", dataflow.DIRECT)
    assert not dataflow.carries_database_credentials("android", dataflow.WEBSERVICE)
