"""Tests for the dataflow as a setup choice: validated at the wizard boundary, and
applied as one operation rather than a setting at a time.

Two guarantees are worth holding onto. A choice nothing recognises is refused where
the researcher gave it, not silently replaced by a default downstream --- a study
quietly collecting the wrong way is the failure that shows up weeks later in the
coverage grid. And a dataflow this deployment cannot honour stops the run before
anything is written, so there is no half-configured study to unpick.

The MySQL binding is the deployment's half of the choice. The published port exists
only so participant phones can open the database themselves, which is what the
direct path needs; every service in the compose file reaches MySQL over the compose
network, so on the webservice path the published address has no audience beyond
this host and is narrowed to loopback.
"""

import pathlib
import sys

import pytest

from shared_config import dataflow

SETUP = pathlib.Path(__file__).resolve().parent.parent / "setup"
sys.path.insert(0, str(SETUP))

import deploy_config  # noqa: E402
import write_request_env  # noqa: E402

from shared_config.serializers import build_android_micro_config  # noqa: E402


class TestProjectRoot:
    """write_request_env.project_root: where the dataflow vocabulary is imported from.

    The wizard runs the same file from two layouts. A checkout keeps it in the
    project's setup directory, so the root is one level up. The wizard container
    keeps it in a flat /wizard directory and mounts the project at /project, so
    the root is the mount. Finding the root by the package it contains lets one
    import serve both.
    """

    def test_a_checkout_resolves_to_the_directory_holding_shared_config(self):
        root = write_request_env.project_root()

        assert (root / "shared_config").is_dir()
        assert (root / "shared_config" / "dataflow.py").is_file()

    def test_the_container_mount_is_among_the_candidates(self):
        """The wizard image copies this file into /wizard and mounts /project."""
        candidates = [str(c) for c in write_request_env.PROJECT_CANDIDATES]

        assert "/project" in candidates

    def test_a_flat_layout_resolves_to_the_mounted_project(self, tmp_path):
        """The container's layout: this file's parent holds no package, and the
        project sits somewhere else entirely."""
        flat = tmp_path / "wizard"
        flat.mkdir()
        mounted = tmp_path / "project"
        (mounted / "shared_config").mkdir(parents=True)

        assert write_request_env.project_root([flat, mounted]) == mounted

    def test_the_checkout_is_preferred_when_both_layouts_are_present(self, tmp_path):
        checkout = tmp_path / "checkout"
        (checkout / "shared_config").mkdir(parents=True)
        mounted = tmp_path / "project"
        (mounted / "shared_config").mkdir(parents=True)

        assert write_request_env.project_root([checkout, mounted]) == checkout


class TestBoundaryValidation:
    """write_request_env.clean_dataflow: the wizard's answer, checked."""

    def test_the_supported_choice_is_accepted(self):
        assert write_request_env.clean_dataflow("direct", "") == dataflow.DIRECT

    def test_case_and_padding_do_not_change_the_answer(self):
        assert write_request_env.clean_dataflow("  DIRECT  ", "") == dataflow.DIRECT

    def test_an_absent_answer_falls_back_to_the_env_then_the_default(self):
        assert write_request_env.clean_dataflow(None, "direct") == dataflow.DIRECT
        assert write_request_env.clean_dataflow(None, "") == dataflow.DIRECT

    def test_an_unrecognised_answer_is_refused_rather_than_defaulted(self):
        """Silently defaulting would run the study the other way without saying so."""
        with pytest.raises(SystemExit) as refused:
            write_request_env.clean_dataflow("htpp", "")

        assert "must be one of" in str(refused.value)

    def test_a_choice_this_deployment_cannot_honour_is_refused_with_the_reason(
        self, monkeypatch
    ):
        """Against a narrowed matrix, so this keeps testing that the boundary
        refuses an unhonourable choice rather than which choices are honourable
        today."""
        monkeypatch.setitem(dataflow.SUPPORTED, "android", (dataflow.DIRECT,))

        with pytest.raises(SystemExit) as refused:
            write_request_env.clean_dataflow("webservice", "")

        assert "does not support" in str(refused.value)


class TestApplication:
    """deploy_config.apply_dataflow: one operation, or none."""

    def _source(self, android):
        return {"deployment": {"dataflow": {"android": android, "ios": "webservice"}}}

    def test_the_direct_path_leaves_mysql_reachable(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("PROTOCOL=http\n")
        monkeypatch.setattr(deploy_config, "ENV_PATH", env_file)

        assert deploy_config.apply_dataflow({}, self._source("direct")) == "0.0.0.0"
        assert "MYSQL_BIND_ADDRESS=0.0.0.0" in env_file.read_text()

    def test_an_unhonourable_dataflow_writes_nothing_at_all(self, tmp_path, monkeypatch):
        """Refused before the first write, so there is no study half-applied for two
        dataflows to unpick afterwards. Narrowed matrix, as above."""
        monkeypatch.setitem(dataflow.SUPPORTED, "android", (dataflow.DIRECT,))
        env_file = tmp_path / ".env"
        env_file.write_text("PROTOCOL=http\n")
        monkeypatch.setattr(deploy_config, "ENV_PATH", env_file)

        with pytest.raises(SystemExit):
            deploy_config.apply_dataflow({}, self._source("webservice"))

        assert "MYSQL_BIND_ADDRESS" not in env_file.read_text()

    def test_a_study_predating_the_field_is_treated_as_direct(self, tmp_path, monkeypatch):
        """Which is what such a study was already doing, so its binding must not
        change under it."""
        env_file = tmp_path / ".env"
        env_file.write_text("PROTOCOL=http\n")
        monkeypatch.setattr(deploy_config, "ENV_PATH", env_file)

        assert deploy_config.apply_dataflow({}, {}) == "0.0.0.0"


class TestAndroidJoinUrl:
    """dataflow.android_study_url: the address an Android phone is given.

    On the webservice path the client posts its data to the URL it joined with, so
    this URL decides which micro-server instance, and therefore which schema, an
    Android phone writes into. iOS holds study number 1 in this deployment, and
    Android's own number is what routes a request to the instance that writes the
    Android schema and runs the enrolment gate. Setup and the Configurator both call
    this, so a phone is given one address whichever regenerated the config.
    """

    def _url(self, android, base_url="http://host", study_key="KEY"):
        return dataflow.android_study_url(
            dataflow.declared(
                {"deployment": {"dataflow": {"android": android}}}, "android"
            ),
            base_url,
            study_key,
            "studyConfig.json",
        )

    def test_the_webservice_path_addresses_androids_own_study_number(self):
        assert self._url("webservice") == (
            f"http://host/{dataflow.ANDROID_STUDY_NUMBER}/KEY"
        )

    def test_the_study_number_is_androids_rather_than_ios(self):
        """A URL carrying iOS's number reaches the iOS instance, which stores a row
        in the iOS shape in the iOS schema and derives no Android enrolment window.
        """
        assert "/1/" not in self._url("webservice")

    def test_the_direct_path_addresses_the_published_config(self):
        """The client opens the database itself and reads this URL for config
        updates, which the deployment serves as a file."""
        assert self._url("direct") == "http://host/studies/files/studyConfig.json"

    def test_the_url_and_the_android_instance_name_one_study(self):
        """A phone is routed to the instance by study number, and the instance
        accepts the study number it was configured with, so the two agree.
        """
        source = {
            "database": {
                "android": {
                    "name": "aware_android",
                    "username": "participant",
                    "password": "secret",
                    "port": 3306,
                }
            },
            "study": {
                "title": "Study",
                "description": "",
                "active": True,
                "start_timestamp": 0,
            },
            "researcher": {
                "first_name": "First",
                "last_name": "Last",
                "contact": "researcher@example.com",
            },
        }
        settings = {
            "micro_database_host": "mysql",
            "external_server_host": "http://host",
            "public_port": 80,
        }
        micro = build_android_micro_config(
            source, settings, "KEY", dataflow.ANDROID_STUDY_NUMBER
        )

        assert self._url("webservice").endswith(
            f"/{micro['study']['study_number']}/KEY"
        )

class TestAndroidQrCode:
    """The join link the Android instance renders its QR code from.

    A client uploads to the address it joined with, so the QR and the published link
    have to be one string: a code encoding another spelling of the same study would
    route a phone's data to the instance that writes the other platform's schema.
    """

    def _micro(self, join_url):
        source = {
            "database": {
                "android": {
                    "name": "aware_android",
                    "username": "participant",
                    "password": "secret",
                    "port": 3306,
                }
            },
            "study": {
                "title": "Study",
                "description": "",
                "active": True,
                "start_timestamp": 0,
            },
            "researcher": {
                "first_name": "First",
                "last_name": "Last",
                "contact": "researcher@example.com",
            },
        }
        settings = {
            "micro_database_host": "mysql",
            "external_server_host": "http://host",
            "public_port": 80,
        }
        return build_android_micro_config(
            source, settings, "KEY", dataflow.ANDROID_STUDY_NUMBER, join_url=join_url
        )

    def test_the_config_carries_the_join_url_it_is_given(self):
        url = dataflow.android_study_url(
            dataflow.WEBSERVICE, "http://host", "KEY", "studyConfig.json"
        )

        assert self._micro(url)["study"]["join_url"] == url

    def test_the_join_url_matches_the_study_number_the_instance_serves(self):
        """The QR sends a phone to the instance that accepts its study number."""
        micro = self._micro(
            dataflow.android_study_url(
                dataflow.WEBSERVICE, "http://host", "KEY", "studyConfig.json"
            )
        )

        assert micro["study"]["join_url"].endswith(
            f"/{micro['study']['study_number']}/KEY"
        )

    def test_a_study_with_no_declared_link_renders_no_code(self):
        """An empty join_url is what the route answers 404 for, rather than encoding
        a guess at the address."""
        assert self._micro("")["study"]["join_url"] == ""

