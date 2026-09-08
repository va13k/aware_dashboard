# The micro-server

The service a phone talks to. It receives sensor uploads over HTTP, decides whether
each batch may be stored, and writes the rows into MySQL. Everything else in the
stack reads that data afterwards; this is the only component that writes it on a
participant's behalf.

It is a [Vert.x](https://vertx.io) application in Kotlin, forked from
[AWARE Micro](https://github.com/denzilferreira/aware-micro). Upstream's own
document is kept as [`README.adoc`](README.adoc). This one describes the fork as it
is deployed here.

Where the service sits in the stack, which routes nginx sends to it and which
database accounts it uses are in
[docs/dev/architecture.md](../docs/dev/architecture.md). This document is about the
code in this directory.

---

## Two instances, one image

The deployment builds this directory once and runs it twice:

| Container | Platform | Study | Port | Config file | Writes to |
| --- | --- | --- | --- | --- | --- |
| `aware_micro` | iOS | 1 | `8080` | `aware-config.json` | `aware_ios` as `aware_ios_participant` |
| `aware_micro_android` | Android | 2 | `8082` | `aware-config.android.json` | `aware_android` as `aware_android_server` |

Both mount their file at `/app/aware-config.json`, so the process itself has no
notion of which platform it is serving. A study number, a study key, a port, a
database and a set of sensors are all it reads, and everything that differs between
the two instances differs only in those files. The Android number is fixed at 2 by
the deployment; the iOS one is whatever `source.json` declares, and 1 unless a study
says otherwise.

Both run under either Android dataflow, and what changes is how much of the Android
one is used. On `webservice` its insert route is the ingest path. On `direct` the
phones write to MySQL themselves and post nothing here, and the only thing still
published from that instance is the QR image it renders. The configuration an
Android phone reads is a static file nginx serves in both cases, never a route on
this service.

---

## What it answers

Every route below carries the study number and the study key, and `validRoute`
compares both against the served config before anything else happens. A request
with either one wrong is answered without reaching the database.

| Route | What it does |
| --- | --- |
| `GET /` | A page naming the study and linking to the join URL. Also the container's health check. |
| `GET /:study/:key` | The join page: an HTML page with the QR code a participant scans, rendered from [`templates/qrcode.peb`](src/main/resources/templates/qrcode.peb). Wrong key answers 404. |
| `GET /qr.png` | The same QR code as a bare PNG, which is what nginx publishes as `/android-qr.png`. 404 while the config declares no join URL. |
| `POST /:study/:key` | The device row a client sends on joining, stored in `aware_device`. |
| `POST /index.php/:study/:key` | The study configuration, as the client asks for it on joining and on every check afterwards. With the form field `study_check=1` it answers with the study's active flag alone. |
| `GET /index.php/webservice/client_get_study_info/:key` | Study name, description and researcher contact, for clients that ask before joining. |
| `POST /index.php/:study/:key/:table/insert` | A batch of sensor rows. This is the ingest route, and the section below is about what happens to it. |
| `POST /index.php/:study/:key/:table/create_table` | Answers 200 and does nothing. The schema is built by [`db/`](../db/README.md), and a client that still asks for a table needs the answer it has always had. |

`/cache/` and `/esm/` are served as static directories, and a request body is capped
at 50 MB.

---

## What the fork added

Five objects hold the behaviour this deployment needs and upstream has no reason to
carry. Each is a small file next to `MainVerticle.kt`, and four of the five have a
test class of their own.

**[`EnrolmentGate.kt`](src/main/kotlin/com/awareframework/micro/EnrolmentGate.kt)**
decides whether a device may write at all. A study that sets `require_enrolment`
accepts rows only from a device that has joined it, which the gate reads from
`device_enrolment`. Membership means having joined at some point, so a participant
who has since withdrawn keeps the data they contributed and stops contributing more
only when the study says so. Android is the platform with an enrolment registry to
check against, so it is the instance that turns this on.

**[`Refusal.kt`](src/main/kotlin/com/awareframework/micro/Refusal.kt)** is the
vocabulary of a write that did not happen. A refused batch stores nothing, so
without this the only trace would be a line in a container log, which is not
somewhere a researcher looks. A refusal travels the event bus to `refusals`, where
it is counted per device and reason, alongside the rows it would have written and
the last table it happened on.

**[`TableName.kt`](src/main/kotlin/com/awareframework/micro/TableName.kt)** holds
the one part of a request that reaches a statement as text rather than as a
parameter. MySQL parses an identifier before it binds anything, so a table name
taken from a URL is the one injection route a prepared statement cannot close. It is
held to the characters an AWARE table is named with.

**[`LogSafe.kt`](src/main/kotlin/com/awareframework/micro/LogSafe.kt)** keeps three
things out of the log that had been reaching it: the study key, which is the
credential a phone presents; the request parameters, which for an upload *are* the
participant's sensor rows, and which no retention or consent story covers once they
are copied into container logs; and the served study config, which carries the key
again alongside third-party plugin credentials.

**[`DeviceMetadata.kt`](src/main/kotlin/com/awareframework/micro/DeviceMetadata.kt)**
decides whether a device report is worth writing. A phone sends its make, model and
label on every sync, so nearly every report repeats the last one, and only the
reports that say something new reach `device_contacts`.

---

## The answer a batch gets

A client reads the response to an insert as "are these rows on the server" and moves
its own watermark past them on a 200. The route therefore waits for the batch's fate
before answering, and each answer means one thing:

| Status | Meaning | What the phone does |
| --- | --- | --- |
| `200` | Written. | Moves past the batch. |
| `403` | The gate turned it away. | Keeps the rows and offers them again. |
| `503` | The database could not take it. | Keeps the rows and offers them again. |
| `400` | No `device_id` anywhere in the request. | Nothing to attribute the rows to. |

The distinction matters because the two failures used to look like success. A batch
answered 200 that was never stored is data the phone deletes and nobody has.

---

## The configuration file

[`aware-config.example.json`](aware-config.example.json) is the shape, and it is the
only one of the three in git. Both live files are written by
[`setup/deploy_config.py`](../setup/deploy_config.py) from the study's `source.json`
and are not edited by hand: the next deploy overwrites them.

Four blocks, all of them read:

- **`server`** is the database connection, the ports, the TLS paths and
  `require_enrolment`.
- **`study`** is the number, the key, the join URL and the researcher's contact
  details, all of which reach a participant's screen.
- **`sensors`** and **`plugins`** are the settings a client applies to itself, which
  is how a study decides what a phone actually records.

A running instance re-reads its file every five seconds and rebinds its server when
the file changes, and `docker compose watch` restarts the container as well. Neither
path needs a rebuild for a settings change to reach a phone.

---

## Working on it

Gradle 8.3 on JDK 11, both pinned: `kotlinOptions.jvmTarget = '11'` in
[`build.gradle`](build.gradle), and the image builds on `gradle:8.3-jdk11` and runs
on `eclipse-temurin:11-jre`.

```bash
cd aware-micro-server && ./gradlew check
```

Thirty-two tests across five classes in
[`src/test/kotlin`](src/test/kotlin/com/awareframework/micro): one class each for
the enrolment gate, the table-name rule, the log redaction and the device-metadata
decision, and `TestMainVerticle`, which stands the server up and asks it for `/`.
The refusal vocabulary is covered through the gate's tests rather than on its own.

This is what CI runs, as the `Micro-server` job in
[`.github/workflows/check.yml`](../.github/workflows/check.yml). The `check.yml`
inside this directory is upstream's and GitHub never reads it, since workflows are
only picked up from the repository root.

To exercise a change against real phones, rebuild the one service rather than the
stack:

```bash
docker compose up --build -d micro-server-android
```

`old_ui_code` is upstream's setup UI, kept as a plain file so it does not compile.
The `create-*.peb` templates belong to it; `qrcode.peb` is the live one.
