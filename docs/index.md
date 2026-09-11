# The map

Where things live. One note per component, each answering "which file owns this"
rather than explaining the component: the prose is in the component's own
`README.md`, and this is the index into it.

Every path a note names is held to a real file by
`shared_config/test_docs_map.py`, so a path here exists.

Open the **repository root** as the Obsidian vault, not `docs/`. The notes link out
to component READMEs and to source files, and those resolve only from the root.
Links are ordinary markdown rather than wikilinks, so the same note reads on GitHub
and still joins the graph in Obsidian.

---

## Before anything else

Two declared choices change what is true about data flow and credentials. A claim
that holds under one and not the other has to name which.

| Choice | Declared in | Values | Decided by |
| --- | --- | --- | --- |
| Android dataflow | `deployment.dataflow.android` | `webservice`, `direct` | [`shared_config/dataflow.py`](../shared_config/dataflow.py) |
| Database placement | derived from `database.host` | `bundled`, `external` | [`shared_config/placement.py`](../shared_config/placement.py) |

`source.json` is the study model that carries both. It is materialised from
`source.example.json` on first deploy and is not in git.

---

## The components

Roughly in the order a study passes through them.

| Component | Note | What it is |
| --- | --- | --- |
| `shared_config/` | [shared_config](map/shared-config.md) | The study model, and the two platform configs derived from it |
| `AWARE-Configurator/` | [Configurator: the back end](map/configurator-backend.md) | Django: the form's endpoints, and the save that regenerates every config |
| `AWARE-Configurator/reactapp/` | [Configurator: the front end](map/configurator-frontend.md) | The form a researcher fills in, and the four layers a sensor setting crosses |
| `setup/` | [setup](map/setup.md) | The wizard, the deploy, and the checks that say whether it worked |
| `db/` | [db](map/db.md) | The MySQL schema, built rather than migrated |
| `nginx/` | [nginx](map/nginx.md) | The only public surface, and what each caller has to prove |
| `aware-micro-server/` | [micro-server](map/micro-server.md) | What a phone posts to, and the rules this fork added |
| `analytics_api/` | [analytics_api](map/analytics-api.md) | The read layer the dashboard asks |
| `dashboard/` | [dashboard](map/dashboard.md) | What a researcher looks at |

---

## The whole-stack documents

| Document | Answers |
| --- | --- |
| [architecture.md](dev/architecture.md) | What runs, how a request is routed, where a sensor row comes from |
| [deploy-pipeline.md](dev/deploy-pipeline.md) | What a deploy does, in order |
| [checks.md](dev/checks.md) | What the checks are, and how to run one here |
| [guide/own-database.md](guide/own-database.md) | Pointing a study at a database the institution already runs |
| [guide/maintenance.md](guide/maintenance.md) | Upgrading, rotating a credential, reclaiming label space |
| [the root README](../README.md) | What a researcher is told to do |
