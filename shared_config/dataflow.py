"""Where a platform's data goes, as one declared choice per platform.

A dataflow is not one setting. It is the webservice channel, the address the phone
is given, whether the published config carries database coordinates at all, and
what the join QR code points at --- and those have to agree or a study ends up
half-configured for each. So the choice is declared once, in
``deployment.dataflow``, and everything else is derived from it here rather than
being set by hand in two generators that can drift apart.

Two values:

``direct``
    The phone opens MySQL itself. Its config must carry the database address, and
    the database has to be reachable from wherever the participant happens to be.

``webservice``
    The phone posts to the micro-server, which performs the write. Its config
    carries a study URL and no database coordinates, so the database can be
    private, remote or managed by somebody else.

iOS is ``webservice`` and cannot be anything else: the micro-server *is* the iOS
path, and an iPhone has no direct-database client.

Android is ``direct`` for now, and ``webservice`` is refused rather than offered
(see :func:`unsupported_reason`). The client can do it: it uploads through
``Webservice.insertData`` when a study asks, and a direct-mode regression run on an
emulator confirmed the branch. What is missing is on this side, and all of it:

* The study URL answers a GET with an HTML QR page, not a study configuration ---
  and a GET there is exactly how the client fetches its config. The client also
  ignores ``webservice_server`` from the config it receives, using the URL it was
  joined with, so the join URL and the config URL have to be the same one.
* The micro-server writes ``(device_id, timestamp, data)``. Android's tables are
  columnar (``double_values_0``, ``accuracy``, ``label``), and have no ``data``
  column to put a blob in.
* The micro-server writes to one configured schema. Android rows and study events
  would land in the iOS database, so no ``aware_android.device_enrolment`` window
  would ever be derived and the enrolment gate would refuse the device forever.

Offering the choice before those are closed would produce a study that looks
configured and collects nothing: the phone buffers locally, uploads into the wrong
place or not at all, and the gap surfaces in the coverage grid weeks later.
"""

#: The phone opens the database itself.
DIRECT = "direct"
#: The phone posts to the micro-server, which writes.
WEBSERVICE = "webservice"

CHOICES = (DIRECT, WEBSERVICE)

#: What each platform may be set to today. iOS has no direct-database client;
#: Android's webservice path has a client but not yet a server to receive it.
SUPPORTED = {
    "android": (DIRECT,),
    "ios": (WEBSERVICE,),
}

#: Used when a study predates the field, and when a platform's entry is missing.
DEFAULTS = {"android": DIRECT, "ios": WEBSERVICE}


def declared(source: dict, platform: str) -> str:
    """The dataflow this study declares for a platform.

    A study written before the field existed reads as its default, which is what
    that study was already doing.
    """
    dataflow = (source.get("deployment") or {}).get("dataflow") or {}
    value = str(dataflow.get(platform) or DEFAULTS[platform]).strip().lower()
    return value if value in CHOICES else DEFAULTS[platform]


def unsupported_reason(platform: str, choice: str) -> str | None:
    """Why this platform cannot run this dataflow, or None when it can.

    Returned as a sentence rather than a boolean because the caller's job is to
    tell a researcher what is missing, and "unsupported" on its own invites
    someone to go looking for the setting that turns it on.
    """
    if platform not in SUPPORTED:
        return f"Unknown platform {platform!r}."
    if choice not in CHOICES:
        return (
            f"{choice!r} is not a dataflow. Choose {DIRECT!r} or {WEBSERVICE!r}."
        )
    if choice in SUPPORTED[platform]:
        return None
    if platform == "android" and choice == WEBSERVICE:
        return (
            "The server cannot yet receive Android data over HTTP/S. The client can "
            "send it, but the study URL serves a QR page rather than a study "
            "configuration, the micro-server writes the iOS row shape into one "
            "configured schema, and Android's tables are columnar and live in "
            "another. A phone given this configuration would collect and never "
            "deliver, or deliver where nothing reads it. Android stays on "
            f"{DIRECT!r} until the micro-server can serve and store it."
        )
    if platform == "ios" and choice == DIRECT:
        return (
            "An iPhone has no direct-database client. iOS data always arrives "
            "through the micro-server."
        )
    return f"{platform} does not support {choice!r}."


def carries_database_credentials(platform: str, choice: str) -> bool:
    """Whether the published config has to include database coordinates.

    Only a phone that opens the database itself needs them. On the webservice path
    the address, the account and the password are all the micro-server's business,
    so publishing them would hand every participant a credential for a database
    they never contact.
    """
    return choice == DIRECT


def validate(source: dict) -> list[str]:
    """Every dataflow in this study that cannot be honoured, as reasons.

    Empty means the study is coherent. Collected rather than raised on the first
    problem, so a researcher fixing a config sees all of it at once.
    """
    problems = []
    for platform in SUPPORTED:
        choice = declared(source, platform)
        reason = unsupported_reason(platform, choice)
        if reason is not None:
            problems.append(f"{platform}: {reason}")
    return problems


def webservice_server(choice: str, study_url: str, config_url: str) -> str:
    """What the phone's ``webservice_server`` setting should hold.

    The same key means two different things, which is why setup and the
    Configurator had each been writing their own answer into it. On the direct
    path the client uses it to fetch config updates, so it is the published
    config's own URL. On the webservice path the client posts data to
    ``<webservice_server>/<table>/insert`` as well, so it is the micro-server's
    study URL.

    One function so the two generators cannot disagree again.
    """
    return study_url if choice == WEBSERVICE else config_url
