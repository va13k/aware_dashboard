"""Which dataflow the study runs, and which one each phone thinks it is on.

The two answers come apart exactly when it matters. A dataflow switch changes the
served config; a phone keeps its own copy until it fetches the new one, and until
then it is still sending data the old way. Reporting both sides is what makes that
stretch visible instead of a study that looks switched and is not.

The inferred case carries most of the weight here. The explicit `dataflow` field is
new, so every config generated before it -- including the copy every already
enrolled phone holds -- has to be read back out of `status_webservice`, or the view
would say "unknown" everywhere until the last phone updated.
"""

import pytest

from app.services import config_diff, study_config


def config(dataflow=None, webservice=None, **extra):
    """A study config carrying whichever of the two dataflow signals is wanted."""
    built = {"_id": "study-1", **extra}
    if dataflow is not None:
        built["dataflow"] = dataflow
    if webservice is not None:
        built["sensors"] = [{"setting": "status_webservice", "value": webservice}]
    return built


def test_a_declared_dataflow_is_read_from_the_field():
    assert study_config.dataflow(config(dataflow="webservice")) == (
        "webservice",
        study_config.DECLARED,
    )


def test_an_older_config_is_read_back_out_of_the_webservice_setting():
    """Every config generated before the field existed, which is every copy an
    already-enrolled phone is holding."""
    assert study_config.dataflow(config(webservice=True)) == (
        "webservice",
        study_config.INFERRED,
    )
    assert study_config.dataflow(config(webservice=False)) == (
        "direct",
        study_config.INFERRED,
    )


def test_the_field_wins_over_the_setting():
    """The setting is derived from the choice, so if they disagree the config was
    written by something that did not know about the field."""
    flow, source = study_config.dataflow(config(dataflow="direct", webservice=True))

    assert (flow, source) == ("direct", study_config.DECLARED)


def test_a_nonsense_field_falls_through_to_the_setting():
    flow, source = study_config.dataflow(config(dataflow="htpp", webservice=False))

    assert (flow, source) == ("direct", study_config.INFERRED)


def test_a_config_with_neither_signal_reports_unknown():
    assert study_config.dataflow(config()) == (None, None)


def test_no_config_at_all_reports_unknown():
    assert study_config.dataflow({}) == (None, None)


def test_the_summary_carries_the_dataflow_and_how_it_is_known():
    summary = study_config.safe_summary(config(dataflow="direct"))

    assert summary["dataflow"] == "direct"
    assert summary["dataflow_source"] == study_config.DECLARED


def test_a_phone_that_has_not_picked_up_a_switch_is_visible():
    """The point of the whole item: mid-switch, the study and the phone disagree,
    and a researcher has to be able to see which phones are still on the old
    path."""
    diff = config_diff.compare(
        config(dataflow="webservice", webservice=True),
        config(webservice=False),
    )

    assert diff.dataflow == "webservice"
    assert diff.device_dataflow == "direct"


def test_a_phone_that_has_caught_up_agrees():
    diff = config_diff.compare(
        config(dataflow="webservice", webservice=True),
        config(dataflow="webservice", webservice=True),
    )

    assert diff.dataflow == diff.device_dataflow == "webservice"
    assert diff.device_dataflow_source == study_config.DECLARED


def test_a_phone_that_has_never_reported_a_config_reports_no_dataflow():
    """Unknown rather than assumed. A phone that joined and has not sent a config
    update yet is not evidence about which path it is using."""
    diff = config_diff.compare(config(dataflow="direct", webservice=False), None)

    assert diff.dataflow == "direct"
    assert diff.device_dataflow is None
    assert diff.status_reason == config_diff.NO_DEVICE_CONFIG


@pytest.mark.asyncio
async def test_the_study_endpoint_always_reports_ios_as_the_micro_server():
    """An iPhone has no direct-database client, so its path is a property of the
    platform rather than a choice this study made."""
    from app.routers import study as study_router

    body = await study_router.get_study_dataflow()

    assert body["ios"] == {"dataflow": "webservice", "source": "platform"}
