"""Researcher messages keep notices separate from answerable ESM prompts."""

import json

from app.routers.messages import SendRequest, _esm, _notice


def test_notice_is_a_notification_payload():
    payload = SendRequest(
        device_id="participant-1",
        kind="notice",
        title="Study reminder",
        instructions="Please charge your phone tonight.",
    )

    notice = json.loads(_notice(payload))
    assert notice["title"] == "Study reminder"
    assert notice["message"] == "Please charge your phone tonight."
    assert len(notice["id"]) == 32


def test_question_remains_an_esm_payload():
    payload = SendRequest(
        device_id="participant-1",
        kind="question",
        title="How are you?",
        instructions="Choose one answer.",
        answers=["Good", "Bad"],
    )

    esm = json.loads(_esm(payload))[0]["esm"]
    assert esm["esm_title"] == "How are you?"
    assert esm["esm_quick_answers"] == ["Good", "Bad"]
