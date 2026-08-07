import json
from types import SimpleNamespace

import pytest

from app.models import AndroidAwareStudy
from app.services import study_config, study_state

DEVICE = "ca14d3f3-0000-4000-8000-000000000001"

CONSENT_CATEGORIES = "Location, Wi-Fi, Bluetooth, Telephony, Applications usage"
INITIAL_CONSENT = f"consent given: enabled=[{CONSENT_CATEGORIES}] declined=[]"
UPDATE_CONSENT = (
    "consent given (study update): "
    f"enabled=[Location, Wi-Fi] declined=[Bluetooth, Keyboard masked text]"
)

REJOIN = "rejoined study"
# What older clients wrote for the same thing; those rows are still stored.
LEGACY_REJOIN = "collection resumed after password re-authentication"

PARTICIPANT_PASSWORD = "participant-secret-9f2a"
OPENWEATHER_KEY = "owm-key-7d3e"


def row(
    _id=1,
    timestamp=1_000.0,
    device_id=DEVICE,
    study_compliance="",
    study_config=None,
    double_join=0,
    double_updated=0,
    double_exit=0,
):
    return SimpleNamespace(
        _id=_id,
        timestamp=timestamp,
        device_id=device_id,
        study_compliance=study_compliance,
        study_config=study_config,
        double_join=double_join,
        double_updated=double_updated,
        double_exit=double_exit,
    )


def config_json(**overrides) -> str:
    config = {
        "_id": "config-id-1",
        "updatedAt": "2026-02-01T00:00:00.000Z",
        "study_info": {"study_title": "Test study"},
        "database": {
            "database_password": PARTICIPANT_PASSWORD,
            "config_without_password": True,
            "require_ssl": False,
        },
        "sensors": [
            {"setting": "status_accelerometer", "value": True},
            {"setting": "plugin_openweather_api_key", "value": OPENWEATHER_KEY},
        ],
    }
    config.update(overrides)
    return json.dumps(config)


# --- classification --------------------------------------------------------


@pytest.mark.parametrize(
    "message,expected",
    [
        ("updated study", study_state.UPDATED),
        ("quit study", study_state.LEFT),
        # "attempt to quit study" contains "quit study" but is not an exit.
        ("attempt to quit study", study_state.OTHER),
        ("Attempt to quit study", study_state.OTHER),
        ("joined study", study_state.JOINED),
        (REJOIN, study_state.REJOINED),
        (LEGACY_REJOIN, study_state.REJOINED),
        ("Rejoined Study", study_state.REJOINED),
        (INITIAL_CONSENT, study_state.CONSENT),
        (UPDATE_CONSENT, study_state.CONSENT),
        ("Updated Study", study_state.UPDATED),
        ("something the client added later", study_state.OTHER),
        ("", study_state.OTHER),
    ],
)
def test_classify_recognises_known_messages(message, expected):
    assert study_state.classify(message, None, None) == expected


def test_an_empty_message_falls_back_to_the_numeric_fields():
    assert study_state.classify("", None, 1_000.0) == study_state.JOINED
    assert study_state.classify("", 2_000.0, None) == study_state.LEFT
    # An exit and a join on the same row: leaving is the decisive one.
    assert study_state.classify("", 2_000.0, 1_000.0) == study_state.LEFT


# --- consent ---------------------------------------------------------------


def test_initial_consent_is_parsed():
    approved, declined, context = study_state.parse_consent(INITIAL_CONSENT)

    assert approved == [
        "Location",
        "Wi-Fi",
        "Bluetooth",
        "Telephony",
        "Applications usage",
    ]
    assert declined == []
    assert context == study_state.CONSENT_INITIAL


def test_study_update_consent_is_parsed():
    approved, declined, context = study_state.parse_consent(UPDATE_CONSENT)

    assert approved == ["Location", "Wi-Fi"]
    assert declined == ["Bluetooth", "Keyboard masked text"]
    assert context == study_state.CONSENT_STUDY_UPDATE


def test_a_consent_event_may_decline_everything():
    approved, declined, _ = study_state.parse_consent(
        "consent given (study update): enabled=[] declined=[Location, Wi-Fi]"
    )

    assert approved == []
    assert declined == ["Location", "Wi-Fi"]


# The exact `study_compliance` strings observed in the production backups, so a
# future tweak to CONSENT_PATTERN cannot silently stop capturing real consent.
@pytest.mark.parametrize(
    "message,approved,declined,context",
    [
        (
            "consent given (study update): enabled=[Location, Wi-Fi, Bluetooth, "
            "Telephony, Calls & messages, Applications usage, Keyboard masked text, "
            "Screenshots, Ambient Noise plugin, OpenWeather plugin] declined=[]",
            [
                "Location",
                "Wi-Fi",
                "Bluetooth",
                "Telephony",
                "Calls & messages",
                "Applications usage",
                "Keyboard masked text",
                "Screenshots",
                "Ambient Noise plugin",
                "OpenWeather plugin",
            ],
            [],
            study_state.CONSENT_STUDY_UPDATE,
        ),
        (
            "consent given: enabled=[] declined=[Location]",
            [],
            ["Location"],
            study_state.CONSENT_INITIAL,
        ),
        (
            "consent given: enabled=[] declined=[]",
            [],
            [],
            study_state.CONSENT_INITIAL,
        ),
    ],
)
def test_real_consent_messages_are_captured(message, approved, declined, context):
    parsed = study_state.parse_consent(message)
    assert parsed == (approved, declined, context)


@pytest.mark.parametrize(
    "message",
    [
        "consent given: enabled=[Location",
        "consent given: declined=[Location]",
        "consent given",
        "consent given: enabled=Location declined=Wi-Fi",
    ],
)
def test_malformed_consent_does_not_parse(message):
    assert study_state.parse_consent(message) is None


def test_malformed_consent_stays_visible_without_inventing_values():
    broken = "consent given: enabled=[Location"
    state = study_state.derive_study_state([row(study_compliance=broken)])
    event = state.events[0]

    assert event.kind == study_state.OTHER
    assert event.message == broken
    assert event.approved_consents == []
    assert event.declined_consents == []
    assert state.summary.approved_consents == []
    assert state.summary.consent_context is None


def test_the_summary_reports_the_latest_consent():
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=1_000.0, study_compliance=INITIAL_CONSENT),
            row(_id=2, timestamp=2_000.0, study_compliance=UPDATE_CONSENT),
        ]
    )

    assert state.summary.approved_consents == ["Location", "Wi-Fi"]
    assert state.summary.declined_consents == ["Bluetooth", "Keyboard masked text"]
    assert state.summary.last_consent_at == 2_000.0
    assert state.summary.consent_context == study_state.CONSENT_STUDY_UPDATE


# --- deduplication ---------------------------------------------------------


def test_identical_rows_become_one_event():
    rows = [
        row(_id=index, timestamp=5_000.0, study_compliance=UPDATE_CONSENT)
        for index in range(1, 6)
    ]
    state = study_state.derive_study_state(rows)

    assert len(state.events) == 1
    assert state.events[0].occurrences == 5
    assert state.summary.event_count == 1
    assert state.summary.duplicate_row_count == 4


def test_events_differing_only_by_primary_key_are_the_same_event():
    state = study_state.derive_study_state(
        [
            row(_id=3, timestamp=1_000.0, study_compliance="updated study"),
            row(_id=99, timestamp=1_000.0, study_compliance="updated study"),
        ]
    )

    assert len(state.events) == 1


def test_repeated_events_at_different_times_stay_separate():
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=1_000.0, study_compliance="updated study"),
            row(_id=2, timestamp=2_000.0, study_compliance="updated study"),
        ]
    )

    assert len(state.events) == 2
    assert [event.occurrences for event in state.events] == [1, 1]


def test_events_are_returned_newest_first():
    state = study_state.derive_study_state(
        [
            row(_id=2, timestamp=2_000.0, study_compliance="quit study"),
            row(_id=1, timestamp=1_000.0, study_compliance="joined study"),
            row(_id=3, timestamp=3_000.0, study_compliance="updated study"),
        ]
    )

    assert [event.timestamp for event in state.events] == [3_000.0, 2_000.0, 1_000.0]
    assert state.summary.last_study_event == "updated study"
    assert state.summary.last_study_event_at == 3_000.0


# --- enrollment ------------------------------------------------------------


def test_a_phone_that_joined_and_quit_has_left():
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=1_000.0, study_compliance="joined study",
                double_join=1_000.0),
            row(_id=2, timestamp=2_000.0, study_compliance="quit study",
                double_exit=2_000.0),
        ]
    )

    assert state.summary.enrollment_status == study_state.LEFT_STUDY
    assert state.summary.last_exit_at == 2_000.0
    assert state.summary.last_join_at == 1_000.0


def test_an_attempt_to_quit_does_not_mark_the_phone_as_left():
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=1_000.0, study_compliance="joined study",
                double_join=1_000.0),
            row(_id=2, timestamp=2_000.0,
                study_compliance="attempt to quit study"),
        ]
    )

    assert state.summary.enrollment_status == study_state.IN_STUDY
    assert state.summary.last_exit_at is None


@pytest.mark.parametrize(
    "message", ["joined study", REJOIN, LEGACY_REJOIN, "updated study", INITIAL_CONSENT]
)
def test_a_later_event_puts_a_phone_that_quit_back_in_the_study(message):
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=1_000.0, study_compliance="quit study",
                double_exit=1_000.0),
            row(_id=2, timestamp=2_000.0, study_compliance=message),
        ]
    )

    assert state.summary.enrollment_status == study_state.IN_STUDY


def test_an_exit_marker_counts_even_without_a_quit_message():
    state = study_state.derive_study_state(
        [row(timestamp=1_000.0, study_compliance="", double_exit=900.0)]
    )

    assert state.summary.enrollment_status == study_state.LEFT_STUDY


def test_a_log_with_no_membership_signal_stays_unknown():
    state = study_state.derive_study_state(
        [row(study_compliance="something the client added later")]
    )

    assert state.summary.enrollment_status == study_state.UNKNOWN


def test_a_phone_with_no_study_rows_is_unknown():
    state = study_state.derive_study_state([])

    assert state.summary.enrollment_status == study_state.UNKNOWN
    assert state.summary.last_study_event_at is None
    assert state.events == []
    assert state.installed_config is None


def test_an_unrecognised_event_does_not_overwrite_a_known_state():
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=1_000.0, study_compliance="quit study",
                double_exit=1_000.0),
            row(_id=2, timestamp=2_000.0, study_compliance="a brand new event type"),
        ]
    )

    assert state.summary.enrollment_status == study_state.LEFT_STUDY


# --- rejoin ----------------------------------------------------------------


def test_a_rejoin_row_names_when_collection_stopped():
    state = study_state.derive_study_state(
        [
            row(
                timestamp=60_000.0,
                study_compliance=REJOIN,
                double_updated=5_000.0,
            )
        ]
    )

    assert state.summary.last_rejoin_pause_started_at == 5_000.0
    assert state.summary.last_rejoin_at == 60_000.0
    assert state.summary.last_rejoin_pause_ms == 55_000.0


def test_a_rejoin_is_paired_with_the_update_sharing_its_join_marker():
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=1_000.0, study_compliance="updated study",
                double_join=500.0),
            row(_id=2, timestamp=2_000.0, study_compliance="updated study",
                double_join=777.0),
            row(_id=3, timestamp=60_000.0,
                study_compliance=REJOIN, double_join=500.0),
        ]
    )

    assert state.summary.last_rejoin_pause_started_at == 1_000.0
    assert state.summary.last_rejoin_pause_ms == 59_000.0


def test_a_rejoin_falls_back_to_the_nearest_preceding_update():
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=1_000.0, study_compliance="updated study"),
            row(_id=2, timestamp=50_000.0, study_compliance="updated study"),
            row(_id=3, timestamp=60_000.0,
                study_compliance=REJOIN),
        ]
    )

    assert state.summary.last_rejoin_pause_started_at == 50_000.0
    assert state.summary.last_rejoin_pause_ms == 10_000.0


def test_a_rejoin_without_a_preceding_update_reports_no_pause():
    """What the real database holds: a rejoin with no update before it."""
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=60_000.0,
                study_compliance=REJOIN, double_join=500.0),
            row(_id=2, timestamp=70_000.0, study_compliance="updated study"),
        ]
    )

    assert state.summary.last_rejoin_at == 60_000.0
    assert state.summary.last_rejoin_pause_started_at is None
    assert state.summary.last_rejoin_pause_ms is None


def test_a_rejoin_earlier_than_its_update_reports_no_pause():
    state = study_state.derive_study_state(
        [
            row(
                timestamp=1_000.0,
                study_compliance=REJOIN,
                double_updated=9_000.0,
            )
        ]
    )

    assert state.summary.last_rejoin_pause_started_at == 9_000.0
    assert state.summary.last_rejoin_at == 1_000.0
    assert state.summary.last_rejoin_pause_ms is None


def test_the_latest_rejoin_wins():
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=10_000.0,
                study_compliance=REJOIN, double_updated=9_000.0),
            row(_id=2, timestamp=80_000.0,
                study_compliance=REJOIN, double_updated=20_000.0),
        ]
    )

    assert state.summary.last_rejoin_pause_started_at == 20_000.0
    assert state.summary.last_rejoin_pause_ms == 60_000.0


def test_no_rejoin_leaves_the_window_empty():
    state = study_state.derive_study_state(
        [row(study_compliance="updated study")]
    )

    assert state.summary.last_rejoin_pause_started_at is None
    assert state.summary.last_rejoin_at is None
    assert state.summary.last_rejoin_pause_ms is None


def test_a_rejoin_is_not_read_as_a_plain_join():
    """"rejoined study" contains "joined study" - order of checks matters."""
    state = study_state.derive_study_state([row(study_compliance=REJOIN)])

    assert state.events[0].kind == study_state.REJOINED


def test_a_rejoin_counts_as_the_latest_join():
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=1_000.0, study_compliance="joined study",
                double_join=900.0),
            row(_id=2, timestamp=2_000.0, study_compliance="quit study",
                double_exit=2_000.0),
            row(_id=3, timestamp=3_000.0, study_compliance=REJOIN,
                double_join=2_900.0),
        ]
    )

    assert state.summary.enrollment_status == study_state.IN_STUDY
    assert state.summary.last_join_at == 2_900.0
    assert state.summary.last_rejoin_at == 3_000.0


def test_both_rejoin_spellings_are_the_same_kind():
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=1_000.0, study_compliance=LEGACY_REJOIN),
            row(_id=2, timestamp=2_000.0, study_compliance=REJOIN),
        ]
    )

    assert [event.kind for event in state.events] == [
        study_state.REJOINED,
        study_state.REJOINED,
    ]


# --- timestamps ------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 0.0, -1, None, "", "not a number", float("nan")])
def test_unusable_timestamps_become_none(value):
    state = study_state.derive_study_state(
        [row(timestamp=value, study_compliance="updated study")]
    )

    assert state.events[0].timestamp is None
    assert state.summary.last_study_event_at is None


def test_numeric_strings_are_accepted():
    state = study_state.derive_study_state(
        [row(timestamp="1785856634012", study_compliance="updated study")]
    )

    assert state.events[0].timestamp == 1_785_856_634_012.0


def test_rows_are_ordered_by_time_then_primary_key():
    state = study_state.derive_study_state(
        [
            row(_id=9, timestamp=1_000.0, study_compliance="second"),
            row(_id=2, timestamp=1_000.0, study_compliance="first"),
            row(_id=1, timestamp=500.0, study_compliance="earliest"),
        ]
    )

    assert [event.message for event in state.events] == [
        "second",
        "first",
        "earliest",
    ]


# --- the phone's config ----------------------------------------------------


def test_the_installed_config_comes_from_the_last_event_that_reported_one():
    """Most events carry no config, so the latest event is the wrong place."""
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=1_000.0, study_compliance="updated study",
                study_config=config_json()),
            row(_id=2, timestamp=2_000.0, study_compliance=UPDATE_CONSENT,
                study_config=""),
            row(_id=3, timestamp=3_000.0, study_compliance=UPDATE_CONSENT,
                study_config=None),
        ]
    )

    assert state.installed_config is not None
    assert state.summary.config_id == "config-id-1"
    assert state.summary.config_updated_at == "2026-02-01T00:00:00.000Z"
    assert state.summary.config_fingerprint == study_config.content_fingerprint(
        json.loads(config_json())
    )


def test_a_newer_config_replaces_an_older_one():
    state = study_state.derive_study_state(
        [
            row(_id=1, timestamp=1_000.0, study_compliance="updated study",
                study_config=config_json()),
            row(_id=2, timestamp=2_000.0, study_compliance="updated study",
                study_config=config_json(_id="config-id-2")),
        ]
    )

    assert state.summary.config_id == "config-id-2"
    assert state.installed_config["_id"] == "config-id-2"


@pytest.mark.parametrize("value", [None, "", "   ", "{not json", "[1,2,3]", '"text"'])
def test_a_missing_or_unusable_config_is_not_a_failure(value):
    state = study_state.derive_study_state(
        [row(study_compliance="updated study", study_config=value)]
    )

    assert state.installed_config is None
    assert state.summary.config_id is None
    assert state.summary.config_fingerprint is None
    assert state.events[0].kind == study_state.UPDATED


def test_the_installed_config_is_redacted():
    state = study_state.derive_study_state(
        [row(study_compliance="updated study", study_config=config_json())]
    )
    serialised = json.dumps(state.installed_config)

    assert PARTICIPANT_PASSWORD not in serialised
    assert OPENWEATHER_KEY not in serialised
    assert state.installed_config["database"] == {
        "config_without_password": True,
        "require_ssl": False,
    }


def test_no_event_carries_a_config_body():
    """A timeline is serialised event by event; none of them may hold a config."""
    state = study_state.derive_study_state(
        [row(study_compliance="updated study", study_config=config_json())]
    )
    serialised = json.dumps([vars(event) for event in state.events])

    assert PARTICIPANT_PASSWORD not in serialised
    assert OPENWEATHER_KEY not in serialised
    assert "status_accelerometer" not in serialised


# --- against the real model ------------------------------------------------


def test_the_service_reads_orm_rows():
    """The fakes above are convenient; the service has to work on real rows."""
    rows = [
        AndroidAwareStudy(
            _id=1,
            timestamp=1_785_856_634_012.0,
            device_id=DEVICE,
            study_compliance="updated study",
            study_config=config_json(),
            double_join=1_785_856_634_018.0,
            double_updated=1_785_856_634_018.0,
            double_exit=0,
        ),
        AndroidAwareStudy(
            _id=2,
            timestamp=1_785_857_723_518.0,
            device_id=DEVICE,
            study_compliance=UPDATE_CONSENT,
            study_config="",
            double_join=1_785_856_634_018.0,
            double_updated=0,
            double_exit=0,
        ),
    ]
    state = study_state.derive_study_state(rows)

    assert state.summary.enrollment_status == study_state.IN_STUDY
    assert state.summary.config_id == "config-id-1"
    assert state.summary.approved_consents == ["Location", "Wi-Fi"]
    assert state.events[0].device_id == DEVICE


# --- configs a phone reported in an unexpected shape ----------------------


@pytest.mark.parametrize(
    "config_id",
    [{"nested": "object"}, ["a", "list"], 12345, 12.5, True, None, ""],
)
def test_an_odd_config_id_does_not_break_deduplication(config_id):
    """The id reaches the event signature, which is used as a dict key.

    An unhashable value there would fail the whole device list, not just this
    phone, so anything that is not a scalar is reported as absent.
    """
    rows = [
        row(_id=index, timestamp=1_000.0, study_compliance="updated study",
            study_config=json.dumps({"_id": config_id, "sensors": []}))
        for index in (1, 2)
    ]
    state = study_state.derive_study_state(rows)

    assert len(state.events) == 1
    assert state.events[0].occurrences == 2
    assert isinstance(state.summary.config_id, (str, type(None)))


@pytest.mark.parametrize("value", [12345, 12.5, {"a": 1}, ["b"], True])
def test_odd_config_versions_still_pass_schema_validation(value):
    """The summary and the timeline are serialised through Pydantic."""
    from app.schemas import AndroidStudyEventSchema, AndroidStudySummarySchema

    state = study_state.derive_study_state(
        [
            row(
                study_compliance="updated study",
                study_config=json.dumps({"_id": value, "updatedAt": value, "sensors": []}),
            )
        ]
    )

    AndroidStudySummarySchema.model_validate(state.summary)
    AndroidStudyEventSchema.model_validate(state.events[0])


def test_a_numeric_config_id_is_reported_as_text():
    state = study_state.derive_study_state(
        [row(study_compliance="updated study",
             study_config=json.dumps({"_id": 999, "updatedAt": 1785, "sensors": []}))]
    )

    assert state.summary.config_id == "999"
    assert state.summary.config_updated_at == "1785"


def test_a_config_without_a_version_still_yields_a_fingerprint():
    state = study_state.derive_study_state(
        [row(study_compliance="updated study", study_config=json.dumps({"sensors": []}))]
    )

    assert state.summary.config_id is None
    assert state.summary.config_fingerprint is not None
    # The redacted config, not the canonical form the fingerprint is taken over.
    assert state.installed_config == {"sensors": []}


def test_deriving_state_does_not_mutate_the_reported_config():
    """The parsed identity is cached, so nothing may be modified in place."""
    original = config_json()
    study_state.derive_study_state(
        [row(study_compliance="updated study", study_config=original)]
    )

    assert json.loads(original) == json.loads(config_json())


def test_the_same_config_text_is_parsed_once():
    study_state.config_identity.cache_clear()
    rows = [
        row(_id=index, timestamp=1_000.0 + index, study_compliance="updated study",
            study_config=config_json())
        for index in range(1, 21)
    ]
    study_state.derive_study_state(rows)

    assert study_state.config_identity.cache_info().misses == 1
    assert study_state.config_identity.cache_info().hits == 19
