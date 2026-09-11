# Working in this repository

A self-hosted platform for mobile sensing research: phones running the AWARE client
send sensor rows to a server a researcher deploys, and a dashboard reads them back.
Seven services as eleven containers, brought up by one `docker compose` project.

This file and `CLAUDE.md` are the same document. Edit both, or edit one and copy it
across; `shared_config/test_agent_instructions.py` fails when they differ.

---

## Read the map before reading code

Every component has a note in [`docs/index.md`](docs/index.md) saying which file
owns what. Start there rather than searching the tree: a question of the form "where
does X live" is answered by one note, and the notes are held to real paths by a
test, so a path in one exists.

| To find out | Read |
| --- | --- |
| Which file owns a concept | [`docs/index.md`](docs/index.md) and the component note it links to |
| What runs and how a request is routed | [`docs/dev/architecture.md`](docs/dev/architecture.md) |
| What a deploy does, in order | [`docs/dev/deploy-pipeline.md`](docs/dev/deploy-pipeline.md) |
| What the checks are and how to run one | [`docs/dev/checks.md`](docs/dev/checks.md) |
| Why a component is built the way it is | Its own `README.md`, beside its code |
| What a researcher is told to do | [`README.md`](README.md) |

---

## Two declared choices change what is true

Read them before concluding anything about data flow or credentials. Both live in
`source.json` and are reported by `shared_config`, never guessed.

**Android dataflow** (`deployment.dataflow.android`, read by `shared_config/dataflow.py`)
is `webservice` or `direct`. On `webservice` a phone posts to `micro-server-android`,
which writes to MySQL. On `direct` the phone opens MySQL itself. iOS is always
`webservice`.

**Database placement** (derived from `database.host` by `shared_config/placement.py`)
is `bundled` or `external`. Bundled runs MySQL as a container in this project;
external points at a server the institution already has.

A claim that holds on one setting and not the other is wrong unless it names which.

---

## The study model, and the files generated from it

`source.json` is the study: what it collects, from whom, on what schedule. It is
materialised from `source.example.json` on first deploy and is not in git.

Everything in
[architecture.md's generated-files table](docs/dev/architecture.md#the-generated-files-and-who-reads-them)
is a product of that model plus `.env`. None of it is committed, and none of it is
edited by hand. Change the model or the template and run the deploy again.

Three products are worth naming because editing them looks reasonable and is not:

- **`db/init_all.sql`** is concatenated by `db/build_init_all.py` from the four
  fragments beside it. Edit a fragment, then run `python3 db/build_init_all.py`.
  `--check` fails when the product is stale, and so does CI.
- **`aware-micro-server/aware-config.json`** and its `.android` sibling are written
  by the deploy and by the Configurator's save. The next of either overwrites yours.
- **`analytics_api/requirements-dev.txt`** is compiled. Add to `requirements-dev.in`
  and run `pip-compile`.

---

## Conventions

**Comments** say what the code does and why the reason is not visible. No negatives,
no references to plans or documents, no history of what changed. Nothing on width,
padding or styling choices.

**Commit titles** are one line, `Area: What it does`, where the area names a
component (`API`, `Micro`, `Configurator`, `Setup`, `Config`, `DB`, `Nginx`,
`Infra`, `Docs`), never a concept. No body, no trailers.

**Documents** carry only what exists now. Plans are not committed; `docs/plans/` is
ignored. One fact has one owner: link to it rather than restating it, and when a
document states a count, add it to `shared_config/test_documented_counts.py`.

---

## How to work

Diagnose and explain before changing anything. Then implement, then run the tests,
then propose commits rather than making them.

Verify a claim against the code before writing it down. Reproduce a bug before
fixing it, and check that a new test fails without the fix.

The two suites that cover the deployment and the study model:

```bash
python3 -m pytest shared_config -q && python3 db/build_init_all.py --check
```

Everything else, including which Python each component wants, is in
[`docs/dev/checks.md`](docs/dev/checks.md).
