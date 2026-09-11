# micro-server

The service a phone talks to. Kotlin on Vert.x, JDK 11, built once and run twice.
Prose: [`aware-micro-server/README.md`](../../aware-micro-server/README.md), which
carries the routes and the response contract.

---

## What owns what

Paths are under
[`aware-micro-server/src/main/kotlin/com/awareframework/micro/`](../../aware-micro-server/src/main/kotlin/com/awareframework/micro).

| Concept | File |
| --- | --- |
| Every route, config reload, QR rendering | [`MainVerticle.kt`](../../aware-micro-server/src/main/kotlin/com/awareframework/micro/MainVerticle.kt) |
| Writing rows, and the statements that do it | [`MySQLVerticle.kt`](../../aware-micro-server/src/main/kotlin/com/awareframework/micro/MySQLVerticle.kt) |
| The Postgres alternative, unused by this deployment | [`PostgresVerticle.kt`](../../aware-micro-server/src/main/kotlin/com/awareframework/micro/PostgresVerticle.kt) |
| The websocket channel | [`WebsocketVerticle.kt`](../../aware-micro-server/src/main/kotlin/com/awareframework/micro/WebsocketVerticle.kt) |
| Whether a device may write at all | [`EnrolmentGate.kt`](../../aware-micro-server/src/main/kotlin/com/awareframework/micro/EnrolmentGate.kt) |
| The vocabulary of a refused write | [`Refusal.kt`](../../aware-micro-server/src/main/kotlin/com/awareframework/micro/Refusal.kt) |
| The one identifier that reaches a statement as text | [`TableName.kt`](../../aware-micro-server/src/main/kotlin/com/awareframework/micro/TableName.kt) |
| What a log may say about a request or a config | [`LogSafe.kt`](../../aware-micro-server/src/main/kotlin/com/awareframework/micro/LogSafe.kt) |
| Whether a device report says anything new | [`DeviceMetadata.kt`](../../aware-micro-server/src/main/kotlin/com/awareframework/micro/DeviceMetadata.kt) |
| The configuration's shape | [`aware-config.example.json`](../../aware-micro-server/aware-config.example.json) |

The last five are this fork's. Upstream has none of them.

---

## Two instances, one image

`aware_micro` serves iOS on `8080` from `aware-config.json`; `aware_micro_android`
serves Android on `8082` from `aware-config.android.json`. Both mount their file at
`/app/aware-config.json`, so the process has no notion of which it is.

`require_enrolment` is the difference that matters: the Android instance sets it,
because Android is the platform with an enrolment registry to check against.

Both config files are generated, by the deploy and by the Configurator's save.
Neither is in git.

---

## What changes together

- **A change to what a phone records** is a change to the study model, not to these
  files. See [shared_config](shared-config.md) and
  [configurator-backend](configurator-backend.md).
- **A new table the phones write to** has to exist in [db](db.md) first, and be
  granted to `aware_android_server` or `aware_ios_participant`.
- **The response a batch gets is a contract.** A client moves its own watermark past
  a batch on a 200, so a batch that was not stored must not get one.

---

## Traps

- **`.github/workflows/check.yml` inside this directory is upstream's**, and GitHub
  never reads it. Workflows are picked up from the repository root only.
- **`old_ui_code` is not compiled.** It has no `.kt` extension on purpose. The
  `create-*.peb` templates belong to it; `qrcode.peb` is the live one.
- **`entrypoint.sh` is dead**: nothing references it, and it names a path the image
  no longer uses.

---

## Tests

```bash
cd aware-micro-server && ./gradlew check
```

Thirty-two tests across five classes, one per fork-specific object plus the route
table. `shared_config/test_documented_counts.py` holds that number to the tests
that exist.
