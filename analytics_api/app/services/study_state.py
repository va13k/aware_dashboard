"""Derives a phone's study state from its `aware_studies` rows.

The client appends a row per study event and never updates one, so the table is
an append-only log that contains duplicates: logically identical events arrive
more than once with different `_id` values. Everything here works on the
deduplicated log, and each surviving event reports how many raw rows collapsed
into it so a researcher can still audit the difference.

Event kinds are returned as identifiers rather than sentences. Wording is a UI
concern, and the original message is carried through untouched so an event kind
this module does not recognise stays visible instead of being swallowed.
"""

import json
import re
from dataclasses import dataclass, field, replace
from typing import Any

from app.services import study_config

IN_STUDY = "in_study"
LEFT_STUDY = "left_study"
UNKNOWN = "unknown"

JOINED = "joined"
REJOINED = "rejoined"
UPDATED = "updated"
CONSENT = "consent"
LEFT = "left"
OTHER = "other"

CONSENT_INITIAL = "initial"
CONSENT_STUDY_UPDATE = "study_update"

QUIT_MESSAGE = "quit study"
UPDATE_MESSAGE = "updated study"
JOIN_MESSAGE = "joined study"
REJOIN_MARKER = "rejoin"
# What the client reported before it reported a rejoin. Rows written by older
# clients are still in the table, so both spellings mean the same thing: the
# phone came back to the study after collection had stopped.
LEGACY_REJOIN_MESSAGE = "collection resumed after password re-authentication"

# `consent given: enabled=[...] declined=[...]`, optionally qualified with a
# context in parentheses: `consent given (study update): ...`.
CONSENT_PATTERN = re.compile(
    r"^consent given"
    r"(?:\s*\((?P<context>[^)]*)\))?"
    r"\s*:\s*enabled=\[(?P<enabled>[^\]]*)\]"
    r"\s*declined=\[(?P<declined>[^\]]*)\]\s*$",
    re.IGNORECASE,
)

# Kinds that mean the phone was in the study when the event happened.
MEMBERSHIP_KINDS = frozenset({JOINED, REJOINED, UPDATED, CONSENT})

# Both put the phone in the study; a rejoin is reported separately because it
# says collection had stopped and started again.
JOIN_KINDS = frozenset({JOINED, REJOINED})


def _number(value: Any) -> float | None:
    """A usable numeric field, or None for the client's zero/absent default."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            number = float(value)
        except ValueError:
            return None
    else:
        return None

    if number != number or number in (float("inf"), float("-inf")):  # NaN, inf
        return None
    return number if number > 0 else None


def _message(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _consent_categories(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_consent(message: str) -> tuple[list[str], list[str], str] | None:
    """Split a consent message into approved, declined and context.

    Returns None when the message does not parse, so the caller can keep the
    original text and classify the event as unrecognised rather than invent
    consent values.
    """
    match = CONSENT_PATTERN.match(message)
    if not match:
        return None

    context = (match.group("context") or "").strip().lower()
    return (
        _consent_categories(match.group("enabled")),
        _consent_categories(match.group("declined")),
        CONSENT_STUDY_UPDATE if "update" in context else CONSENT_INITIAL,
    )


def classify(message: str, exited: float | None, joined: float | None) -> str:
    """The kind of event a compliance message describes.

    Falls back to the numeric fields, because some rows carry an empty message
    while still recording a join or an exit.
    """
    lowered = message.lower()

    if QUIT_MESSAGE in lowered:
        return LEFT
    if lowered.startswith("consent given"):
        return CONSENT if parse_consent(message) else OTHER
    # Before the plain join: "rejoined study" contains "joined study".
    if REJOIN_MARKER in lowered or LEGACY_REJOIN_MESSAGE in lowered:
        return REJOINED
    if UPDATE_MESSAGE in lowered:
        return UPDATED
    if JOIN_MESSAGE in lowered:
        return JOINED

    if not lowered:
        if exited is not None:
            return LEFT
        if joined is not None:
            return JOINED

    return OTHER


def device_config(raw: Any) -> dict | None:
    """The phone's config, redacted, or None when it reported none.

    The column is `NULL` on some events and an empty string on most of them -
    only the update events carry a config - so an absent config is normal and
    not a parse failure.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    return study_config.redact(parsed)


@dataclass(frozen=True)
class StudyEvent:
    device_id: str | None
    timestamp: float | None
    kind: str
    message: str
    joined_at: float | None = None
    updated_at: float | None = None
    exited_at: float | None = None
    approved_consents: list[str] = field(default_factory=list)
    declined_consents: list[str] = field(default_factory=list)
    consent_context: str | None = None
    config_id: str | None = None
    config_updated_at: str | None = None
    config_fingerprint: str | None = None
    # How many raw rows collapsed into this event. Above 1 means the client
    # reported it more than once, which is normal and not a data problem.
    occurrences: int = 1

    @property
    def signature(self) -> tuple:
        """Identity of the event itself, deliberately excluding `_id`.

        Duplicates differ only by primary key, so including it would defeat the
        deduplication it is meant to support.
        """
        return (
            self.device_id,
            self.timestamp,
            self.message,
            self.joined_at,
            self.updated_at,
            self.exited_at,
            self.config_id,
            self.config_updated_at,
        )


@dataclass(frozen=True)
class StudySummary:
    enrollment_status: str = UNKNOWN
    last_study_event_at: float | None = None
    last_study_event: str | None = None
    last_join_at: float | None = None
    last_exit_at: float | None = None
    config_id: str | None = None
    config_updated_at: str | None = None
    config_fingerprint: str | None = None
    approved_consents: list[str] = field(default_factory=list)
    declined_consents: list[str] = field(default_factory=list)
    last_consent_at: float | None = None
    consent_context: str | None = None
    last_rejoin_at: float | None = None
    last_rejoin_pause_started_at: float | None = None
    last_rejoin_pause_ms: float | None = None
    event_count: int = 0
    duplicate_row_count: int = 0


@dataclass(frozen=True)
class StudyState:
    summary: StudySummary
    #: Deduplicated, newest first - the order both the API and the UI present.
    events: list[StudyEvent] = field(default_factory=list)
    #: The redacted config from the most recent event that carried one.
    installed_config: dict | None = field(default=None, repr=False)


def _to_event(row: Any, config: dict | None) -> StudyEvent:
    message = _message(getattr(row, "study_compliance", None))
    joined_at = _number(getattr(row, "double_join", None))
    updated_at = _number(getattr(row, "double_updated", None))
    exited_at = _number(getattr(row, "double_exit", None))

    kind = classify(message, exited_at, joined_at)
    approved: list[str] = []
    declined: list[str] = []
    context: str | None = None
    if kind == CONSENT:
        approved, declined, context = parse_consent(message)

    config_id = None
    config_updated_at = None
    fingerprint = None
    if config is not None:
        config_id = config.get("_id") or None
        config_updated_at = config.get("updatedAt") or None
        fingerprint = study_config.content_fingerprint(config)

    device_id = getattr(row, "device_id", None)
    return StudyEvent(
        device_id=str(device_id) if device_id is not None else None,
        timestamp=_number(getattr(row, "timestamp", None)),
        kind=kind,
        message=message,
        joined_at=joined_at,
        updated_at=updated_at,
        exited_at=exited_at,
        approved_consents=approved,
        declined_consents=declined,
        consent_context=context,
        config_id=config_id,
        config_updated_at=config_updated_at,
        config_fingerprint=fingerprint,
    )


def _sorted_rows(rows) -> list[Any]:
    return sorted(
        rows,
        key=lambda row: (
            _number(getattr(row, "timestamp", None)) or 0.0,
            _number(getattr(row, "_id", None)) or 0.0,
        ),
    )


def _deduplicate(events: list[StudyEvent]) -> list[StudyEvent]:
    """Collapse identical events, keeping the earliest and counting the rest."""
    counts: dict[tuple, int] = {}
    first: dict[tuple, StudyEvent] = {}
    order: list[tuple] = []

    for event in events:
        signature = event.signature
        if signature not in first:
            first[signature] = event
            order.append(signature)
        counts[signature] = counts.get(signature, 0) + 1

    return [
        replace(first[signature], occurrences=counts[signature])
        for signature in order
    ]


def derive_enrollment_status(events: list[StudyEvent]) -> str:
    """The state the last decisive event left the phone in.

    Later events win, so a phone that quit and rejoined reads as in the study
    again. Events that say nothing about membership leave the state alone, and a
    log with no membership signal at all stays unknown rather than guessing.
    """
    status = UNKNOWN
    for event in events:
        if event.kind == LEFT or event.exited_at is not None:
            status = LEFT_STUDY
        elif event.kind in MEMBERSHIP_KINDS or event.joined_at is not None:
            status = IN_STUDY
    return status


def _latest(events: list[StudyEvent], kinds) -> StudyEvent | None:
    wanted = {kinds} if isinstance(kinds, str) else kinds
    for event in reversed(events):
        if event.kind in wanted:
            return event
    return None


def _pause_start(events: list[StudyEvent], rejoin: StudyEvent) -> float | None:
    """When collection stopped before this rejoin.

    Three ways to find it, in descending order of directness: the rejoin row
    names it, an earlier update shares the rejoin row's join marker, or - last
    resort - it was the closest update before the rejoin.
    """
    if rejoin.updated_at is not None:
        return rejoin.updated_at

    rejoined_at = rejoin.timestamp
    preceding = [
        event
        for event in events
        if event.kind == UPDATED
        and event.timestamp is not None
        and (rejoined_at is None or event.timestamp <= rejoined_at)
    ]

    if rejoin.joined_at is not None:
        for event in reversed(preceding):
            if event.joined_at == rejoin.joined_at:
                return event.timestamp

    return preceding[-1].timestamp if preceding else None


def _rejoin_window(
    events: list[StudyEvent],
) -> tuple[float | None, float | None, float | None]:
    """When the phone last rejoined, and how long collection was stopped."""
    rejoin = _latest(events, REJOINED)
    if rejoin is None:
        return None, None, None

    started_at = _pause_start(events, rejoin)
    rejoined_at = rejoin.timestamp
    paused_ms = None
    if started_at is not None and rejoined_at is not None and rejoined_at >= started_at:
        paused_ms = rejoined_at - started_at
    return rejoined_at, started_at, paused_ms


def derive_study_state(rows) -> StudyState:
    """Everything the dashboard shows about one phone's study membership."""
    configs = []
    raw_events = []
    for row in _sorted_rows(rows):
        config = device_config(getattr(row, "study_config", None))
        configs.append(config)
        raw_events.append(_to_event(row, config))

    events = _deduplicate(raw_events)
    if not events:
        return StudyState(summary=StudySummary())

    latest = events[-1]
    consent = _latest(events, CONSENT)
    joined = _latest(events, JOIN_KINDS)
    left = _latest(events, LEFT)
    # Most events carry no config at all - only the update events do - so the
    # installed config is the last one reported, not the one on the last event.
    installed_config = next(
        (config for config in reversed(configs) if config is not None), None
    )
    configured = next(
        (event for event in reversed(events) if event.config_fingerprint), None
    )

    rejoined_at, pause_started_at, paused_ms = _rejoin_window(events)

    summary = StudySummary(
        enrollment_status=derive_enrollment_status(events),
        last_study_event_at=latest.timestamp,
        last_study_event=latest.message or None,
        last_join_at=joined.joined_at if joined else None,
        last_exit_at=left.exited_at if left else None,
        config_id=configured.config_id if configured else None,
        config_updated_at=configured.config_updated_at if configured else None,
        config_fingerprint=configured.config_fingerprint if configured else None,
        approved_consents=consent.approved_consents if consent else [],
        declined_consents=consent.declined_consents if consent else [],
        last_consent_at=consent.timestamp if consent else None,
        consent_context=consent.consent_context if consent else None,
        last_rejoin_at=rejoined_at,
        last_rejoin_pause_started_at=pause_started_at,
        last_rejoin_pause_ms=paused_ms,
        event_count=len(events),
        duplicate_row_count=len(raw_events) - len(events),
    )

    return StudyState(
        summary=summary,
        events=list(reversed(events)),
        installed_config=installed_config,
    )
