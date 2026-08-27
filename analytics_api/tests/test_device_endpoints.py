"""Endpoint tests over a stand-in database session.

The point is the wiring: which fields reach the response, how a study-only phone
is ordered, and that nothing from a config gets serialised. The SQL itself is
replaced - `_combined_last_seen_by_device` and friends are patched - so these run
without MySQL.
"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import devices as devices_router
from app.services import micro_config, study_config, study_state

ANDROID_DEVICE = "android-device-1"
STUDY_ONLY_DEVICE = "android-device-2"
IOS_DEVICE = "ios-device-1"

PARTICIPANT_PASSWORD = "participant-secret-9f2a"
OPENWEATHER_KEY = "owm-key-7d3e"

CONFIG = {
    "_id": "config-id-1",
    "updatedAt": "2026-02-01T00:00:00.000Z",
    "study_info": {"study_title": "Test study"},
    "database": {
        "database_password": PARTICIPANT_PASSWORD,
        "config_without_password": True,
        "require_ssl": False,
    },
    "sensors": [
        {"setting": "status_wifi", "value": True},
        {"setting": "enable_config_update", "value": False},
        {"setting": "plugin_openweather_api_key", "value": OPENWEATHER_KEY},
    ],
}

CONSENT = "consent given: enabled=[Location, Wi-Fi] declined=[Bluetooth]"


def study_row(_id, timestamp, device_id, message, config=None, **doubles):
    return SimpleNamespace(
        _id=_id,
        timestamp=timestamp,
        device_id=device_id,
        study_compliance=message,
        study_config=json.dumps(config) if config else None,
        double_join=doubles.get("double_join", 0),
        double_updated=doubles.get("double_updated", 0),
        double_exit=doubles.get("double_exit", 0),
    )


STUDY_ROWS = [
    study_row(1, 1_000.0, ANDROID_DEVICE, "updated study", CONFIG, double_join=900.0),
    # Reported twice, as the client does.
    study_row(2, 2_000.0, ANDROID_DEVICE, CONSENT, double_join=900.0),
    study_row(3, 2_000.0, ANDROID_DEVICE, CONSENT, double_join=900.0),
    study_row(4, 3_000.0, STUDY_ONLY_DEVICE, "joined study", double_join=3_000.0),
]


@pytest.fixture(autouse=True)
def _deployed_config(monkeypatch, tmp_path):
    """A deployed config the fixture phone matches exactly."""
    path = tmp_path / "studyConfig.json"
    path.write_text(json.dumps(CONFIG), encoding="utf-8")
    monkeypatch.setenv(study_config.CONFIG_PATH_ENV, str(path))
    monkeypatch.setenv(micro_config.CONFIG_PATH_ENV, str(tmp_path / "absent.json"))
    study_config.clear_cache()
    micro_config.clear_cache()
    yield
    study_config.clear_cache()
    micro_config.clear_cache()


@pytest.fixture(autouse=True)
def _database(monkeypatch):
    """Replace every query helper the device router uses."""

    async def last_seen(db, models, count_model=None):
        if models and models[0] is devices_router.AndroidDevice:
            return {ANDROID_DEVICE: 5_000.0}
        return {IOS_DEVICE: 9_000.0}

    async def metadata(db, model):
        if model is devices_router.AndroidDevice:
            return {
                ANDROID_DEVICE: {
                    "device_id": ANDROID_DEVICE,
                    "manufacturer": "Google",
                    "model": "Pixel 8",
                    "timestamp": 5_000.0,
                }
            }
        return {IOS_DEVICE: {"device_id": IOS_DEVICE, "label": "Test iPhone"}}

    async def contacts(db, model):
        if model is devices_router.AndroidDeviceContact:
            return {ANDROID_DEVICE: 5_500}
        return {IOS_DEVICE: 9_500}

    async def study_rows(db, device_id=None):
        if device_id is None:
            return STUDY_ROWS
        return [row for row in STUDY_ROWS if row.device_id == device_id]

    async def best_device_row(db, model, device_id):
        return None

    async def counts_for_device(db, count_model, device_id):
        # Empty cache → every stream reads as zero with no per-sensor query.
        return {}

    async def enrolment_windows(db, device_id=None):
        # No stored windows, which is the shape a deployment has before the
        # first refresh. test_enrolment_endpoint.py covers the filled table.
        return {}

    async def first_record_by_device(db, coverage_model):
        # An empty rollup, so `first_seen` reads as unknown rather than invented.
        return {}

    monkeypatch.setattr(devices_router, "_combined_last_seen_by_device", last_seen)
    monkeypatch.setattr(devices_router, "_device_metadata_by_device", metadata)
    monkeypatch.setattr(devices_router, "_last_contact_by_device", contacts)
    monkeypatch.setattr(devices_router, "_android_study_rows", study_rows)
    monkeypatch.setattr(devices_router, "_best_device_row", best_device_row)
    monkeypatch.setattr(devices_router, "_enrolment_windows", enrolment_windows)
    monkeypatch.setattr(
        devices_router.enrolment, "first_record_by_device", first_record_by_device
    )
    monkeypatch.setattr(
        devices_router.record_counts, "counts_for_device", counts_for_device
    )

    async def no_exclusions(db, model):
        # Nothing taken out of the analysis, so a row's `excluded` reads as absent.
        return {}

    monkeypatch.setattr(devices_router.exclusions, "exclusions", no_exclusions)

    async def session():
        yield SimpleNamespace()

    app.dependency_overrides[devices_router.get_android_db] = session
    app.dependency_overrides[devices_router.get_ios_db] = session
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def android_devices(client):
    return client.get("/devices").json()["android"]


def by_id(devices, device_id):
    return next(device for device in devices if device["device_id"] == device_id)


def test_a_first_data_window_is_not_mistaken_for_recorded_enrolment():
    windows = [{"join_source": devices_router.enrolment.FIRST_DATA}]

    assert devices_router._has_recorded_enrolment(windows) is False


def test_a_phone_reported_join_is_recognised():
    windows = [{"join_source": devices_router.enrolment.STUDY_EVENT}]

    assert devices_router._has_recorded_enrolment(windows) is True


# --- the device list -------------------------------------------------------


def test_the_list_includes_a_phone_that_only_ever_joined(client):
    devices = android_devices(client)

    assert {device["device_id"] for device in devices} == {
        ANDROID_DEVICE,
        STUDY_ONLY_DEVICE,
    }


def test_a_phone_that_never_uploaded_has_no_last_seen(client):
    device = by_id(android_devices(client), STUDY_ONLY_DEVICE)

    assert device["last_seen"] is None
    assert device["study"]["enrollment_status"] == "in_study"


def test_phones_that_never_uploaded_sort_last(client):
    """The old sort key raised on a null last_seen."""
    devices = android_devices(client)

    assert [device["device_id"] for device in devices] == [
        ANDROID_DEVICE,
        STUDY_ONLY_DEVICE,
    ]


def test_the_list_carries_a_compact_study_summary(client):
    summary = by_id(android_devices(client), ANDROID_DEVICE)["study"]

    assert summary == {
        "enrollment_status": "in_study",
        "last_study_event_at": 2_000.0,
        "config_status": "current",
        "diff_count": 0,
    }


def test_the_list_keeps_sensor_uploads_and_study_activity_apart(client):
    device = by_id(android_devices(client), ANDROID_DEVICE)

    assert device["last_seen"] == 5_000.0
    assert device["last_sensor_data"] == 5_000.0
    assert device["last_contact"] == 5_500
    assert device["study"]["last_study_event_at"] == 2_000.0


def test_a_study_only_phone_has_neither_contact_nor_sensor_data(client):
    device = by_id(android_devices(client), STUDY_ONLY_DEVICE)

    assert device["last_contact"] is None
    assert device["last_sensor_data"] is None


def test_iphones_carry_no_study_summary(client):
    ios = client.get("/devices").json()["ios"]

    assert [device["device_id"] for device in ios] == [IOS_DEVICE]
    assert "study" not in ios[0]


# --- the device detail ----------------------------------------------------


def test_android_detail_reports_the_derived_state(client):
    detail = client.get(f"/devices/android/{ANDROID_DEVICE}").json()

    assert detail["study"]["enrollment_status"] == "in_study"
    assert detail["study"]["approved_consents"] == ["Location", "Wi-Fi"]
    assert detail["study"]["declined_consents"] == ["Bluetooth"]
    assert detail["study"]["config_id"] == "config-id-1"
    assert detail["config_diff"]["config_status"] == "current"
    assert detail["config_diff"]["config_update_enabled"] is False


def test_android_detail_returns_the_deduplicated_timeline(client):
    detail = client.get(f"/devices/android/{ANDROID_DEVICE}").json()
    events = detail["study_events"]

    assert [event["kind"] for event in events] == ["consent", "updated"]
    assert events[0]["occurrences"] == 2
    assert detail["study"]["duplicate_row_count"] == 1


def test_android_detail_still_returns_the_streams(client):
    detail = client.get(f"/devices/android/{ANDROID_DEVICE}").json()

    assert detail["platform"] == "android"
    assert [stream["key"] for stream in detail["streams"]] == list(
        devices_router.ANDROID_STREAMS
    )


def test_a_phone_with_no_study_rows_reports_unknown(client):
    detail = client.get("/devices/android/never-heard-of-it").json()

    assert detail["study"]["enrollment_status"] == "unknown"
    assert detail["config_diff"]["config_status"] == "unknown"
    assert detail["config_diff"]["status_reason"] == "no_device_config"
    assert detail["study_events"] == []


def test_iphone_detail_has_no_study_fields(client):
    detail = client.get(f"/devices/ios/{IOS_DEVICE}").json()

    assert "study" not in detail
    assert "config_diff" not in detail


def test_an_unknown_platform_is_rejected(client):
    assert client.get("/devices/windows-phone/whatever").status_code == 404


# --- the timeline endpoint -------------------------------------------------


def test_study_events_are_paginated(client):
    first = client.get(
        f"/devices/android/{ANDROID_DEVICE}/study-events", params={"limit": 1}
    ).json()
    second = client.get(
        f"/devices/android/{ANDROID_DEVICE}/study-events",
        params={"limit": 1, "offset": 1},
    ).json()

    assert [event["kind"] for event in first] == ["consent"]
    assert [event["kind"] for event in second] == ["updated"]


def test_study_events_for_an_unknown_device_are_empty(client):
    response = client.get("/devices/android/never-heard-of-it/study-events")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("limit", [0, 501, -1])
def test_the_event_limit_is_enforced(client, limit):
    response = client.get(
        f"/devices/android/{ANDROID_DEVICE}/study-events", params={"limit": limit}
    )

    assert response.status_code == 422


def test_the_timeline_route_is_not_shadowed_by_the_detail_route(client):
    """`/{platform}/{device_id}` must not swallow the three-segment path."""
    response = client.get(f"/devices/android/{ANDROID_DEVICE}/study-events")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


# --- withdrawal -----------------------------------------------------------


def test_withdrawal_passes_the_participants_own_date_to_the_window(monkeypatch, client):
    async def close_window(db, model, device_id, left_at):
        assert device_id == ANDROID_DEVICE
        assert left_at == 12_345
        return {
            "device_id": device_id,
            "joined_at": 1_000,
            "left_at": left_at,
            "join_source": devices_router.enrolment.STUDY_EVENT,
            "left_source": devices_router.enrolment.MANUAL,
        }

    monkeypatch.setattr(devices_router.enrolment, "close_window", close_window)

    response = client.post(
        f"/devices/android/{ANDROID_DEVICE}/withdraw",
        json={"left_at": 12_345},
    )

    assert response.status_code == 200
    assert response.json()["window"]["left_at"] == 12_345


def test_withdrawal_without_a_window_is_refused(monkeypatch, client):
    async def close_window(db, model, device_id, left_at):
        return None

    monkeypatch.setattr(devices_router.enrolment, "close_window", close_window)

    response = client.post(f"/devices/android/{ANDROID_DEVICE}/withdraw", json={})

    assert response.status_code == 404


def test_rejoin_hands_the_device_back_to_derivation(monkeypatch, client):
    refreshed = False

    async def reopen(db, model, device_id):
        assert device_id == ANDROID_DEVICE
        return True

    async def refresh(db, model, coverage_model, study_model):
        nonlocal refreshed
        refreshed = True
        assert model is devices_router.AndroidDeviceEnrolment
        assert coverage_model is devices_router.AndroidCoverageHourly
        assert study_model is devices_router.AndroidAwareStudy
        return {"devices": 1, "windows": 1, "researcher_owned": 0}

    monkeypatch.setattr(devices_router.enrolment, "reopen", reopen)
    monkeypatch.setattr(devices_router.enrolment, "refresh", refresh)

    response = client.post(f"/devices/android/{ANDROID_DEVICE}/rejoin", json={})

    assert response.status_code == 200
    assert response.json() == {"status": "reopened", "device_id": ANDROID_DEVICE}
    assert refreshed is True


# --- requirements ---------------------------------------------------------


def test_requirements_come_from_the_two_configs(client):
    body = client.get("/study/requirements").json()

    assert body["android"]["available"] is True
    assert "wifi" in {
        item["sensor_key"] for item in body["android"]["sensors"] if item["required"]
    }
    # The micro-server config is absent in this fixture.
    assert body["ios"]["available"] is False
    assert body["ios"]["sensors"] == []


# --- nothing leaks --------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/devices",
        f"/devices/android/{ANDROID_DEVICE}",
        f"/devices/android/{ANDROID_DEVICE}/study-events",
        "/study/requirements",
    ],
)
def test_no_endpoint_serialises_a_credential(client, path):
    body = client.get(path).text

    assert PARTICIPANT_PASSWORD not in body
    assert OPENWEATHER_KEY not in body
    assert "database_password" not in body
    assert "rootPassword" not in body


def test_the_detail_never_returns_the_raw_config(client):
    body = client.get(f"/devices/android/{ANDROID_DEVICE}").text

    # The config version is fine to expose; the config body is not.
    assert "config-id-1" in body
    assert "status_wifi" not in body


def test_the_fingerprint_stays_server_side(client):
    body = client.get(f"/devices/android/{ANDROID_DEVICE}").json()

    assert "config_fingerprint" not in body["study"]
    assert all("config_fingerprint" not in event for event in body["study_events"])


# --- the derivation is shared, not reimplemented --------------------------


def test_the_endpoint_and_the_service_agree(client):
    detail = client.get(f"/devices/android/{ANDROID_DEVICE}").json()
    state = study_state.derive_study_state(
        [row for row in STUDY_ROWS if row.device_id == ANDROID_DEVICE]
    )

    assert detail["study"]["enrollment_status"] == state.summary.enrollment_status
    assert len(detail["study_events"]) == state.summary.event_count


# --- one phone's bad data must not break the list -------------------------


ODD_CONFIGS = [
    {"_id": {"nested": "object"}, "sensors": []},
    {"_id": 12345, "updatedAt": 678, "sensors": []},
    {"_id": "x", "sensors": {"status_wifi": True}},
    {"_id": "x", "study_info": ["a list"], "database": "a string", "sensors": []},
]


@pytest.mark.parametrize("odd", ODD_CONFIGS)
def test_the_list_survives_a_phone_reporting_an_odd_config(client, monkeypatch, odd):
    """aware_studies.study_config comes from the phone, so its shape is untrusted."""
    rows = STUDY_ROWS + [
        study_row(99, 9_000.0, "odd-phone", "updated study", odd),
    ]

    async def study_rows(db, device_id=None):
        if device_id is None:
            return rows
        return [row for row in rows if row.device_id == device_id]

    monkeypatch.setattr(devices_router, "_android_study_rows", study_rows)

    response = client.get("/devices")

    assert response.status_code == 200
    devices = response.json()["android"]
    assert "odd-phone" in {device["device_id"] for device in devices}
    # The healthy phones are unaffected.
    assert by_id(devices, ANDROID_DEVICE)["study"]["config_status"] == "current"


@pytest.mark.parametrize("odd", ODD_CONFIGS)
def test_the_detail_survives_a_phone_reporting_an_odd_config(client, monkeypatch, odd):
    rows = [study_row(99, 9_000.0, "odd-phone", "updated study", odd)]

    async def study_rows(db, device_id=None):
        return rows if device_id in (None, "odd-phone") else []

    monkeypatch.setattr(devices_router, "_android_study_rows", study_rows)

    detail = client.get("/devices/android/odd-phone")
    events = client.get("/devices/android/odd-phone/study-events")

    assert detail.status_code == 200
    assert events.status_code == 200
    assert detail.json()["study"]["enrollment_status"] == "in_study"


def test_a_date_before_the_device_joined_says_so(monkeypatch, client):
    """Two different refusals. A date outside the enrolment is a typo to correct;
    no enrolment at all is a finding about the device — and the message has to say
    which, since the first one used to claim the device had never enrolled."""

    async def close_window(db, model, device_id, left_at):
        return None

    async def enrolment_windows(db, device_id=None):
        return {ANDROID_DEVICE: [{"joined_at": 5_000, "left_at": None}]}

    monkeypatch.setattr(devices_router.enrolment, "close_window", close_window)
    monkeypatch.setattr(devices_router, "_enrolment_windows", enrolment_windows)

    response = client.post(
        f"/devices/android/{ANDROID_DEVICE}/withdraw", json={"left_at": 1_000}
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "outside this device's enrolment" in detail
    # The join time, so the researcher can pick a date that works.
    assert "1970" in detail
