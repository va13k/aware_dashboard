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

import pathlib
import sys

import pytest

from shared_config import dataflow, placement

SETUP = pathlib.Path(__file__).resolve().parent.parent / "setup"
sys.path.insert(0, str(SETUP))

import deploy_config  # noqa: E402
import write_request_env  # noqa: E402

from shared_config import database  # noqa: E402


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

    def test_the_backup_job_goes_with_it(self):
        """It dumps as root on 3306 without asking for encryption, which is a
        description of the bundled database and of nothing else. Left in, it would
        fail against a server it cannot reach for the length of the study."""
        assert "mysql-backup: !reset null" in deploy_config.build_compose_override()

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
            set(deploy_config.WAITS_ON_BUNDLED_MYSQL)
            | set(deploy_config.BUNDLED_ONLY_SERVICES) - {"mysql"}
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
