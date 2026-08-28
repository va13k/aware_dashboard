"""Reaching a participant's phone, as topics the client already listens on.

Every other part of this system observes. This is the one path that speaks, and it
exists because the clients were already built for it: the AWARE client subscribes on
connect and acts on what arrives, routing by the last segment of the topic. So the
server half is a broker and a publish, not client work.

What a phone does with each channel, read from ``Mqtt.messageArrived``:

``broadcasts``
    The body is an Android action, re-broadcast as an intent. Sending
    ``ACTION_AWARE_SYNC_DATA`` here is how a researcher asks a phone to upload now.

``esm``
    The body is an ESM definition, queued for display. This is a questionnaire asked
    on demand rather than on the schedule the study config carries.

``notice``
    The body is a researcher message, shown as a high-priority Android notification
    with the participant's configured notification sound and vibration.

``configuration``
    A JSON array of settings, applied by ``Aware.tweakSettings``.

``schedulers``
    A JSON array of schedules, handed to the client's own scheduler.

**The topic is unscoped by study, deliberately.** The client also subscribes to
``<study_key>/<device_id>/<channel>``, reading the study key with ``getInt`` against
a column holding text --- which is ``0`` for every device this deployment has
enrolled. A publisher addressing the study key would reach nobody and say nothing
about it. The client self-subscribes to ``<device_id>/#`` as well, and that is what
this addresses: it does not depend on what the study key parses as.

**Two accounts, because the shared one is the phones'.** The credential a phone uses
travels in the study config, which is one file every participant is served, so it
cannot be per-device and cannot be kept from anyone in the study. What it *can* be is
read-only: a phone that has it may receive on these channels and may not publish on
them, so no participant can send prompts to another. Publishing is a second account
that never leaves the server. Confining a phone to its own topics needs a credential
the client fetches per device, which is client work rather than deployment work.
"""

#: What a phone does with a message, keyed by the topic's last segment.
SYNC = "broadcasts"
ESM = "esm"
NOTICE_CHANNEL = "notice"
CONFIGURATION = "configuration"
SCHEDULERS = "schedulers"

CHANNELS = (SYNC, ESM, NOTICE_CHANNEL, CONFIGURATION, SCHEDULERS)

#: The action a phone re-broadcasts to start an upload, which is the client's own
#: name for it rather than one invented here.
SYNC_ACTION = "ACTION_AWARE_SYNC_DATA"

#: The action that makes a phone re-read the study configuration it was joined with.
#: The client answers it with ``enqueueStudyConfigSync``, which is the same work its
#: own schedule does --- so this is asking for that now rather than waiting on a timer.
#:
#: It is what a study needs after any change to what the phones are told: a new
#: question, a changed schedule, a sensor turned on. Without it a researcher edits the
#: study and then waits on each phone's own clock, unable to tell a phone that has not
#: noticed from one that has nothing to report.
CONFIG_ACTION = "ACTION_AWARE_SYNC_CONFIG"

#: The account a phone connects with, carried in the study config it is served.
#: Receives on the channels above and publishes on none of them.
PARTICIPANT_USER = "aware_participant"

#: The account the dashboard publishes with. Held by the API alone and never written
#: into anything a phone is served.
PUBLISHER_USER = "aware_publisher"

#: The prefix the client builds its study-scoped subscriptions from. Read here as the
#: literal the client's own parse produces, so the broker permits the subscriptions a
#: phone actually makes rather than the ones its source appears to describe.
STUDY_SCOPE = "0"

#: Plaintext and TLS. The client chooses between them by port alone --- 1883 is
#: opened as ``tcp`` and anything else as ``ssl`` --- so the port is the setting that
#: decides whether a participant's prompts travel in clear.
PLAIN_PORT = 1883
TLS_PORT = 8883


#: Where what a researcher asked of a phone is kept. The other two states of a
#: prompt are the phone's own rows; this is the one this side owns.
SENT_TABLE = "messages_sent"

#: What a researcher can ask for, as the record names it.
SYNC_REQUEST = "sync"
QUESTION = "question"
NOTICE = "notice"
UPDATE_REQUEST = "update"

#: What a phone is asked to do rather than shown. Neither interrupts a participant,
#: so both are held to the looser of the two limits.
QUIET_KINDS = (SYNC_REQUEST, UPDATE_REQUEST)

#: How many prompts one device may be sent in a window, and how long the window is.
#: Nothing in the mechanism stops a researcher filling somebody's phone, and the
#: interface should not be the only thing that does. Sync requests are counted
#: separately and allowed more often: one costs a participant nothing and shows them
#: nothing, where a question interrupts them.
PROMPT_LIMIT = 6
SYNC_LIMIT = 30
LIMIT_WINDOW_SECONDS = 3600


def limit_for(kind: str) -> int:
    """How many of this kind of message one device may be sent in a window."""
    return SYNC_LIMIT if kind in QUIET_KINDS else PROMPT_LIMIT


def action_for(kind: str) -> str:
    """The Android action a phone re-broadcasts for this request."""
    return CONFIG_ACTION if kind == UPDATE_REQUEST else SYNC_ACTION


def over_limit(kind: str, already_sent: int) -> str | None:
    """Why this device may not be sent another right now, or None when it may.

    A sentence rather than a boolean, because the caller's job is to tell a
    researcher what the limit is and when it lifts rather than to refuse silently.
    """
    limit = limit_for(kind)
    if already_sent < limit:
        return None
    window = LIMIT_WINDOW_SECONDS // 60
    return (
        f"{already_sent} of these have gone to this device in the last {window} "
        f"minutes, which is the limit ({limit}). A participant's phone is not a "
        "channel to keep pushing at; wait for the window to pass."
    )


def topic(device_id: str, channel: str) -> str:
    """Where a message for one device on one channel is published."""
    if channel not in CHANNELS:
        raise ValueError(f"{channel!r} is not a channel a phone listens on")
    return f"{device_id}/{channel}"


def port_for(protocol: str) -> int:
    """The broker port that follows the deployment's own protocol.

    The two travel together because they answer the same question: a deployment
    serving participants over TLS has a certificate the broker can present, and one
    serving them over HTTP has nothing to present. The client reads TLS from the port,
    so this is also what turns encryption on for it.
    """
    return TLS_PORT if str(protocol).strip().lower() == "https" else PLAIN_PORT


def uses_tls(protocol: str) -> bool:
    return port_for(protocol) == TLS_PORT


def acl(participant_user: str = PARTICIPANT_USER, publisher_user: str = PUBLISHER_USER) -> str:
    """Who may publish and who may receive, as mosquitto reads it.

    Written as an explicit list of channels rather than a wildcard over everything: a
    subscription to ``#`` is answered by whatever these lines permit, so naming the
    five channels is what keeps a phone out of the broker's own ``$SYS`` tree and out
    of any topic somebody adds later without thinking about who can read it.

    ``+`` matches one segment, which is a device id, so one line covers every device
    without naming any.
    """
    lines = [
        "# Generated from shared_config/messaging.py. Edit the study, not this file.",
        "#",
        "# The publisher is the dashboard's API and never leaves this deployment.",
        f"user {publisher_user}",
    ]
    lines += [f"topic write +/{channel}" for channel in CHANNELS]
    lines += [f"topic write {STUDY_SCOPE}/+/{channel}" for channel in CHANNELS]
    lines += [
        "",
        "# Every participant's phone connects as this, with the credential its study",
        "# config carries. Read-only on purpose: the credential is shared by the whole",
        "# study, so a phone that can publish on these channels can prompt anybody in it.",
        f"user {participant_user}",
    ]
    lines += [f"topic read +/{channel}" for channel in CHANNELS]
    # The client subscribes to the study-scoped form as well, so the broker permits it
    # rather than answering a phone's own startup with a string of refusals.
    lines += [f"topic read {STUDY_SCOPE}/+/{channel}" for channel in CHANNELS]
    lines.append("")
    return "\n".join(lines)


def broker_config(protocol: str, cert_path: str = "", key_path: str = "") -> str:
    """The broker's own configuration, following the deployment's protocol.

    Anonymous access is refused whichever protocol is in use: the credential is shared
    and therefore weak, and it is still the difference between a broker only the study
    can reach and one anybody who finds the port can read.
    """
    lines = [
        "# Generated by setup/deploy_config.py. Edit the study, not this file.",
        "persistence true",
        "persistence_location /mosquitto/data/",
        "log_dest stdout",
        "allow_anonymous false",
        "password_file /mosquitto/config/passwords",
        "acl_file /mosquitto/config/acl",
        "",
        "# Reachable from inside the deployment whatever the participants use, so the",
        "# dashboard's API publishes over the compose network rather than out and back.",
        "listener 1883 0.0.0.0",
        "",
    ]
    if uses_tls(protocol):
        lines += [
            "# What participants connect to. The client opens any port but 1883 as TLS,",
            "# so this port is what turns encryption on at the phone.",
            f"listener {TLS_PORT} 0.0.0.0",
            f"certfile {cert_path or '/mosquitto/certs/fullchain.pem'}",
            f"keyfile {key_path or '/mosquitto/certs/privkey.pem'}",
            "tls_version tlsv1.2",
            "",
        ]
    return "\n".join(lines)


def study_settings(server: str, protocol: str, username: str, password: str) -> dict:
    """The MQTT block a phone is served, filled from what this deployment runs.

    The keys are the client's own, and every one of them has been present and blank in
    the study model all along --- which is what makes reaching a participant a matter
    of filling them in.
    """
    # Both halves or neither: an address with no credential is a connection the
    # broker refuses, retried for the life of the study.
    reachable = bool(server) and bool(username) and bool(password)
    settings = dict(STUDY_OWNED_DEFAULTS)
    settings.update(
        {
            "status_mqtt": reachable,
            "mqtt_server": server,
            "mqtt_port": port_for(protocol),
            "mqtt_username": username,
            "mqtt_password": password,
        }
    )
    return settings


#: Where the broker is and who connects to it. Derived from what this deployment
#: actually runs, and rewritten on every deploy: the dashboard publishes to the
#: broker it brought up, so a study naming a different one would have its phones
#: listening somewhere nothing is sent.
DEPLOYMENT_OWNED = ("mqtt_server", "mqtt_port", "mqtt_username", "mqtt_password")

#: How the client behaves once connected. Nothing here decides where a message
#: goes, so a researcher may set them and a deploy leaves them alone.
#:
#: ``mqtt_qos`` is at-least-once: the phone records what it received, so a duplicate
#: is visible where a silently dropped prompt would not be.
STUDY_OWNED_DEFAULTS = {"status_mqtt": False, "mqtt_keep_alive": 600, "mqtt_qos": 1}


def apply_deployment_settings(existing: dict, generated: dict) -> dict:
    """The deployment's half rewritten, the study's half left as the researcher set it.

    Called on every deploy. Without the split a saved change to how often the client
    pings, or to whether messaging is on at all, would survive until the next deploy
    and then vanish without anybody touching it.
    """
    merged = dict(existing or {})
    for key in DEPLOYMENT_OWNED:
        merged[key] = generated[key]
    for key, fallback in STUDY_OWNED_DEFAULTS.items():
        if key not in merged:
            merged[key] = generated.get(key, fallback)
    # A study with no broker to reach cannot be messaging, whatever it last said.
    if not generated.get("status_mqtt"):
        merged["status_mqtt"] = False
    return merged
