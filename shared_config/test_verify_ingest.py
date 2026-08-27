"""Tests for the pre-enrolment ingest self-test.

The check exists because a study can be deployed, healthy and serving while
delivering nothing, and the only actor that would notice is a participant's phone
weeks later. What is worth holding onto here is the shape of its answers rather
than the network it walks: a refusal and an unreachable endpoint are different
failures and have to read differently, the row it posts has to be the row a client
posts, and whatever the outcome the probe has to leave the study exactly as it
found it --- including the caches, which are keyed by device and would otherwise
carry a phantom participant's figures for the life of the deployment.
"""

import json
import pathlib
import sys
import urllib.error
import urllib.parse
from types import SimpleNamespace

import pytest

SETUP = pathlib.Path(__file__).resolve().parent.parent / "setup"
sys.path.insert(0, str(SETUP))

import verify_ingest  # noqa: E402


class _Response:
    """Enough of an HTTP response for the reader under test."""

    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body.encode()

    def read(self, _limit=None):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class TestTheProbeDevice:
    """probe_device_id: a name that cannot collide with a participant's."""

    def test_a_run_never_repeats_a_name(self):
        assert verify_ingest.probe_device_id() != verify_ingest.probe_device_id()

    def test_the_name_says_what_put_it_there(self):
        # A row that outlives a killed run is found and removed by this prefix, so
        # it is what makes an interrupted check recoverable rather than a mystery.
        assert verify_ingest.probe_device_id().startswith("setup-self-test-")


class TestTheWindowTheProbeOpens:
    """The gate admits a device on the strength of where its window came from."""

    def test_the_probe_uses_a_source_the_gate_trusts(self):
        gate = (
            pathlib.Path(__file__).resolve().parent.parent
            / "aware-micro-server/src/main/kotlin/com/awareframework/micro/EnrolmentGate.kt"
        ).read_text(encoding="utf-8")
        # Read from the gate rather than restated here: a probe whose window the
        # gate does not trust is refused, and the check then reports a broken
        # ingest path for a study whose ingest path works.
        assert f'"{verify_ingest.PROBE_JOIN_SOURCE}"' in gate


class TestReadingTheStudyConfiguration:
    """fetch_study_config: what a joining phone gets, and what it would refuse."""

    def test_a_served_configuration_passes_and_is_described(self, monkeypatch):
        body = json.dumps({"sensors": [{"setting": "a"}, {"setting": "b"}]})
        monkeypatch.setattr(
            verify_ingest.urllib.request, "urlopen", lambda *a, **k: _Response(200, body)
        )
        ok, detail = verify_ingest.fetch_study_config("http://host/2/key")
        assert ok
        assert "2 settings" in detail

    def test_html_at_the_join_url_fails_rather_than_counting_as_reachable(self, monkeypatch):
        # A 200 is not the question. The client reads this as JSON, so a landing
        # page here is an endpoint that answers and a study nobody can join.
        monkeypatch.setattr(
            verify_ingest.urllib.request,
            "urlopen",
            lambda *a, **k: _Response(200, "<html>join</html>"),
        )
        ok, detail = verify_ingest.fetch_study_config("http://host/2/key")
        assert not ok
        assert "study configuration" in detail

    def test_json_without_a_study_block_fails(self, monkeypatch):
        monkeypatch.setattr(
            verify_ingest.urllib.request,
            "urlopen",
            lambda *a, **k: _Response(200, json.dumps({"unrelated": 1})),
        )
        ok, _ = verify_ingest.fetch_study_config("http://host/2/key")
        assert not ok

    def test_an_unreachable_host_names_the_url(self, monkeypatch):
        def refuse(*_a, **_k):
            raise urllib.error.URLError("Connection refused")

        monkeypatch.setattr(verify_ingest.urllib.request, "urlopen", refuse)
        ok, detail = verify_ingest.fetch_study_config("http://host/2/key")
        assert not ok
        assert "http://host/2/key" in detail


class TestPostingTheRow:
    """post_probe_row: the request a client makes, and the answers it can get."""

    def _capture(self, monkeypatch, response):
        sent = {}

        def urlopen(request, timeout=None):
            sent["url"] = request.full_url
            sent["body"] = request.data.decode()
            sent["content_type"] = request.get_header("Content-type")
            if isinstance(response, Exception):
                raise response
            return response

        monkeypatch.setattr(verify_ingest.urllib.request, "urlopen", urlopen)
        return sent

    def test_the_row_is_posted_the_way_the_client_posts_one(self, monkeypatch):
        sent = self._capture(monkeypatch, _Response(200, ""))
        ok, _ = verify_ingest.post_probe_row("http://host/2/key/aware_device/insert", "d1", 111)
        assert ok
        # The two field names and the form encoding are the client's, so the
        # request under test is the request a phone makes rather than one the
        # server happens also to accept.
        assert sent["content_type"] == "application/x-www-form-urlencoded"
        assert "device_id=d1" in sent["body"]
        assert "data=" in sent["body"]

    def test_the_posted_rows_carry_the_probes_own_device(self, monkeypatch):
        sent = self._capture(monkeypatch, _Response(200, ""))
        verify_ingest.post_probe_row("http://host/2/key/aware_device/insert", "d1", 111)
        payload = json.loads(urllib.parse.parse_qs(sent["body"])["data"][0])
        assert payload[0]["device_id"] == "d1"
        assert payload[0]["timestamp"] == 111

    def test_a_refusal_says_the_gate_refused_rather_than_the_path_is_broken(self, monkeypatch):
        self._capture(
            monkeypatch,
            urllib.error.HTTPError("u", 403, "Forbidden", {}, None),
        )
        ok, detail = verify_ingest.post_probe_row("http://host/i", "d1", 1)
        assert not ok
        # The distinction is the whole value of the check: a 403 means the request
        # arrived, was parsed and was judged against the registry, so the network
        # and the certificate are not what needs fixing.
        assert "enrolment gate" in detail
        assert "reachable" in detail

    def test_a_database_that_could_not_take_it_is_its_own_answer(self, monkeypatch):
        self._capture(
            monkeypatch,
            urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None),
        )
        ok, detail = verify_ingest.post_probe_row("http://host/i", "d1", 1)
        assert not ok
        assert "study database could not" in detail


class _FakeMysql:
    """Records the statements it is given and answers the count it is told to."""

    def __init__(self, remaining="0", fail=False):
        self.statements = []
        self._remaining = remaining
        self._fail = fail

    def execute(self, sql):
        self.statements.append(sql)
        return SimpleNamespace(
            returncode=1 if self._fail else 0,
            stderr="denied" if self._fail else "",
        )

    def scalar(self, sql):
        self.statements.append(sql)
        return self._remaining


class TestTheProbeLeavesNothingBehind:
    """clear_probe: what the probe touched, and how it is taken back out."""

    def test_every_table_the_probe_reaches_is_cleared(self):
        sql = _FakeMysql()
        ok, _ = verify_ingest.clear_probe(sql, "d1")
        assert ok
        written = "\n".join(sql.statements)
        for table in (verify_ingest.PROBE_TABLE, "device_enrolment", *verify_ingest.DERIVED_TABLES):
            assert f"`{table}`" in written

    def test_the_caches_are_cleared_by_device(self):
        # Both are keyed by device, which is what makes removing a probe's figures
        # exact: a real participant's rows in the same sensor and the same hour
        # are a different key and stay where they are.
        sql = _FakeMysql()
        verify_ingest.clear_probe(sql, "d1")
        for table in ("record_counts", "coverage_hourly"):
            assert any(
                f"`{table}`" in statement and "`device_id` = 'd1'" in statement
                for statement in sql.statements
            )

    def test_the_refusal_a_turned_away_probe_leaves_is_cleared_too(self):
        # A refused probe writes no row and still leaves a record, which is shown
        # beside the client logs. It belongs to the probe, so it goes with it.
        sql = _FakeMysql()
        verify_ingest.clear_probe(sql, "d1")
        assert any("`refusals`" in statement for statement in sql.statements)

    def test_rows_still_present_are_reported_with_the_name_to_remove(self):
        sql = _FakeMysql(remaining="2")
        ok, detail = verify_ingest.clear_probe(sql, "d1")
        assert not ok
        assert "'d1'" in detail

    def test_a_failed_delete_says_what_to_remove_by_hand(self):
        sql = _FakeMysql(fail=True)
        ok, detail = verify_ingest.clear_probe(sql, "d1")
        assert not ok
        assert "'d1'" in detail


class TestTheResultShape:
    """What the wizard and the terminal both read."""

    def test_a_skipped_check_is_not_a_failure(self):
        # An HTTP deployment presents no certificate. That is worth saying and is
        # not a reason to tell a researcher their ingest path does not work.
        entry = verify_ingest.check("certificate", True, "no certificate", skipped=True)
        assert entry["ok"] and entry["skipped"]

    def test_every_check_carries_a_detail(self):
        entry = verify_ingest.check("endpoint", False, "refused")
        assert set(entry) == {"name", "ok", "skipped", "detail"}
        assert entry["detail"]
