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


class TestWhenEncryptionIsTheDefault:
    """placement.requires_tls: derived from whether the connection leaves the host."""

    @pytest.mark.parametrize(
        "where,flow",
        [
            (placement.BUNDLED, dataflow.DIRECT),
            (placement.EXTERNAL, dataflow.DIRECT),
            (placement.EXTERNAL, dataflow.WEBSERVICE),
        ],
    )
    def test_a_connection_that_leaves_the_machine_is_encrypted(self, where, flow):
        assert placement.requires_tls(where, flow)
        # And the interface has a sentence for what turning it off would cost.
        assert placement.unencrypted_warning(where, flow)

    def test_a_hop_inside_one_machine_is_not_forced(self):
        # A bridge on one host and the internet are the same statement in a config
        # and not the same risk, so only one of them is made non-negotiable.
        assert not placement.requires_tls(placement.BUNDLED, dataflow.WEBSERVICE)
        assert placement.unencrypted_warning(placement.BUNDLED, dataflow.WEBSERVICE) is None

    def test_the_two_unsafe_cases_read_differently(self):
        # One exposes every participant's own network, the other the link between
        # two servers. A single generic caution would understate both.
        phones = placement.unencrypted_warning(placement.BUNDLED, dataflow.DIRECT)
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
        assert sorted(waiting) == sorted(deploy_config.WAITS_ON_BUNDLED_MYSQL)


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
