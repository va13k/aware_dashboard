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

import json
import pathlib
import sys

import pytest

from shared_config import database, dataflow, placement

SETUP = pathlib.Path(__file__).resolve().parent.parent / "setup"
sys.path.insert(0, str(SETUP))

import deploy_config  # noqa: E402
import write_request_env  # noqa: E402

from shared_config import serializers  # noqa: E402
from shared_config.serializers import (  # noqa: E402
    build_android_micro_config,
    serialize_android_config,
)


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
        assert self._url("direct") == "http://host/studies/files/KEY/studyConfig.json"

    def test_both_paths_carry_the_key_the_deployment_answers_to(self):
        """The config a direct phone downloads carries the account it opens the
        database with, so the address it is given holds the study's key just as the
        webservice one does."""
        for android in ("direct", "webservice"):
            assert "/KEY" in self._url(android)

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


class TestWhichAccountTheServerWritesWith:
    """build_android_micro_config: the credential the Android instance authenticates
    with.

    The server performs every write on the webservice path, so ingest is the server's
    connection rather than a participant's. Its account is granted what ingest does
    --- inserts, the enrolment registry it reads to decide which writes to keep, the
    refusal counters, the device-metadata row it fills in --- and the participant
    account is left to the path phones write on, where a phone holds the published
    credential and reads nothing back.
    """

    SOURCE = {
        "database": {
            "android": {
                "name": "aware_android",
                "username": "aware_android_participant",
                "password": "phone-pw",
                "server_username": "aware_android_server",
                "server_password": "server-pw",
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
    SETTINGS = {
        "micro_database_host": "mysql",
        "external_server_host": "http://host",
        "public_port": 80,
    }

    def _server(self, source=None):
        import copy

        return build_android_micro_config(
            copy.deepcopy(source or self.SOURCE),
            dict(self.SETTINGS),
            "KEY",
            dataflow.ANDROID_STUDY_NUMBER,
        )["server"]

    def test_the_instance_authenticates_as_the_server_account(self):
        server = self._server()

        assert server["database_user"] == "aware_android_server"
        assert server["database_pwd"] == "server-pw"

    def test_the_participant_credential_is_not_in_the_instances_configuration(self):
        """It belongs to the path phones open the database on, and this file is the
        server's."""
        server = self._server()

        assert "aware_android_participant" not in server.values()
        assert "phone-pw" not in server.values()

    def test_a_declared_dataflow_does_not_change_the_account(self):
        """The instance is configured on either path, and it is the same server."""
        import copy

        direct = copy.deepcopy(self.SOURCE)
        direct["deployment"] = {"dataflow": {"android": "direct"}}

        assert self._server(direct)["database_user"] == self._server()["database_user"]

    def test_the_gate_is_on_for_the_account_granted_to_read_the_registry(self):
        """The enrolment read is this account's, so the two travel together."""
        assert self._server()["require_enrolment"] is True


class TestTheCredentialsADeploySettles:
    """deploy_config: two Android accounts, two secrets, neither reaching the other's
    reader.

    The participant password is embedded in the study config every phone downloads,
    and the server's account can read the enrolment registry and update device
    metadata that a phone's cannot. Sharing one secret would hand every participant
    the wider account, so each account carries its own -- and each is seeded whichever
    dataflow the study runs, since the instance is configured either way.
    """

    def _seed(self, monkeypatch, env, requested=""):
        stored = {}
        template = json.loads(
            (pathlib.Path(__file__).resolve().parent.parent / "source.example.json")
            .read_text(encoding="utf-8")
        )

        def update_source(mutate):
            stored.clear()
            stored.update(mutate(template))
            return stored

        monkeypatch.setattr(deploy_config, "update_source", update_source)
        monkeypatch.setattr(deploy_config, "requested_dataflow", lambda: requested)
        return deploy_config.seed_source_secrets(env)

    def _env(self):
        env = {"STUDY_ID": "study-1"}
        deploy_config.ensure_participant_password(env)
        deploy_config.ensure_server_password(env)
        return env

    def test_each_account_is_given_its_own_generated_password(self, monkeypatch):
        env = self._env()

        assert env["PARTICIPANT_DB_PASSWORD"] != env["ANDROID_SERVER_DB_PASSWORD"]

    def test_a_password_already_on_record_is_kept(self, monkeypatch):
        """A change the Configurator made survives the next deploy."""
        env = {"ANDROID_SERVER_DB_PASSWORD": "chosen-by-the-researcher"}
        deploy_config.ensure_server_password(env)

        assert env["ANDROID_SERVER_DB_PASSWORD"] == "chosen-by-the-researcher"

    def test_both_credentials_reach_the_study_model(self, monkeypatch):
        env = self._env()
        android = self._seed(monkeypatch, env)["database"]["android"]

        assert android["password"] == env["PARTICIPANT_DB_PASSWORD"]
        assert android["server_password"] == env["ANDROID_SERVER_DB_PASSWORD"]

    def test_the_server_account_is_named_on_a_study_that_carried_none(
        self, monkeypatch
    ):
        env = self._env()
        stored = {}

        def update_source(mutate):
            stored.update(mutate({"database": {"android": {}}}))
            return stored

        monkeypatch.setattr(deploy_config, "update_source", update_source)
        monkeypatch.setattr(deploy_config, "requested_dataflow", lambda: "")
        seeded = deploy_config.seed_source_secrets(env)

        assert seeded["database"]["android"]["server_username"] == (
            database.ANDROID_SERVER_USER
        )

    def test_the_participant_password_stays_out_of_the_servers_configuration(
        self, monkeypatch
    ):
        env = self._env()
        source = self._seed(monkeypatch, env, requested="webservice")
        micro = build_android_micro_config(
            source,
            {
                "micro_database_host": "mysql",
                "external_server_host": "http://host",
                "public_port": 80,
            },
            "KEY",
            dataflow.ANDROID_STUDY_NUMBER,
        )

        assert micro["server"]["database_pwd"] == env["ANDROID_SERVER_DB_PASSWORD"]
        assert env["PARTICIPANT_DB_PASSWORD"] not in json.dumps(micro)

    def test_the_servers_password_is_never_published_to_phones(self, monkeypatch):
        """The direct path publishes a config carrying a credential; it is the
        participants' one, and the server's belongs to nothing a phone downloads."""
        env = self._env()
        source = self._seed(monkeypatch, env, requested="direct")
        template = (
            pathlib.Path(__file__).resolve().parent.parent
            / "AWARE-Configurator"
            / "reactapp"
            / "public"
            / "study-config.json"
        )
        published = serialize_android_config(
            source,
            {
                "android_database_host": "example.org",
                "micro_database_host": "mysql",
                "external_server_host": "http://host",
                "public_port": 80,
            },
            template,
        )

        assert published["database"]["database_username"] == (
            database.ANDROID_PARTICIPANT_USER
        )
        assert env["ANDROID_SERVER_DB_PASSWORD"] not in json.dumps(published)


class TestWhoDeclaresTheDataflow:
    """deploy_config.seed_source_secrets: which answer a deploy honours.

    Two writers reach this: the setup wizard, which asks the question, and the
    Configurator, which writes the study model. `.env` keeps the last value the
    wizard wrote, so treating it as the answer means a deploy nobody asked the
    question in reverts whatever the Configurator declared -- and reverting the
    dataflow on a running study changes the address phones joined with, which
    every enrolled participant has to act on.

    So the rule is: an answer given in this run wins, the study model stands
    otherwise, and `.env` seeds only a study that has never carried a declaration.
    """

    def _seed(self, monkeypatch, tmp_path, env, source, requested=None):
        """Run the seeding against a throwaway source.json, returning what it holds."""
        stored = dict(source)

        def update_source(mutate):
            stored.clear()
            stored.update(mutate(dict(source)))
            return stored

        monkeypatch.setattr(deploy_config, "update_source", update_source)
        monkeypatch.setattr(
            deploy_config, "requested_dataflow", lambda: requested or ""
        )
        merged = {
            "PARTICIPANT_DB_PASSWORD": "kept",
            "ANDROID_SERVER_DB_PASSWORD": "kept-server",
            "STUDY_ID": "study-1",
            **env,
        }
        deploy_config.seed_source_secrets(merged)
        return dataflow.declared(stored, "android")

    def test_an_answer_given_in_this_run_wins(self, monkeypatch, tmp_path):
        """The researcher chose it in the wizard just now."""
        declared = self._seed(
            monkeypatch,
            tmp_path,
            {"ANDROID_DATAFLOW": "direct"},
            {"deployment": {"dataflow": {"android": "webservice"}}},
            requested="direct",
        )

        assert declared == dataflow.DIRECT

    def test_a_stale_env_does_not_revert_the_study(self, monkeypatch, tmp_path):
        """The case that reverts a running study: `.env` holds the last wizard
        answer, and a deploy with no question asked must leave the study alone."""
        declared = self._seed(
            monkeypatch,
            tmp_path,
            {"ANDROID_DATAFLOW": "direct"},
            {"deployment": {"dataflow": {"android": "webservice"}}},
        )

        assert declared == dataflow.WEBSERVICE

    def test_env_seeds_a_study_with_no_declaration(self, monkeypatch, tmp_path):
        """First deploy: the study model carries nothing, so the wizard's answer
        in `.env` is the only one there is."""
        declared = self._seed(
            monkeypatch, tmp_path, {"ANDROID_DATAFLOW": "webservice"}, {}
        )

        assert declared == dataflow.WEBSERVICE

    def test_a_study_with_neither_reads_as_the_default(self, monkeypatch, tmp_path):
        assert self._seed(monkeypatch, tmp_path, {}, {}) == dataflow.DEFAULTS["android"]

    def test_ios_is_declared_alongside_android(self, monkeypatch, tmp_path):
        stored = {}

        def update_source(mutate):
            stored.update(mutate({"deployment": {"dataflow": {"android": "webservice"}}}))
            return stored

        monkeypatch.setattr(deploy_config, "update_source", update_source)
        monkeypatch.setattr(deploy_config, "requested_dataflow", lambda: "")
        deploy_config.seed_source_secrets(
            {
                "PARTICIPANT_DB_PASSWORD": "kept",
                "ANDROID_SERVER_DB_PASSWORD": "kept-server",
                "STUDY_ID": "study-1",
            }
        )

        assert dataflow.declared(stored, "ios") == dataflow.WEBSERVICE


class TestEnvMirrorsTheDeclaration:
    """apply_dataflow writes the resolved dataflow back to `.env`.

    The setup wizard fills its form from `.env`. A mirror is what lets it open on
    the dataflow the study is running instead of on the form's own default, which
    is what makes reopening the wizard safe.
    """

    def test_the_resolved_dataflow_is_written_back(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("PROTOCOL=http\nANDROID_DATAFLOW=direct\n")
        monkeypatch.setattr(deploy_config, "ENV_PATH", env_file)

        deploy_config.apply_dataflow(
            {}, {"deployment": {"dataflow": {"android": "webservice", "ios": "webservice"}}}
        )

        assert "ANDROID_DATAFLOW=webservice" in env_file.read_text()
        assert "ANDROID_DATAFLOW=direct" not in env_file.read_text()


class TestTheDeployIsChecked:
    """deploy_config.check_dataflow_applied: the artefacts, read back.

    A study half-configured for two dataflows starts, serves and looks deployed.
    Every disagreement here is one a researcher would otherwise find by a phone
    delivering nothing.
    """

    def _webservice(self):
        return {"deployment": {"dataflow": {"android": "webservice", "ios": "webservice"}}}

    def _publish(self, monkeypatch, tmp_path, config, join_url):
        study = tmp_path / "studyConfig.json"
        study.write_text(json.dumps(config), encoding="utf-8")
        monkeypatch.setattr(deploy_config, "STUDY_CONFIG_PATH", study)
        urls = tmp_path / "deployment-urls.json"
        urls.write_text(json.dumps({"android_join_url": join_url}), encoding="utf-8")
        monkeypatch.setattr(deploy_config, "PROJECT", tmp_path)

    def test_a_matching_deployment_passes(self, tmp_path, monkeypatch):
        self._publish(monkeypatch, tmp_path, {"sensors": {}}, "http://host/2/KEY")

        deploy_config.check_dataflow_applied(
            self._webservice(), "127.0.0.1", "http://host/2/KEY"
        )

    def test_an_open_binding_on_the_webservice_path_is_refused(self, tmp_path, monkeypatch):
        """The failure that publishes MySQL to every network the host is on."""
        self._publish(monkeypatch, tmp_path, {"sensors": {}}, "http://host/2/KEY")

        with pytest.raises(SystemExit) as refused:
            deploy_config.check_dataflow_applied(
                self._webservice(), "0.0.0.0", "http://host/2/KEY"
            )

        assert "0.0.0.0" in str(refused.value)

    def test_a_published_credential_on_the_webservice_path_is_refused(
        self, tmp_path, monkeypatch
    ):
        """The config is served from a public path, so this hands every participant
        a credential for a database they never contact."""
        self._publish(
            monkeypatch, tmp_path, {"database": {"database_host": "db"}}, "http://host/2/KEY"
        )

        with pytest.raises(SystemExit) as refused:
            deploy_config.check_dataflow_applied(
                self._webservice(), "127.0.0.1", "http://host/2/KEY"
            )

        assert "database coordinates" in str(refused.value)

    def test_a_join_url_from_the_other_dataflow_is_refused(self, tmp_path, monkeypatch):
        """Exactly the drift a phone meets as a join that delivers nowhere."""
        self._publish(
            monkeypatch,
            tmp_path,
            {"sensors": {}},
            "http://host/studies/files/studyConfig.json",
        )

        with pytest.raises(SystemExit) as refused:
            deploy_config.check_dataflow_applied(
                self._webservice(), "127.0.0.1", "http://host/2/KEY"
            )

        assert "join URL" in str(refused.value)

    def test_the_direct_path_is_checked_by_its_own_rules(self, tmp_path, monkeypatch):
        direct_url = "http://host/studies/files/studyConfig.json"
        self._publish(monkeypatch, tmp_path, {"database": {"database_host": "db"}}, direct_url)

        deploy_config.check_dataflow_applied(
            {"deployment": {"dataflow": {"android": "direct", "ios": "webservice"}}},
            "0.0.0.0",
            direct_url,
        )


class TestTheServersOwnTlsSetting:
    """serializers.database_ssl_mode: the client asks for what the account was granted.

    One answer read from two ends. A client asking for less than the account requires
    is refused by the server; a client asking for more than the server offers cannot
    connect at all. Both come from the study's one declaration, and the placement
    decides whether that declaration is the researcher's to make.
    """

    #: The values MySQLVerticle.setDatabaseSslMode maps to an encrypting client.
    ENCRYPTING = {"prefer", "preferred", "require", "required"}

    def _databases(self, host="db.internal", require=None):
        databases = {
            "host": host,
            "android": {
                "name": "aware_android",
                "username": "aware_android_participant",
                "password": "secret",
                "port": 3306,
            },
        }
        if require is not None:
            databases["tls"] = {"require": require}
        return databases

    def _micro(self, host="db.internal", require=None):
        source = {
            "database": self._databases(host, require),
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
        return build_android_micro_config(
            source,
            {
                "micro_database_host": "mysql",
                "external_server_host": "http://host",
                "public_port": 80,
                "public_host": "h",
                "protocol": "http",
            },
            "k",
            2,
            join_url="http://h/2/k",
        )

    def test_a_database_this_deployment_runs_always_encrypts(self):
        assert serializers.database_ssl_mode({}) == "required"

    @pytest.mark.parametrize("stated", [True, False, None])
    def test_a_bundled_study_cannot_declare_its_way_out_of_it(self, stated):
        # Both ends are this deployment's and every account it creates requires an
        # encrypted session, so a client talked into asking for less would simply be
        # refused by the server beside it.
        assert serializers.database_ssl_mode(self._databases(require=stated)) == "required"

    def test_a_named_database_encrypts_unless_the_study_says_otherwise(self):
        # Silence has meant TLS since every account was created requiring it, so a
        # study written before the setting arrived keeps the connection it has.
        assert serializers.database_ssl_mode(self._databases("db.example.edu")) == "required"

    def test_a_named_database_that_cannot_encrypt_is_told_so(self):
        # Asking for TLS from a server that does not offer it is a client that never
        # connects, which collects exactly as much as no configuration at all.
        assert (
            serializers.database_ssl_mode(self._databases("db.example.edu", False))
            == "disabled"
        )

    @pytest.mark.parametrize("stated", [True, None])
    def test_the_micro_server_is_configured_to_encrypt(self, stated):
        mode = self._micro("db.example.edu", stated)["server"]["database_ssl_mode"]
        assert mode in self.ENCRYPTING
        assert mode == "required"

    def test_the_micro_server_follows_a_study_that_declared_plaintext(self):
        mode = self._micro("db.example.edu", False)["server"]["database_ssl_mode"]
        assert mode not in self.ENCRYPTING


class TestTheDatabaseCertificateAuthority:
    """The one thing that lets a phone tell which server answered.

    Encryption is unconditional and closes reading the traffic. It cannot close
    impersonation, because nothing in an encrypted connection says who is on the
    other end. The client has always been able to check --- it builds a trust store
    from `database_certificate_authority` and verifies against it --- and the study
    simply never published one.
    """

    def _config(self, ca=None, tls=None):
        entry = {
            "name": "aware_android",
            "username": "aware_android_participant",
            "password": "phone-pw",
            "port": 3306,
            "host": "db.example.edu",
        }
        databases = {"host": "db.example.edu", "android": entry}
        if ca is not None:
            databases["tls"] = {"ca_certificate": ca}
        if tls is not None:
            databases.setdefault("tls", {})["require"] = tls
        source = {
            "database": databases,
            "deployment": {"dataflow": {"android": dataflow.DIRECT}},
            "study": {"title": "S", "description": "", "active": True, "start_timestamp": 0},
            "researcher": {"first_name": "F", "last_name": "L", "contact": "r@example.com"},
            "android": {"settings": {}, "sensors": {}},
            "shared": {"sensors": {}, "esms": {"questions": [], "schedules": []}},
        }
        return serialize_android_config(
            source,
            {
                "public_host": "h",
                "protocol": "http",
                "public_port": 80,
                "android_database_host": "db.example.edu",
                "micro_database_host": "mysql",
                "external_server_host": "http://h",
            },
            pathlib.Path("shared_config/android_template.json"),
            "study-id",
            "http://h/2/k",
        )

    def _database_block(self, config):
        return config.get("database") or {}

    def test_the_key_is_the_clients_own(self):
        client = (
            pathlib.Path(__file__).resolve().parent.parent.parent
            / "aware-client-main/aware-core/src/main/java/com/aware/Aware_Preferences.java"
        )
        if not client.exists():
            pytest.skip("the Android client is not checked out beside this project")
        # Read from the client rather than restated: a key it does not read is an
        # authority the phone never learns about, and a connection it cannot verify.
        assert f'"{serializers.DB_CA_KEY}"' in client.read_text(encoding="utf-8")

    def test_an_authority_reaches_the_phone(self):
        block = self._database_block(self._config("-----BEGIN CERTIFICATE-----\nabc\n"))
        assert "BEGIN CERTIFICATE" in block[serializers.DB_CA_KEY]

    def test_a_study_publishing_none_still_says_so_explicitly(self):
        # An empty string is what the client reads as "no authority, encrypt without
        # verifying". Omitting the key entirely would read the same, and being
        # explicit is what makes the absence visible in a config somebody inspects.
        block = self._database_block(self._config())
        assert block[serializers.DB_CA_KEY] == ""

    def test_a_phone_is_told_to_encrypt_unless_the_study_declared_otherwise(self):
        assert self._database_block(self._config())["require_ssl"] is True

    def test_a_phone_opening_a_server_that_cannot_encrypt_is_told_that_too(self):
        # A client asking for TLS from a database that does not offer it never
        # connects, so it would keep every batch and deliver none.
        block = self._database_block(self._config(tls=False))
        assert block["require_ssl"] is False
        # And there is nothing to verify on a connection nobody encrypts, so no
        # authority is published for one.
        assert block[serializers.DB_CA_KEY] == ""


class TestPublishingTheDatabaseAuthority:
    """deploy_config: what a phone verifies the database against, and what stops it.

    The client treats an authority it cannot parse as a database it cannot reach: it
    keeps its data and stops uploading rather than falling back to an unverified
    connection. That is the right behaviour and it makes a malformed certificate a
    study-wide outage, so nothing unreadable is allowed to reach a config.
    """

    #: A real certificate, as `docker exec` hands one over -- with the trailing NUL
    #: byte it appends, which is exactly the wrapper that would reach a phone.
    REAL = (
        "-----BEGIN CERTIFICATE-----\n"
        "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA\n"
        "-----END CERTIFICATE-----\n\x00"
    )

    def test_a_certificate_survives_what_it_arrived_wrapped_in(self):
        cleaned = deploy_config.read_certificate(self.REAL)
        assert cleaned.startswith("-----BEGIN CERTIFICATE-----")
        # The NUL would travel into the study config and be the unreadable authority
        # that stops every phone.
        assert "\x00" not in cleaned

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "just some text",
            "-----BEGIN CERTIFICATE-----\nnot base64 at all!!\n-----END CERTIFICATE-----",
            "-----BEGIN CERTIFICATE-----\nMIIBIjANBgkqhkiG9w0",
        ],
    )
    def test_nothing_unreadable_passes(self, bad):
        assert not deploy_config.valid_certificate(bad)

    def test_a_study_supplying_an_unreadable_authority_is_refused(self):
        # Refused at deploy rather than published: the alternative is every phone in
        # the study stopping at once, with nothing on the server saying why.
        source = {
            "database": {"host": "db.example.edu", "android": {"ca_certificate": "broken"}}
        }
        with pytest.raises(SystemExit):
            deploy_config.ensure_database_authority(source)

    def test_a_researchers_own_authority_is_left_alone(self):
        # On the placement it was given for. The wizard asks for one only about a
        # database this deployment does not administer, so that is the only
        # placement where a supplied authority describes the server in front of it.
        source = {
            "database": {"host": "db.example.edu", "android": {"ca_certificate": self.REAL}}
        }
        assert deploy_config.ensure_database_authority(source) == "supplied"

    def test_a_named_database_gets_none_of_ours(self):
        # Its authority is the researcher's to provide; this deployment has no file
        # to read and inventing one would verify nothing.
        source = {"database": {"host": "db.example.edu", "android": {}}}
        assert deploy_config.ensure_database_authority(source) == "none"


class TestWhatTheWizardMayAskOfTheConnection:
    """write_request_env.clean_tls: the researcher's answer, and where it is allowed.

    Encryption is a question only for a database this deployment does not
    administer. Asking it about the bundled one would offer a way to make a working
    study less safe for nothing in return, so an answer arriving for that placement
    is a form field nobody was shown rather than a decision to apply.
    """

    REAL = (
        "-----BEGIN CERTIFICATE-----\n"
        "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA\n"
        "-----END CERTIFICATE-----\n"
    )

    def test_a_bundled_database_is_encrypted_whatever_arrives(self):
        assert write_request_env.clean_tls(placement.BUNDLED, "0", self.REAL) == (
            True,
            "",
        )

    def test_a_named_database_defaults_to_encrypted(self):
        assert write_request_env.clean_tls(placement.EXTERNAL, None, "") == (True, "")

    @pytest.mark.parametrize("answer", ["0", "false", "no", "off"])
    def test_a_named_database_can_say_it_cannot_encrypt(self, answer):
        assert write_request_env.clean_tls(placement.EXTERNAL, answer, "") == (
            False,
            "",
        )

    def test_an_authority_is_kept_only_for_a_connection_that_verifies(self):
        # Nothing checks a certificate on a connection nobody encrypts, and storing
        # one would be a promise every interface then has to un-make.
        assert write_request_env.clean_tls(placement.EXTERNAL, "0", self.REAL) == (
            False,
            "",
        )

    def test_an_authority_survives_what_it_arrived_wrapped_in(self):
        required, authority = write_request_env.clean_tls(
            placement.EXTERNAL, "1", f"  {self.REAL}  trailing text"
        )
        assert required
        assert authority.startswith("-----BEGIN CERTIFICATE-----")
        assert "trailing text" not in authority

    def test_a_certificate_that_cannot_be_read_is_refused_here(self):
        # Refused where the researcher pasted it: devices treat an unreadable
        # authority as a database they cannot reach, so the alternative is a study
        # that enrols and then stops uploading.
        with pytest.raises(SystemExit):
            write_request_env.clean_tls(placement.EXTERNAL, "1", "not a certificate")


class TestCarryingTheAnswerToTheStudyModel:
    """deploy_config: what this wizard run declares about the connection.

    The request env is the boundary between a form and a study, and a `.env` file
    holds one setting per line while a PEM holds several. Encoding is what lets a
    researcher's paste cross it as the bytes they pasted.
    """

    REAL = TestWhatTheWizardMayAskOfTheConnection.REAL

    def _request(self, monkeypatch, values, tmp_path):
        path = tmp_path / "request.env"
        path.write_text(
            "\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8"
        )
        monkeypatch.setattr(deploy_config, "RUNNING_IN_WIZARD", True)
        monkeypatch.setattr(deploy_config, "REQUEST_ENV_PATH", path)

    def test_a_named_database_carries_its_answer(self, monkeypatch, tmp_path):
        self._request(
            monkeypatch,
            {
                "DB_PLACEMENT": "external",
                "DB_HOST": "db.example.edu",
                "DB_PORT": "3306",
                "DB_REQUIRE_TLS": "0",
            },
            tmp_path,
        )
        assert deploy_config.requested_placement()["require_tls"] is False

    def test_an_authority_arrives_as_the_bytes_that_were_pasted(
        self, monkeypatch, tmp_path
    ):
        import base64

        self._request(
            monkeypatch,
            {
                "DB_PLACEMENT": "external",
                "DB_HOST": "db.example.edu",
                "DB_REQUIRE_TLS": "1",
                "DB_CA_CERTIFICATE_B64": base64.b64encode(
                    self.REAL.encode("utf-8")
                ).decode("ascii"),
            },
            tmp_path,
        )
        assert deploy_config.requested_placement()["ca_certificate"].startswith(
            "-----BEGIN CERTIFICATE-----"
        )

    def test_a_run_that_pasted_nothing_leaves_the_study_alone(
        self, monkeypatch, tmp_path
    ):
        # The wizard cannot tell an empty field from one nobody typed in, so it does
        # not get to clear an authority a study is publishing. That is done where
        # the current one can be seen, which is the Configurator.
        self._request(
            monkeypatch,
            {
                "DB_PLACEMENT": "external",
                "DB_HOST": "db.example.edu",
                "DB_REQUIRE_TLS": "1",
            },
            tmp_path,
        )
        assert "ca_certificate" not in deploy_config.requested_placement()

    def test_the_bundled_placement_carries_no_answer(self, monkeypatch, tmp_path):
        self._request(
            monkeypatch, {"DB_PLACEMENT": "bundled", "DB_REQUIRE_TLS": "0"}, tmp_path
        )
        assert deploy_config.requested_placement() == {"host": placement.DEFAULT_HOST}

    def test_an_unencrypted_study_publishes_no_authority(self):
        # ensure_database_authority reads a bundled MySQL's own certificate out of
        # the container; there is nothing to read for a connection that carries
        # nothing to verify.
        source = {
            "database": {
                "host": "db.example.edu",
                "tls": {"require": False},
                "android": {},
            }
        }
        assert deploy_config.ensure_database_authority(source) == "unencrypted"


class TestWhatIsWrittenBackToEnv:
    """persist_env: a wizard run's answers, minus the ones that were only in transit.

    The request env is merged over `.env` so a run's answers reach the code that
    applies them, and everything unrecognised is carried through --- which is what
    keeps a deployment's own settings from being dropped by a wizard that never
    asked about them. A pasted certificate is the exception: the study model holds
    it, and a second copy in `.env` is one more thing that can go stale.
    """

    def test_a_pasted_authority_is_not_a_deployment_setting(
        self, monkeypatch, tmp_path
    ):
        written = tmp_path / ".env"
        monkeypatch.setattr(deploy_config, "ENV_PATH", written)
        deploy_config.persist_env(
            {"PUBLIC_HOST": "h", "DB_CA_CERTIFICATE_B64": "QUJD", "DB_PORT": "3306"}
        )
        body = written.read_text(encoding="utf-8")
        assert "DB_CA_CERTIFICATE_B64" not in body
        assert "DB_PORT=3306" in body


class TestTheDeployIsCheckedAgainstThePlacementToo:
    """check_dataflow_applied: the bundled bind address only when there is one.

    The dataflow does not decide that address on its own. A study on the direct path
    with a database of its own has to publish MySQL to every network a participant
    might be on; the same study pointed at a server it names publishes nothing,
    because the phones open that server instead and the bundled service is removed
    from the deployment altogether. Read as though the dataflow decided it, the
    placeholder written for the compose file reads as a deployment that disagrees
    with itself, and the combination the wizard offers cannot be deployed at all.
    """

    def _external_direct(self):
        return {
            "deployment": {"dataflow": {"android": "direct", "ios": "webservice"}},
            "database": {"host": "db.example.edu", "android": {"port": 3306}},
        }

    def _publish(self, monkeypatch, tmp_path, config, join_url):
        study = tmp_path / "studyConfig.json"
        study.write_text(json.dumps(config), encoding="utf-8")
        monkeypatch.setattr(deploy_config, "STUDY_CONFIG_PATH", study)
        urls = tmp_path / "deployment-urls.json"
        urls.write_text(json.dumps({"android_join_url": join_url}), encoding="utf-8")
        monkeypatch.setattr(deploy_config, "PROJECT", tmp_path)

    def test_a_named_database_leaves_the_bind_address_undecided(self, tmp_path, monkeypatch):
        direct_url = "http://host/studies/files/studyConfig.json"
        self._publish(monkeypatch, tmp_path, {"database": {"database_host": "db"}}, direct_url)

        # The value apply_dataflow writes for this combination, which is a placeholder
        # rather than a claim about anything a phone reaches.
        deploy_config.check_dataflow_applied(self._external_direct(), "127.0.0.1", direct_url)

    def test_the_bundled_database_is_still_held_to_the_dataflow(self, tmp_path, monkeypatch):
        direct_url = "http://host/studies/files/studyConfig.json"
        self._publish(monkeypatch, tmp_path, {"database": {"database_host": "db"}}, direct_url)
        bundled = {
            "deployment": {"dataflow": {"android": "direct", "ios": "webservice"}},
            "database": {"host": "mysql", "android": {"port": 3306}},
        }

        with pytest.raises(SystemExit) as refused:
            deploy_config.check_dataflow_applied(bundled, "127.0.0.1", direct_url)

        assert "0.0.0.0" in str(refused.value)
