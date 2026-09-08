# The checks

Eight jobs, run on every push to `main` and every pull request by
[`.github/workflows/check.yml`](../../.github/workflows/check.yml). Each one has a
local equivalent, and this is the list of both.

The versions are the ones the Dockerfiles build with. A suite that passes against a
different Python or Node says nothing about the deployment, which is why CI pins them
rather than taking whatever the runner ships.

---

## What runs, and how to run it here

| Job | Locally | Needs |
| --- | --- | --- |
| **Study model and read layer** | `pytest shared_config -q`<br>`cd analytics_api && pytest -q` | Python 3.12, `analytics_api/requirements-dev.txt` |
| **Configurator backend** | `pytest AWARE-Configurator -q` | Python 3.11, `AWARE-Configurator/requirements.txt` plus `pytest` |
| **Read layer against a real MySQL** | `cd analytics_api && pytest -m integration -q` | A local `mysqld`, 8.0 or newer |
| **Dashboard types and lint** | `cd dashboard && npm ci && npx tsc -b && npx eslint .` | Node 20 |
| **Configurator frontend** | `cd AWARE-Configurator/reactapp && npm ci && CI=true npx react-scripts test --watchAll=false` | Node 18 |
| **Micro-server** | `cd aware-micro-server && ./gradlew check` | JDK 11 |
| **Host scripts on Windows** | Covered here by the tests that strip the Unix-only pieces, in `pytest shared_config`; the platform itself only answers on CI | A Windows machine |
| **A fresh clone deploys and ingests** | See below | Docker |

Three things worth knowing about running them here rather than in CI:

- **`pytest shared_config` covers more than this package.** The suites for `setup/`
  and `db/` live there too — the entrypoint parity check, the database and ingest
  checks, and the guard that `db/init_all.sql` matches its sources.
- **The integration suite skips rather than fails when `mysqld` is absent**, so a
  checkout without MySQL still reports green. CI asks for the binary explicitly, so
  a runner without one is a red job rather than a green one that tested nothing.
- **Your Python is probably not 3.12.** The suites pass on later versions; the pins
  in `requirements.txt` were compiled for 3.12, which is what the image runs, so CI
  is the one that answers for the deployed combination.
- **The read layer and the Configurator get an environment each.** They ask for
  different versions of `cryptography` and `PyMySQL`, which is no conflict in a
  deployment — each runs in its own image, on its own Python, 3.12 and 3.11 — and is
  one inside a single virtualenv. A local environment holding both resolves to
  whichever was installed last.
- **`requirements-dev.txt` is a build product.** Its input asks for the deployed set
  with `-r requirements.txt`, so a package added to `requirements.in` reaches the
  suite only once the dev file is compiled again:
  `pip-compile --output-file=requirements-dev.txt requirements-dev.in`.
  `analytics_api/tests/test_prerequisites.py` holds the two files to each other.

---

## The deployment smoke test

The last job is the one that answers a question no unit test can: does a fresh clone
deploy, and would a participant's phone actually deliver data. It runs the same
sequence [`setup.sh`](../../setup.sh) runs, without the wizard:

```bash
python3 setup/deploy_config.py
python3 setup/check_ports.py
docker compose up --build -d --wait
python3 setup/init_study_tables.py
python3 setup/publish_authority.py
python3 setup/verify_database.py
python3 setup/verify_ingest.py
```

Two differences from a deployment, both deliberate. The dataflow is written into
`source.json` rather than answered in a form, because the deploy reads the model's
own answer when it runs outside the wizard. And the two checks are allowed to fail
the run: `setup.sh` reports them and carries on, since a researcher's stack is up
either way, while in CI a study that cannot collect is the failure worth stopping on.

It runs twice, once per Android dataflow, because `direct` and `webservice` are
different deployments: one puts a phone on the database itself, the other puts every
write through the micro-server and its enrolment gate. A smoke test covering one
leaves the other unproven. Both need a full image build, which is most of the job's
runtime — if that ever needs cutting, dropping to `webservice` alone keeps the path
this project's own code sits in.

To run it here, do it on a checkout you can throw away rather than in your working
copy: the sequence writes `.env`, `source.json` and every generated file.

---

## What is not covered

- **`setup.bat` is never executed as a deploy.** The Windows job runs the host half
  it drives, which is every script that reads the study model and hashes the
  researcher's password, and that is where each Windows failure so far has been. What
  the job cannot reach is the deploy itself, since that needs Linux containers. What
  holds the two entry scripts to each other instead is
  [`shared_config/test_setup_entrypoints.py`](../../shared_config/test_setup_entrypoints.py),
  which reads both as text and requires them to name the same scripts and wait on the
  same containers.
- **The dashboard has no tests**, only typechecking and lint. Its behaviour is
  covered indirectly, through the API the pages read.
- **`db/build_init_all.py --check-client`** compares the Android schema against the
  client's own declared tables, and needs a checkout of the client repository. It is
  run by hand when the client changes.
- [`aware-micro-server/.github/workflows/check.yml`](../../aware-micro-server/.github/workflows/check.yml)
  came with the fork and does nothing here: GitHub reads workflows only from
  `.github/workflows` at the repository root. The `micro-server` job above is what
  runs those tests.
