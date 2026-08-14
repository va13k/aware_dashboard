"""Enrolment windows derived from a phone's study log.

The heatmap reads these to decide whether an empty hour means "nothing was
expected" or "expected and missing", so what is worth pinning down is the shape
of the windows rather than the storage: where one opens, where it closes, and
what happens when the log cannot answer on its own.

The log itself - deduplication, and which message is a join - is
test_study_state.py's subject. These build on it rather than repeating it.
"""

from types import SimpleNamespace

import pytest

from app.services import enrolment, study_state

DEVICE = "ca14d3f3-0000-4000-8000-000000000001"
OTHER_DEVICE = "ca14d3f3-0000-4000-8000-000000000002"

HOUR = 60 * 60 * 1000
JOIN = "joined study"
REJOIN = "rejoined study"
QUIT = "quit study"


def row(
    _id=1,
    timestamp=1_000.0,
    device_id=DEVICE,
    study_compliance="",
    double_join=0,
    double_updated=0,
    double_exit=0,
):
    return SimpleNamespace(
        _id=_id,
        timestamp=timestamp,
        device_id=device_id,
        study_compliance=study_compliance,
        study_config=None,
        double_join=double_join,
        double_updated=double_updated,
        double_exit=double_exit,
    )


def events(*rows):
    """The event list the service works from, in the order it reads them."""
    return list(reversed(study_state.derive_study_state(list(rows)).events))


def windows(*rows, first_data_at=None):
    return enrolment.windows_for(DEVICE, events(*rows), first_data_at)


def test_a_join_opens_a_window_that_stays_open():
    """A phone still in the study has no end date, and must not be given one."""
    (window,) = windows(row(timestamp=1_000, study_compliance=JOIN))

    assert window.joined_at == 1_000
    assert window.left_at is None
    assert window.join_source == enrolment.STUDY_EVENT
    assert window.left_source is None


def test_a_quit_closes_the_window_it_follows():
    (window,) = windows(
        row(_id=1, timestamp=1_000, study_compliance=JOIN),
        row(_id=2, timestamp=5_000, study_compliance=QUIT),
    )

    assert (window.joined_at, window.left_at) == (1_000, 5_000)
    assert window.left_source == enrolment.STUDY_EVENT


def test_a_rejoin_opens_a_second_window_rather_than_extending_the_first():
    """The gap between quitting and coming back is time nothing was expected.
    One window spanning both would report every hour of it as missing data."""
    first, second = windows(
        row(_id=1, timestamp=1_000, study_compliance=JOIN),
        row(_id=2, timestamp=5_000, study_compliance=QUIT),
        row(_id=3, timestamp=9_000, study_compliance=REJOIN),
    )

    assert (first.joined_at, first.left_at) == (1_000, 5_000)
    assert (second.joined_at, second.left_at) == (9_000, None)


def test_a_join_reported_twice_is_still_one_window():
    """A phone re-reporting a join it already reported has not rejoined
    anything, and two windows would put a false gap between them."""
    assert (
        len(
            windows(
                row(_id=1, timestamp=1_000, study_compliance=JOIN),
                row(_id=2, timestamp=2_000, study_compliance=JOIN),
                row(_id=3, timestamp=3_000, study_compliance=JOIN),
            )
        )
        == 1
    )


def test_the_window_follows_when_the_participant_acted():
    """`double_join` and `double_exit` are the phone's own account of the
    moment. A quit made offline reaches the server whenever the phone next
    connects, and the window has to close on the day it actually closed."""
    (window,) = windows(
        row(_id=1, timestamp=1_000, study_compliance=JOIN, double_join=900),
        row(_id=2, timestamp=9_000, study_compliance=QUIT, double_exit=5_000),
    )

    assert (window.joined_at, window.left_at) == (900, 5_000)


def test_a_device_that_never_reported_joining_gets_its_first_record():
    """Data arrived, so it was collecting. `first_data` says the join time is
    inferred rather than reported, which is what makes it questionable."""
    (window,) = windows(first_data_at=4 * HOUR)

    assert window.joined_at == 4 * HOUR
    assert window.left_at is None
    assert window.join_source == enrolment.FIRST_DATA


def test_a_log_that_opens_with_a_quit_is_dated_from_the_first_record():
    """The join predates what the phone reported, and its first record is the
    earliest moment it can have been collecting."""
    (window,) = windows(
        row(_id=1, timestamp=9_000, study_compliance=QUIT),
        first_data_at=2_000,
    )

    assert (window.joined_at, window.left_at) == (2_000, 9_000)
    assert window.join_source == enrolment.FIRST_DATA
    assert window.left_source == enrolment.STUDY_EVENT


def test_a_quit_before_any_data_leaves_no_window():
    """Nothing says this device ever collected anything, and inventing a window
    that starts after it ends would be worse than having none."""
    assert windows(row(_id=1, timestamp=1_000, study_compliance=QUIT), first_data_at=5_000) == []


def test_a_device_with_a_log_but_no_data_still_gets_its_window():
    """It joined and has yet to upload, which the device list already shows."""
    (window,) = windows(row(timestamp=1_000, study_compliance=JOIN), first_data_at=None)

    assert window.joined_at == 1_000


def test_data_before_the_reported_join_does_not_move_the_window():
    """The phone said when it joined, and that is the study's answer. Records
    outside the window are out of window - a different question, and one the
    heatmap should keep asking."""
    (window,) = windows(
        row(timestamp=5_000, study_compliance=JOIN),
        first_data_at=1_000,
    )

    assert window.joined_at == 5_000


def test_a_device_with_no_events_and_no_data_has_no_window():
    assert enrolment.windows_for(DEVICE, [], None) == []


def test_every_device_either_source_names_is_covered():
    """A device known only to the study log and one known only by its data both
    belong, so the two sources are a union rather than a join."""
    derived = enrolment.derive(
        {DEVICE: events(row(timestamp=1_000, study_compliance=JOIN))},
        {OTHER_DEVICE: 7_000},
    )

    assert {window.device_id for window in derived} == {DEVICE, OTHER_DEVICE}
    by_device = {window.device_id: window for window in derived}
    assert by_device[DEVICE].join_source == enrolment.STUDY_EVENT
    assert by_device[OTHER_DEVICE].join_source == enrolment.FIRST_DATA


@pytest.mark.parametrize(
    "reported, logged, expected",
    [
        (5_000, 1_000, 5_000),
        (0, 1_000, 1_000),
        (None, 1_000, 1_000),
        (0, 0, None),
        (None, None, None),
    ],
)
def test_the_clients_zero_default_is_not_a_moment(reported, logged, expected):
    """`double_join` and `double_exit` default to 0 rather than to NULL, so a
    zero means the phone reported nothing and the logged time stands."""
    assert enrolment._moment(reported, logged) == expected
