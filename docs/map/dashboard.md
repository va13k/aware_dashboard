# dashboard

What a researcher looks at. React and TypeScript on Vite, Node 20, served as static
files. It reads the [analytics_api](analytics-api.md) and writes nothing of its own.
Prose: [`dashboard/README.md`](../../dashboard/README.md), which lists the pages and
the directories.

---

## What owns what

| Concept | File |
| --- | --- |
| Routes, and the shell every page sits in | [`src/App.tsx`](../../dashboard/src/App.tsx) |
| Every REST call | [`src/api/client.ts`](../../dashboard/src/api/client.ts) |
| The live channel | [`src/api/live.ts`](../../dashboard/src/api/live.ts) |
| The sensor registry the cards and filters are built from | [`src/config/sensors.ts`](../../dashboard/src/config/sensors.ts) |
| The shapes the API returns | [`src/types.ts`](../../dashboard/src/types.ts) |
| The dev proxy to the API, WebSocket upgrades included | [`vite.config.ts`](../../dashboard/vite.config.ts) |

### The utilities

| Module | What it decides |
| --- | --- |
| [`time.ts`](../../dashboard/src/utils/time.ts) | Every timestamp the dashboard renders goes through here |
| [`timeRange.ts`](../../dashboard/src/utils/timeRange.ts) | The span a set of records covers |
| [`period.ts`](../../dashboard/src/utils/period.ts) | The chosen period, with all time said explicitly |
| [`coverageScale.ts`](../../dashboard/src/utils/coverageScale.ts) | What colour a coverage cell takes, and what the colour claims |
| [`coverageView.ts`](../../dashboard/src/utils/coverageView.ts) | The coverage grid's own view state, held in the URL |
| [`sensorView.ts`](../../dashboard/src/utils/sensorView.ts) | How the sensor grids are filtered, shared between pages |
| [`requirements.ts`](../../dashboard/src/utils/requirements.ts) | What the study config says a phone should be sending |
| [`devices.ts`](../../dashboard/src/utils/devices.ts) | A readable name for a phone, falling back to a shortened id |
| [`headerSlot.ts`](../../dashboard/src/utils/headerSlot.ts) | The one slot a page fills in the shared header |
| [`stats.ts`](../../dashboard/src/utils/stats.ts) | Minima, maxima and the rest, over a series |

---

## What changes together

- **A new sensor card** needs an entry in `config/sensors.ts`, a component in
  `src/components/`, and an endpoint on the router for its platform. See
  [analytics_api](analytics-api.md).
- **A shape the API changes** is a change to `src/types.ts`. `npm run build` runs
  `tsc -b` first, so a mismatch fails the build rather than the page.
- **A coverage band's meaning** lives in `coverageScale.ts` and in the API's
  `coverage_matrix.py`. The colour and the claim behind it have to agree.

---

## Traps

- **Composing a message is on the messages page only.** The device page shows a
  phone's messages and cannot write one.
- **The bundle exceeds Vite's 500 kB advisory.** Known, and not an error.
- **The dev server needs an API on `localhost:8000`**, either the stack's
  `dashboard-api` published locally or one started by hand.

---

## Tests

```bash
cd dashboard && npx tsc -b && npx eslint .
```

There is no unit suite. Types and lint are what CI runs, as the `Dashboard` job.
