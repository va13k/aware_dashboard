"""Tests for where the study database runs, as a choice with consequences.

Three things are worth holding onto. The placement is read from the host the study
declares rather than kept as a field beside it, so the two can never disagree about
which database a study is using. What the connection demands --- who opens it, whether
it leaves the machine, and therefore whether it is encrypted --- is read from the
combination of placement and dataflow, because either alone names only half of it.
And taking the bundled database out of a deployment means taking the waits on it out
too: a service kept out of a compose file is still depended on, and compose starts a
dependency whether or not anybody asked for it.
"""

import json
import pathlib
import subprocess
import sys

import re

import pytest
from types import SimpleNamespace

from shared_config import dataflow, placement

SETUP = pathlib.Path(__file__).resolve().parent.parent / "setup"
sys.path.insert(0, str(SETUP))

import deploy_config  # noqa: E402
import write_request_env  # noqa: E402

from shared_config import database  # noqa: E402


def request_env_for(payload: dict, tmp_path: pathlib.Path) -> str:
    """What the wizard writes for one run, produced the way the wizard produces it."""
    written = tmp_path / "request.env"
    subprocess.run(
        [sys.executable, str(SETUP / "write_request_env.py"), str(written)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return written.read_text(encoding="utf-8")


class TestWhereItIsRead:
    """placement.declared: one answer, taken from the host the study names."""

    @pytest.mark.parametrize("host", ["", "db.internal", "mysql", "localhost", "127.0.0.1"])
    def test_a_host_naming_our_own_database_is_bundled(self, host):
        assert placement.declared({"database": {"host": host}}) == placement.BUNDLED

    @pytest.mark.parametrize("host", ["db.example.edu", "10.1.2.3", "mysql.institution.internal"])
    def test_any_other_host_is_external(self, host):
        assert placement.declared({"database": {"host": host}}) == placement.EXTERNAL

    def test_a_study_naming_no_host_runs_the_bundled_one(self):
        # Which is what a study written before the choice existed was already doing.
        assert placement.declared({}) == placement.BUNDLED

    def test_the_placement_is_not_a_field_of_its_own(self):
        # Reading it from the host is what keeps a study from declaring one thing and
        # connecting to another; a second field could carry a second answer.
        source = {"database": {"host": "db.example.edu", "placement": "bundled"}}
        assert placement.declared(source) == placement.EXTERNAL


class TestWhatTheCombinationDecides:
    """placement.connection: the dataflow names half of it, the placement the rest."""

    @pytest.mark.parametrize(
        "where,flow,opener,crosses,bind",
        [
            (placement.BUNDLED, dataflow.DIRECT, "participants", True, "0.0.0.0"),
            (placement.BUNDLED, dataflow.WEBSERVICE, "server", False, "127.0.0.1"),
            (placement.EXTERNAL, dataflow.DIRECT, "participants", True, None),
            (placement.EXTERNAL, dataflow.WEBSERVICE, "server", True, None),
        ],
    )
    def test_every_cell(self, where, flow, opener, crosses, bind):
        c = placement.connection(where, flow)
        assert (c["opener"], c["crosses_network"], c["bundled_bind"]) == (opener, crosses, bind)

    def test_a_phone_opening_the_database_needs_it_published_publicly(self):
        # Not a preference: a participant's phone reaches it from whatever network
        # they happen to be on, so loopback would cut off the whole study.
        assert placement.connection(placement.BUNDLED, dataflow.DIRECT)["bundled_bind"] == "0.0.0.0"

    def test_a_server_beside_the_database_publishes_nothing_public(self):
        # Every service reaches it over the compose network, so the published
        # address has no audience beyond this host.
        assert placement.connection(placement.BUNDLED, dataflow.WEBSERVICE)["bundled_bind"] == "127.0.0.1"

    def test_a_named_database_has_no_bind_of_ours(self):
        # This deployment runs no database, so there is nothing to publish.
        for flow in (dataflow.DIRECT, dataflow.WEBSERVICE):
            assert placement.connection(placement.EXTERNAL, flow)["bundled_bind"] is None


class TestWhenEncryptionIsNotAQuestion:
    """placement.requires_tls: settled by the placement, or the researcher's to answer."""

    @pytest.mark.parametrize("flow", [dataflow.DIRECT, dataflow.WEBSERVICE])
    def test_a_database_this_deployment_runs_is_always_encrypted(self, flow):
        # Both ends are ours: this deployment generates the certificate, publishes
        # the authority and grants the accounts. There is nothing to arrange and so
        # nothing to ask.
        assert placement.requires_tls(placement.BUNDLED)
        assert placement.unencrypted_warning(placement.BUNDLED, flow) is None

    @pytest.mark.parametrize("flow", [dataflow.DIRECT, dataflow.WEBSERVICE])
    def test_a_named_database_answers_to_its_owner(self, flow):
        # TLS on somebody else's server is something they offer or do not, so the
        # study declares what it needs and the interface says what going without it
        # costs.
        assert not placement.requires_tls(placement.EXTERNAL)
        assert placement.unencrypted_warning(placement.EXTERNAL, flow)

    def test_the_two_unsafe_cases_read_differently(self):
        # One exposes every participant's own network, the other the link between
        # two servers. A single generic caution would understate both.
        phones = placement.unencrypted_warning(placement.EXTERNAL, dataflow.DIRECT)
        server = placement.unencrypted_warning(placement.EXTERNAL, dataflow.WEBSERVICE)
        assert "participant" in phones and phones != server


class TestWhatIsRefusedAndWhatIsOnlyWarnedAbout:
    def test_a_named_database_with_phones_on_it_is_offered(self):
        # Refusing would decide for a researcher running their own server. The cost
        # is stated instead.
        assert placement.unsupported_reason(placement.EXTERNAL, dataflow.DIRECT) is None
        assert placement.exposure_caution(placement.EXTERNAL, dataflow.DIRECT)

    def test_the_caution_names_who_has_to_open_the_host(self):
        caution = placement.exposure_caution(placement.EXTERNAL, dataflow.DIRECT)
        assert "any network" in caution and "institution" in caution

    def test_the_server_path_asks_nothing_of_the_network(self):
        assert placement.exposure_caution(placement.EXTERNAL, dataflow.WEBSERVICE) is None

    def test_a_placement_nothing_recognises_is_still_refused(self):
        assert placement.unsupported_reason("elsewhere", dataflow.WEBSERVICE) is not None

    def test_validate_is_empty_for_every_real_combination(self):
        for host in ("db.internal", "db.example.edu"):
            for flow in (dataflow.DIRECT, dataflow.WEBSERVICE):
                source = {"database": {"host": host}, "deployment": {"dataflow": {"android": flow}}}
                assert placement.validate(source) == []


class TestWhatASwitchCosts:
    """placement.switch_note: the part the software does not do."""

    def test_no_change_says_nothing(self):
        assert placement.switch_note(placement.BUNDLED, placement.BUNDLED) is None

    @pytest.mark.parametrize(
        "current,chosen",
        [(placement.BUNDLED, placement.EXTERNAL), (placement.EXTERNAL, placement.BUNDLED)],
    )
    def test_a_switch_says_the_data_stays_where_it_is(self, current, chosen):
        note = placement.switch_note(current, chosen)
        # Carrying the history is the researcher's, through export and merge-import.
        # A switch that silently left the rows behind would read as data loss.
        assert "does not move" in note
        assert "merge-import" in note


class TestTheBoundary:
    """write_request_env.clean_placement: refused where the researcher gave it."""

    def test_bundled_resolves_to_our_own_host(self):
        assert write_request_env.clean_placement("bundled", dataflow.DIRECT, "") == (
            placement.BUNDLED,
            placement.DEFAULT_HOST,
        )

    def test_external_keeps_the_host_it_was_given(self):
        assert write_request_env.clean_placement(
            "external", dataflow.WEBSERVICE, " db.example.edu "
        ) == (placement.EXTERNAL, "db.example.edu")

    def test_external_with_the_direct_dataflow_is_accepted(self):
        # It asks something of the network that an institution will usually refuse,
        # and that is a cost to state rather than a decision to take for a researcher
        # running their own server. The caution carries it; the boundary does not.
        assert write_request_env.clean_placement("external", dataflow.DIRECT, "db.example.edu") == (
            placement.EXTERNAL,
            "db.example.edu",
        )
        assert placement.exposure_caution(placement.EXTERNAL, dataflow.DIRECT)

    def test_external_naming_no_host_is_refused(self):
        with pytest.raises(SystemExit):
            write_request_env.clean_placement("external", dataflow.WEBSERVICE, "")

    def test_external_naming_our_own_database_is_refused(self):
        # Otherwise the study declares external, the override takes the bundled
        # database out, and the address left behind names the thing just removed.
        with pytest.raises(SystemExit):
            write_request_env.clean_placement("external", dataflow.WEBSERVICE, "localhost")

    def test_an_unknown_placement_is_refused_rather_than_defaulted(self):
        with pytest.raises(SystemExit):
            write_request_env.clean_placement("elsewhere", dataflow.WEBSERVICE, "db.example.edu")


class TestTakingTheBundledDatabaseOut:
    """deploy_config.build_compose_override: the service and its waits, together."""

    def test_the_database_service_is_removed(self):
        assert "mysql: !reset null" in deploy_config.build_compose_override()

    def test_the_backup_job_goes_with_it_unless_it_was_asked_for(self):
        """The job was written for the database this deployment runs. Left in
        without being asked for, it would dump a server it cannot reach for the
        length of the study; taken out without being asked, it would end a study's
        backups because its database moved."""
        assert "mysql-backup: !reset null" in deploy_config.build_compose_override()
        assert "mysql-backup: !reset null" not in deploy_config.build_compose_override(
            {"MYSQL_USER": "aware_analytics"}
        )

    def test_a_kept_backup_job_stops_waiting_on_the_database_that_left(self):
        # Kept and still depending on the removed service is the one combination
        # that deploys nothing: compose starts a dependency whether or not the
        # override asked for it.
        override = deploy_config.build_compose_override({"MYSQL_USER": "aware_analytics"})
        assert "  mysql-backup:\n    depends_on: !reset null" in override

    def test_a_kept_backup_job_is_told_which_server_and_which_account(self):
        override = deploy_config.build_compose_override(
            {"MYSQL_PORT": "12365", "MYSQL_USER": "aware_analytics", "MYSQL_SSL_MODE": "REQUIRED"}
        )
        assert "      MYSQL_PORT: 12365" in override
        assert "      MYSQL_USER: aware_analytics" in override
        assert "      MYSQL_SSL_MODE: REQUIRED" in override

    def test_the_account_that_dumps_a_named_server_may_only_read(self):
        """An administrator's password would sit in a container's environment for
        the length of the study, to do something reading every row already does."""
        connection = deploy_config.backup_connection(
            {"database": {"android": {"port": 12365}, "tls": {"required": True}}}
        )
        assert connection["MYSQL_USER"] == database.ANALYTICS_USER
        assert connection["MYSQL_PORT"] == "12365"
        assert connection["MYSQL_SSL_MODE"] == "REQUIRED"

    def test_no_password_is_written_into_the_generated_file(self):
        # Left as a reference compose resolves from .env, which the deployment
        # already protects. A generated file holding the same secret is one more
        # place for it to be read from.
        override = deploy_config.build_compose_override(
            deploy_config.backup_connection({"database": {"android": {"port": 3306}}})
        )
        assert "${ANALYTICS_DB_PASSWORD}" in override
        assert database.ANALYTICS_SEED_PASSWORD not in override

    def test_every_service_that_waits_on_it_stops_waiting(self):
        override = deploy_config.build_compose_override()
        for service in deploy_config.WAITS_ON_BUNDLED_MYSQL:
            assert f"  {service}:\n    depends_on: !reset null" in override

    def test_the_waits_match_the_compose_file(self):
        # Read from the compose file rather than restated, because a service that
        # gains a wait on the database and is missed here would hold up every
        # external deployment while compose starts a database nobody wants.
        compose = (
            pathlib.Path(__file__).resolve().parent.parent / "docker-compose.yml"
        ).read_text(encoding="utf-8")
        waiting, service = [], ""
        lines = compose.splitlines()
        for index, line in enumerate(lines):
            if line.startswith("  ") and line.endswith(":") and not line.startswith("    "):
                service = line.strip().rstrip(":")
            if line.strip() == "depends_on:" and index + 1 < len(lines):
                if lines[index + 1].strip() == "mysql:":
                    waiting.append(service)
        # A service that waits is either kept and released from the wait, or taken
        # out of the deployment altogether. One that is neither would hold up every
        # external deployment while compose starts a database nobody wants.
        assert sorted(waiting) == sorted(
            set(deploy_config.WAITS_ON_BUNDLED_MYSQL) | {deploy_config.BACKUP_SERVICE}
        )


class TestWhichPlacementRunsADatabase:
    def test_bundled_runs_one(self):
        assert placement.runs_bundled_mysql(placement.BUNDLED)

    def test_external_runs_none(self):
        assert not placement.runs_bundled_mysql(placement.EXTERNAL)


class TestReadingACertificate:
    """shared_config.certificates: one reader, because two places must agree.

    The Configurator accepts a certificate from a researcher and the deploy publishes
    it to the phones. If one accepted what the other could not read, it would be
    stored as valid and then stop every device uploading — which is the failure the
    check exists to prevent, arriving through the check itself.
    """

    ONE = (
        "-----BEGIN CERTIFICATE-----\n"
        "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA\n"
        "-----END CERTIFICATE-----"
    )

    def test_a_certificate_survives_its_wrapper(self):
        from shared_config.certificates import read_certificate

        # The NUL is what `docker exec` appends, and it would travel into the study
        # config as the unreadable authority that halts collection.
        cleaned = read_certificate(self.ONE + "\n\x00")
        assert cleaned.startswith("-----BEGIN CERTIFICATE-----")
        assert "\x00" not in cleaned

    def test_a_bundle_is_kept_whole(self):
        from shared_config.certificates import read_certificate

        # A provider handing over a chain expects all of it to be trusted; dropping
        # the rest leaves a client unable to build a path to the root.
        assert read_certificate(self.ONE + "\n" + self.ONE).count("BEGIN CERTIFICATE") == 2

    @pytest.mark.parametrize(
        "bad",
        ["", "just text", "-----BEGIN CERTIFICATE-----\nnot base64!!\n-----END CERTIFICATE-----"],
    )
    def test_nothing_unreadable_passes(self, bad):
        from shared_config.certificates import valid_certificate

        assert not valid_certificate(bad)

    def test_the_deploy_and_the_configurator_use_the_same_reader(self):
        import deploy_config
        from shared_config import certificates

        # Not two implementations that happen to agree today.
        assert deploy_config.read_certificate is certificates.read_certificate

class TestTheAdministratorAccount:
    """Which account creates the schema, when the database is not ours.

    A bundled database is MySQL's own, where the administrator is root. A managed
    one names it something else, and a study told to authenticate as root there
    fails in a way that reads like a wrong password rather than a wrong account.
    """

    def test_root_is_the_fallback(self):
        assert write_request_env.clean_admin_user("", "root") == "root"
        assert write_request_env.clean_admin_user(None, "") == "root"

    def test_a_named_account_is_kept(self):
        assert write_request_env.clean_admin_user("avnadmin", "root") == "avnadmin"
        assert write_request_env.clean_admin_user("  doadmin  ", "root") == "doadmin"

    def test_a_previous_answer_stands_in_for_a_blank_field(self):
        assert write_request_env.clean_admin_user("", "avnadmin") == "avnadmin"

    @pytest.mark.parametrize(
        "name", ["ad min", "admin;DROP", "'admin'", "a" * 33, "admin`"]
    )
    def test_a_name_mysql_would_not_take_is_refused(self, name):
        # Refused rather than escaped: this ends up in a command line and in
        # GRANT statements, and neither takes a placeholder for an account.
        with pytest.raises(SystemExit):
            write_request_env.clean_admin_user(name, "root")

    def test_the_names_managed_services_use_are_all_acceptable(self):
        for name in ["avnadmin", "doadmin", "aware_admin", "admin@example", "a-b.c_d"]:
            assert write_request_env.clean_admin_user(name, "root") == name

class TestWhatAProviderHandsOut:
    """A connection string is what a researcher has, so it is what setup reads.

    Nobody deploying for the first time knows that Aiven calls its administrator
    `avnadmin`, and nothing about a managed database says so on the form. The
    string carries it, and the host says it even when the string is not used.
    """

    def test_a_connection_string_becomes_its_parts(self):
        found = write_request_env.parse_connection_string(
            "mysql://avnadmin:AVNS_token@mysql-1.aivencloud.com:12365/defaultdb?ssl-mode=REQUIRED"
        )
        assert found == {
            "host": "mysql-1.aivencloud.com",
            "port": "12365",
            "admin_user": "avnadmin",
            "admin_password": "AVNS_token",
        }

    def test_a_password_with_url_characters_survives_the_trip(self):
        found = write_request_env.parse_connection_string(
            "mysql://doadmin:a%40b%2Fc@db-1.ondigitalocean.com:25060/defaultdb"
        )
        assert found["admin_password"] == "a@b/c"

    @pytest.mark.parametrize(
        "text", ["db.example.edu", "", "not a string at all", "mysql://"]
    )
    def test_anything_that_is_not_one_reads_as_nothing(self, text):
        assert write_request_env.parse_connection_string(text) == {}

    @pytest.mark.parametrize(
        "host, expected",
        [
            ("mysql-133d-x.a.aivencloud.com", "avnadmin"),
            ("db-mysql-fra1-1.b.ondigitalocean.com", "doadmin"),
            ("db.example.edu", ""),
            ("", ""),
        ],
    )
    def test_the_host_names_the_account_where_it_can(self, host, expected):
        assert database.admin_for_host(host) == expected

    def test_the_answer_is_settled_in_one_place(self):
        # The wizard, the deploy and the checks each need it, and an account one
        # of them uses and the others do not is a deployment that half works.
        assert database.admin_user("mysql-1.aivencloud.com", "") == "avnadmin"
        assert database.admin_user("db.example.edu", "") == "root"
        assert database.admin_user("mysql-1.aivencloud.com", "chosen") == "chosen"

class TestWhoMakesTheDatabaseReady:
    """Setup, or whoever administers the database — and the study says which.

    Creating a schema needs an account stronger than the one that writes to it.
    Most managed databases hand you one; an institutional server hands you an
    account that may insert and nothing else, and that study needs its SQL run
    for it rather than by it.
    """

    def test_setup_does_it_unless_told_otherwise(self):
        assert write_request_env.clean_db_init("", "") == "auto"
        assert write_request_env.clean_db_init(None, "auto") == "auto"

    def test_a_study_can_ask_to_run_the_sql_itself(self):
        assert write_request_env.clean_db_init("manual", "auto") == "manual"

    def test_a_previous_answer_stands_in_for_a_blank_one(self):
        assert write_request_env.clean_db_init("", "manual") == "manual"

    @pytest.mark.parametrize("choice", ["later", "sometimes", "1"])
    def test_anything_else_is_refused(self, choice):
        with pytest.raises(SystemExit):
            write_request_env.clean_db_init(choice, "auto")

class TestWhatFollowsTheStudyToTheNewServer:
    """Neither the collected rows nor the backup job moves because the database did.

    A move settles where the next row is written. Copying gigabytes onto a server
    somebody else pays for, and pulling the whole study back across the network every
    night, are decisions about that server rather than steps in a redeploy --- so
    each is a question whose unanswered value is no.
    """

    @pytest.mark.parametrize("answer", ["", None, "later", "maybe", "  "])
    def test_an_answer_nobody_gave_is_no(self, answer):
        assert write_request_env.clean_flag(answer) == "0"

    @pytest.mark.parametrize("answer", ["1", "true", "yes", "on", "  On  "])
    def test_a_yes_is_read_however_it_arrives(self, answer):
        assert write_request_env.clean_flag(answer) == "1"

    @pytest.mark.parametrize("answer", ["0", "false", "no", "off"])
    def test_a_no_is_read_the_same_way(self, answer):
        assert write_request_env.clean_flag(answer, "1") == "0"

    def test_a_blank_field_keeps_what_the_deployment_settled(self):
        # A redeploy that opens the wizard on its defaults must not end the backups
        # a study has been taking.
        assert write_request_env.clean_flag("", "1") == "1"

    def test_both_answers_reach_the_deployment(self, tmp_path):
        written = request_env_for(
            {
                "mysql_root_password": "adminpass",
                "public_host": "study.example.edu",
                "android_dataflow": dataflow.WEBSERVICE,
                "db_placement": "external",
                "db_host": "db.example.edu",
                "db_keep_backups": "1",
            },
            tmp_path,
        )
        assert "DB_KEEP_BACKUPS=1" in written
        # Unanswered, and written all the same: the deploy reads a file rather than
        # a form, and a key that is absent on one run and present on another is a
        # default restated in two places.
        assert "DB_CARRY_DATA=0" in written

    def test_the_kept_answer_is_documented_where_the_deployment_keeps_it(self):
        # It outlives the wizard run, so somebody reading .env has to find out what
        # it decides without opening the setup page.
        example = (
            pathlib.Path(__file__).resolve().parent.parent / "env.example"
        ).read_text(encoding="utf-8")
        assert "DB_KEEP_BACKUPS=" in example


class TestWhichAnswerTheDeploymentRemembers:
    """One of these two is a setting and the other is an act.

    Backups run for as long as the study does, so the answer belongs to the
    deployment. A copy happens once, and a deployment that remembered it would offer
    to repeat it on every redeploy.
    """

    def test_the_backup_answer_outlives_the_wizard_run_that_gave_it(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(deploy_config, "REQUEST_ENV_PATH", tmp_path / "no-request.env")
        env_path = tmp_path / ".env"
        env_path.write_text("DB_KEEP_BACKUPS=1\n", encoding="utf-8")
        monkeypatch.setattr(deploy_config, "ENV_PATH", env_path)
        assert deploy_config.keeps_backups() is True

    def test_this_run_answers_over_what_was_settled_before(self, tmp_path, monkeypatch):
        request = tmp_path / "request.env"
        request.write_text("DB_KEEP_BACKUPS=0\n", encoding="utf-8")
        monkeypatch.setattr(deploy_config, "REQUEST_ENV_PATH", request)
        env_path = tmp_path / ".env"
        env_path.write_text("DB_KEEP_BACKUPS=1\n", encoding="utf-8")
        monkeypatch.setattr(deploy_config, "ENV_PATH", env_path)
        assert deploy_config.keeps_backups() is False

    def test_the_copy_is_asked_for_once_and_never_remembered(self, tmp_path, monkeypatch):
        monkeypatch.setattr(deploy_config, "REQUEST_ENV_PATH", tmp_path / "no-request.env")
        env_path = tmp_path / ".env"
        env_path.write_text("DB_CARRY_DATA=1\n", encoding="utf-8")
        monkeypatch.setattr(deploy_config, "ENV_PATH", env_path)
        assert deploy_config.carries_collected_rows() is False
        assert "DB_CARRY_DATA" in deploy_config.REQUEST_ONLY_KEYS


class TestCarryingTheCollectedRows:
    """deploy_config.apply_data_copy: a file that exists only where it was asked for."""

    SOURCE = {
        "database": {
            "host": "db.example.edu",
            "android": {"port": 12365, "name": "aware_android"},
            "ios": {"port": 12365, "name": "aware_ios"},
            "tls": {"require": True},
        }
    }

    def ask(self, tmp_path, monkeypatch, answer):
        request = tmp_path / "request.env"
        request.write_text(f"DB_CARRY_DATA={answer}\n", encoding="utf-8")
        monkeypatch.setattr(deploy_config, "REQUEST_ENV_PATH", request)
        env_path = tmp_path / ".env"
        env_path.write_text("DB_ADMIN_USER=avnadmin\n", encoding="utf-8")
        monkeypatch.setattr(deploy_config, "ENV_PATH", env_path)
        monkeypatch.setattr(deploy_config, "COPY_SCRIPT_PATH", tmp_path / "copy-study-data.sh")
        return tmp_path / "copy-study-data.sh"

    def test_a_move_that_leaves_the_rows_behind_leaves_nothing_to_run(
        self, tmp_path, monkeypatch
    ):
        path = self.ask(tmp_path, monkeypatch, "0")
        assert deploy_config.apply_data_copy(self.SOURCE) is False
        assert not path.exists()

    def test_a_study_staying_where_it_is_has_nowhere_to_copy_from(
        self, tmp_path, monkeypatch
    ):
        path = self.ask(tmp_path, monkeypatch, "1")
        assert deploy_config.apply_data_copy({"database": {"host": "db.internal"}}) is False
        assert not path.exists()

    def test_asking_again_for_a_move_already_made_takes_the_file_away(
        self, tmp_path, monkeypatch
    ):
        path = self.ask(tmp_path, monkeypatch, "1")
        deploy_config.apply_data_copy(self.SOURCE)
        assert path.exists()
        self.ask(tmp_path, monkeypatch, "0")
        deploy_config.apply_data_copy(self.SOURCE)
        assert not path.exists()

    def test_the_script_names_the_server_it_copies_into(self, tmp_path, monkeypatch):
        path = self.ask(tmp_path, monkeypatch, "1")
        deploy_config.apply_data_copy(self.SOURCE)
        written = path.read_text(encoding="utf-8")
        assert "TARGET_HOST='db.example.edu'" in written
        assert "TARGET_PORT='12365'" in written
        assert "TARGET_USER='avnadmin'" in written
        assert "TARGET_SSL_MODE='REQUIRED'" in written

    def test_it_carries_no_password_of_its_own(self, tmp_path, monkeypatch):
        # Read from the container that holds one and from .env for the other, so a
        # file the researcher may copy about is not a credential.
        path = self.ask(tmp_path, monkeypatch, "1")
        (tmp_path / ".env").write_text(
            "DB_ADMIN_USER=avnadmin\nDB_ADMIN_PASSWORD=n0t-in-the-script\n",
            encoding="utf-8",
        )
        deploy_config.apply_data_copy(self.SOURCE)
        written = path.read_text(encoding="utf-8")
        assert "n0t-in-the-script" not in written
        assert 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD"' in written
        assert "sed -n 's/^DB_ADMIN_PASSWORD=//p' .env" in written

    def test_stopping_halfway_costs_only_the_time(self, tmp_path, monkeypatch):
        # Every row is inserted by the id the old server gave it, so a second run
        # adds what the first did not and repeats nothing.
        path = self.ask(tmp_path, monkeypatch, "1")
        deploy_config.apply_data_copy(self.SOURCE)
        assert "--insert-ignore" in path.read_text(encoding="utf-8")

    def test_a_database_already_collecting_is_refused_rather_than_merged(
        self, tmp_path, monkeypatch
    ):
        # INSERT IGNORE against a server with rows of its own drops the colliding
        # ids without a word, which is the one way this could lose data.
        path = self.ask(tmp_path, monkeypatch, "1")
        deploy_config.apply_data_copy(self.SOURCE)
        written = path.read_text(encoding="utf-8")
        assert "SELECT COUNT(*) FROM aware_device" in written
        assert "backup page" in written

    def test_only_what_the_api_rebuilds_is_left_behind(self, tmp_path, monkeypatch):
        # A copy into an empty server has no second deployment's answers to
        # reconcile with, so the researcher's own --- enrolment, refusals,
        # exclusions --- travel. What stays is arithmetic over the rows themselves.
        path = self.ask(tmp_path, monkeypatch, "1")
        deploy_config.apply_data_copy(self.SOURCE)
        written = path.read_text(encoding="utf-8")
        assert "SKIP_TABLES='record_counts coverage_hourly'" in written
        for decision in ("device_enrolment", "refusals", "device_exclusions"):
            assert f"--ignore-table=aware_android.{decision}" not in written

    def test_it_is_a_script_a_shell_will_take(self, tmp_path, monkeypatch):
        path = self.ask(tmp_path, monkeypatch, "1")
        deploy_config.apply_data_copy(self.SOURCE)
        checked = subprocess.run(["sh", "-n", str(path)], capture_output=True, text=True)
        assert checked.returncode == 0, checked.stderr

    def test_it_is_a_file_the_researcher_can_run(self, tmp_path, monkeypatch):
        path = self.ask(tmp_path, monkeypatch, "1")
        deploy_config.apply_data_copy(self.SOURCE)
        assert path.stat().st_mode & 0o111


class TestTheEnvironmentAlwaysCarriesTheAccount:
    """`.env` is what every script reads before opening the database.

    A deployment upgraded in place has a file written before the question was
    asked, so the answer is settled when the file is written rather than guessed
    again by each reader.
    """

    def test_the_example_file_shows_the_key(self):
        example = (
            pathlib.Path(__file__).resolve().parent.parent / "env.example"
        ).read_text(encoding="utf-8")
        assert "DB_ADMIN_USER=" in example

    def test_the_host_settles_it_when_nothing_else_did(self):
        assert database.admin_user("mysql-1.aivencloud.com", "") == "avnadmin"

    def test_a_bundled_database_keeps_mysqls_own_administrator(self):
        assert database.admin_user(database.COMPOSE_HOST, "") == "root"
        assert database.admin_user("db.internal", "") == "root"


class TestWhatComesBackWithTheBundledDatabase:
    """Moving a study back onto the database this deployment runs.

    The placement decides the address, and the address is a host and a port. Only the
    host was settled by it, so a study returning from a server on 12365 kept that
    number and every service was configured for a port this deployment does not
    publish --- a deployment that starts, looks configured and reaches nothing.
    """

    def test_the_bundled_database_brings_its_own_port(self):
        payload = {"db_placement": "bundled", "db_port": "12365"}
        chosen, host = write_request_env.clean_placement(
            payload["db_placement"], "webservice", ""
        )
        assert (chosen, host) == (placement.BUNDLED, placement.DEFAULT_HOST)
        # The whole point: what the form still carried is not what is written.
        assert placement.DEFAULT_PORT == 3306

    def test_a_named_server_keeps_the_port_it_was_given(self, tmp_path, monkeypatch):
        written = self._request(
            monkeypatch,
            tmp_path,
            {
                "db_placement": "external",
                "db_host": "db.example.edu",
                "db_port": "12365",
                "android_dataflow": "webservice",
                "mysql_root_password": "pw",
                "public_host": "study.example.org",
            },
        )
        assert "DB_PORT=12365" in written

    def test_moving_back_leaves_the_other_servers_port_behind(self, tmp_path, monkeypatch):
        written = self._request(
            monkeypatch,
            tmp_path,
            {
                "db_placement": "bundled",
                "db_port": "12365",
                "android_dataflow": "webservice",
                "mysql_root_password": "pw",
                "public_host": "study.example.org",
            },
        )
        assert "DB_PORT=3306" in written
        assert "DB_PORT=12365" not in written
        assert f"DB_HOST={placement.DEFAULT_HOST}" in written

    def _request(self, monkeypatch, tmp_path, payload):
        """One wizard submission, as write_request_env writes it out."""
        target = tmp_path / "request.env"
        monkeypatch.setattr(sys, "argv", ["write_request_env.py", str(target)])
        monkeypatch.setattr(
            write_request_env.json, "load", lambda _stream: dict(payload)
        )
        write_request_env.main()
        return target.read_text(encoding="utf-8")


class TestTheAuthorityBelongsToTheServer:
    """ensure_database_authority: a CA is the server's, not the study's.

    A researcher moving back onto the bundled database keeps every answer they gave
    except the ones that described the other server. The authority is one of those:
    published to phones and checked against a certificate it never signed, it reads
    as a database they cannot reach, and the deployment's own check refuses first.
    """

    ANOTHER_SERVERS_CA = (
        "-----BEGIN CERTIFICATE-----\nnot this server's\n-----END CERTIFICATE-----"
    )

    def _model(self, host):
        return {
            "database": {
                "host": host,
                "android": {"port": 3306},
                "tls": {"require": True, "ca_certificate": self.ANOTHER_SERVERS_CA},
            }
        }

    def test_moving_onto_the_bundled_database_clears_it(self, monkeypatch):
        monkeypatch.setattr(deploy_config, "valid_certificate", lambda _pem: True)
        monkeypatch.setattr(deploy_config, "update_source", lambda mutate: mutate({}))
        # No container to read a new one from, which is the first deploy's case too.
        monkeypatch.setattr(
            deploy_config.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr=""),
        )
        source = self._model(placement.DEFAULT_HOST)

        assert deploy_config.ensure_database_authority(source) == "none"
        assert source["database"]["tls"]["ca_certificate"] == ""

    def test_a_named_server_keeps_the_authority_it_was_given(self, monkeypatch):
        monkeypatch.setattr(deploy_config, "valid_certificate", lambda _pem: True)
        source = self._model("db.example.edu")

        assert deploy_config.ensure_database_authority(source) == "supplied"
        assert source["database"]["tls"]["ca_certificate"] == self.ANOTHER_SERVERS_CA

    def test_the_bundled_servers_own_authority_replaces_it(self, monkeypatch):
        monkeypatch.setattr(deploy_config, "valid_certificate", lambda _pem: True)
        monkeypatch.setattr(deploy_config, "update_source", lambda mutate: mutate({}))
        own = "-----BEGIN CERTIFICATE-----\nthe bundled one\n-----END CERTIFICATE-----"
        monkeypatch.setattr(
            deploy_config.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout=own, stderr=""),
        )
        monkeypatch.setattr(deploy_config, "read_certificate", lambda text: text.strip())
        source = self._model(placement.DEFAULT_HOST)

        assert deploy_config.ensure_database_authority(source) == "generated"
        assert source["database"]["tls"]["ca_certificate"] == own

    def test_the_clearing_reaches_the_file_every_other_reader_opens(self, monkeypatch):
        """The check, the Configurator and the next deploy read source.json.

        The authority read from the bundled container is deliberately not written
        back --- it is re-read each deploy so a regenerated certificate is followed.
        Clearing the old server's is the opposite case: left in the file, it outlives
        the run that moved off that server and every reader keeps refusing.
        """
        monkeypatch.setattr(deploy_config, "valid_certificate", lambda _pem: True)
        monkeypatch.setattr(
            deploy_config.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr=""),
        )
        stored = {"database": {"tls": {"ca_certificate": self.ANOTHER_SERVERS_CA}}}
        monkeypatch.setattr(
            deploy_config, "update_source", lambda mutate: mutate(stored)
        )

        deploy_config.ensure_database_authority(self._model(placement.DEFAULT_HOST))

        assert stored["database"]["tls"]["ca_certificate"] == ""


class TestTheBundledServersOwnAdministrator:
    """The container's root password, and the account a researcher names.

    Two servers, two administrators. Conflating them is what made switching
    placement a one-way trip: the value the bundled server was created with is not
    retypeable, and the wizard was writing over it every time a study named
    somebody else's database.
    """

    def test_the_container_password_is_generated_once(self):
        env = {}
        deploy_config.ensure_bundled_root_password(env)
        first = env["MYSQL_ROOT_PASSWORD"]
        assert len(first) > 12

        deploy_config.ensure_bundled_root_password(env)
        # Regenerating it would describe a server that no longer takes it.
        assert env["MYSQL_ROOT_PASSWORD"] == first

    def test_a_placeholder_counts_as_no_password(self):
        env = {"MYSQL_ROOT_PASSWORD": "CHANGE_ME"}
        deploy_config.ensure_bundled_root_password(env)
        assert env["MYSQL_ROOT_PASSWORD"] != "CHANGE_ME"

    def test_the_wizard_writes_the_administrator_and_not_the_container(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / "request.env"
        monkeypatch.setattr(sys, "argv", ["write_request_env.py", str(target)])
        monkeypatch.setattr(
            write_request_env.json,
            "load",
            lambda _stream: {
                "db_placement": "external",
                "db_host": "db.example.edu",
                "android_dataflow": "webservice",
                "public_host": "study.example.org",
                "mysql_root_password": "typed-into-the-form",
            },
        )
        write_request_env.main()
        written = target.read_text(encoding="utf-8")

        assert "DB_ADMIN_PASSWORD=typed-into-the-form" in written
        assert "MYSQL_ROOT_PASSWORD" not in written


class TestEveryBootstrappedAccountLosesItsSeed:
    """db/00-bootstrap.sql creates accounts with a word this repository publishes.

    That is survivable only while the server is reachable over its socket alone,
    which is the whole of the initialisation and not a moment longer: the port it
    opens next is bound to every address a participant might reach it from on the
    direct dataflow. So the script beside it has to name every account the bootstrap
    creates --- one added to the SQL and forgotten here would sit on a network
    holding a password anybody can read in the source.
    """

    ROOT = pathlib.Path(__file__).resolve().parent.parent

    def _accounts(self, text):
        return set(re.findall(r"CREATE USER IF NOT EXISTS '([a-z_]+)'@", text))

    def test_the_password_script_names_every_one_of_them(self):
        created = self._accounts((self.ROOT / "db" / "00-bootstrap.sql").read_text())
        script = (self.ROOT / "db" / "zz-account-passwords.sh").read_text()
        altered = set(re.findall(r"ALTER USER '([a-z_]+)'@", script))
        assert created and created == altered

    def test_it_refuses_rather_than_keeping_one(self):
        script = (self.ROOT / "db" / "zz-account-passwords.sh").read_text()
        assert "exit 1" in script
        assert "keeping the seed password" not in script

    def test_it_sorts_after_the_bootstrap_that_creates_them(self):
        # MySQL runs /docker-entrypoint-initdb.d in name order, so an account is
        # only there to be altered if the file creating it comes first.
        names = sorted(p.name for p in (self.ROOT / "db").glob("*") if p.is_file())
        assert names.index("zz-account-passwords.sh") > names.index("00-bootstrap.sql")
