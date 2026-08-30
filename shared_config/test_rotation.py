"""Tests for replacing a credential a participant's phone already holds.

Every secret this deployment needs is generated on the first deploy that needs one
and kept afterwards, which is what lets a redeploy leave a running study running.
The same rule leaves a deployment no way to replace a credential that has been
exposed, and two of them are published to every phone in the study: the study key
is the address a phone uploads to, and the broker password is what it connects
with. `ROTATE` is how a deploy is asked for a new one.

Two guarantees are worth holding onto. The request is acted on once, because a key
that moves on every deploy is a study that collects nothing. And a name nothing
recognises stops the run rather than passing quietly, because a rotation that was
reported and did not happen leaves somebody believing an exposed credential is
gone.
"""

import pathlib
import sys

import pytest

SETUP = pathlib.Path(__file__).resolve().parent.parent / "setup"
sys.path.insert(0, str(SETUP))

import deploy_config  # noqa: E402


class TestRotationRequest:
    """deploy_config.apply_rotation_request: what a deploy was asked to mint again."""

    def test_no_request_leaves_every_credential_alone(self):
        env = {"STUDY_KEY": "kept", "MQTT_PARTICIPANT_PASSWORD": "kept too"}

        assert deploy_config.apply_rotation_request(env) == []
        assert env["STUDY_KEY"] == "kept"
        assert env["MQTT_PARTICIPANT_PASSWORD"] == "kept too"

    def test_the_study_key_is_emptied_for_its_generator(self):
        """Emptied rather than replaced here: one generator owns each value, and a
        blank is the deployment-has-none-yet path it already takes."""
        env = {"STUDY_KEY": "9qFNcpdTs_CN", "ROTATE": "study-key"}

        assert deploy_config.apply_rotation_request(env) == ["study-key"]
        assert env["STUDY_KEY"] == ""

    def test_both_broker_accounts_are_emptied_together(self):
        env = {
            "MQTT_PARTICIPANT_PASSWORD": "published",
            "MQTT_PUBLISHER_PASSWORD": "held by the api",
            "ROTATE": "broker",
        }

        deploy_config.apply_rotation_request(env)

        assert env["MQTT_PARTICIPANT_PASSWORD"] == ""
        assert env["MQTT_PUBLISHER_PASSWORD"] == ""

    def test_a_list_is_read_however_it_is_spelled(self):
        env = {"ROTATE": "study-key, broker"}

        assert deploy_config.apply_rotation_request(env) == ["broker", "study-key"]

    def test_the_request_is_cleared_once_it_has_been_read(self):
        """Left in place it would mint a new key on every subsequent deploy, and a
        study whose address moves each time it is redeployed collects nothing."""
        env = {"STUDY_KEY": "old", "ROTATE": "study-key"}

        deploy_config.apply_rotation_request(env)

        assert env["ROTATE"] == ""

    def test_a_name_nothing_mints_stops_the_run(self):
        with pytest.raises(SystemExit) as refused:
            deploy_config.apply_rotation_request({"ROTATE": "studykey"})

        assert "studykey" in str(refused.value)
        assert "study-key" in str(refused.value)

    def test_an_emptied_credential_is_minted_again(self):
        """The generators are what produce the new value, so a rotation ends with a
        credential this deployment has never served."""
        env = {
            "STUDY_KEY": "9qFNcpdTs_CN",
            "MQTT_PARTICIPANT_PASSWORD": "published",
            "MQTT_PUBLISHER_PASSWORD": "held by the api",
            "ROTATE": "study-key broker",
        }

        deploy_config.apply_rotation_request(env)
        deploy_config.ensure_study_key(env)
        deploy_config.ensure_broker_passwords(env)

        assert env["STUDY_KEY"] not in ("", "9qFNcpdTs_CN")
        assert env["MQTT_PARTICIPANT_PASSWORD"] not in ("", "published")
        assert env["MQTT_PUBLISHER_PASSWORD"] not in ("", "held by the api")

    def test_two_deployments_are_not_handed_the_same_key(self):
        """The point of minting rather than declaring: what a study answers to is
        this deployment's, so reading one study's config says nothing about
        another's."""
        keys = set()
        for _ in range(20):
            env = {"STUDY_KEY": "", "MQTT_PARTICIPANT_PASSWORD": ""}
            deploy_config.ensure_study_key(env)
            deploy_config.ensure_broker_passwords(env)
            keys.add((env["STUDY_KEY"], env["MQTT_PARTICIPANT_PASSWORD"]))

        assert len(keys) == 20
