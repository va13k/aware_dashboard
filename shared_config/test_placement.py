"""Tests for where the study database runs, as a choice with consequences.

Three things are worth holding onto. The placement is read from the host the study
declares rather than kept as a field beside it, so the two can never disagree about
which database a study is using. The one combination that cannot be honoured is
refused where the researcher gives it, not discovered when the coverage grid stays
empty. And taking the bundled database out of a deployment means taking the waits on
it out too --- a service kept out of a compose file is still depended on, and compose
starts a dependency whether or not anybody asked for it.
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


class TestWhatCannotBeHonoured:
    """placement.unsupported_reason: the combination that is refused, and why."""

    def test_external_with_phones_on_the_database_is_refused(self):
        reason = placement.unsupported_reason(placement.EXTERNAL, dataflow.DIRECT)
        assert reason is not None
        # The sentence has to carry the consequence rather than the word
        # "unsupported", which invites someone to go looking for the setting that
        # turns it on.
        assert "every participant's phone" in reason

    def test_external_through_the_server_is_offered(self):
        assert placement.unsupported_reason(placement.EXTERNAL, dataflow.WEBSERVICE) is None

    @pytest.mark.parametrize("choice", [dataflow.DIRECT, dataflow.WEBSERVICE])
    def test_the_bundled_database_is_offered_either_way(self, choice):
        # Nothing outside this machine is involved, so the dataflow does not bear on it.
        assert placement.unsupported_reason(placement.BUNDLED, choice) is None

    def test_a_placement_nothing_recognises_is_refused(self):
        assert placement.unsupported_reason("elsewhere", dataflow.WEBSERVICE) is not None

    def test_validate_reports_a_study_that_cannot_be_run(self):
        source = {
            "database": {"host": "db.example.edu"},
            "deployment": {"dataflow": {"android": dataflow.DIRECT}},
        }
        assert placement.validate(source)

    def test_validate_is_empty_for_a_coherent_study(self):
        source = {
            "database": {"host": "db.example.edu"},
            "deployment": {"dataflow": {"android": dataflow.WEBSERVICE}},
        }
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

    def test_external_with_the_direct_dataflow_is_refused(self):
        with pytest.raises(SystemExit):
            write_request_env.clean_placement("external", dataflow.DIRECT, "db.example.edu")

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
