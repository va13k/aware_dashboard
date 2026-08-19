# Analytics Dashboard

The researcher's window into a running AWARE study. A React + TypeScript single-page
app, built with Vite and styled with Tailwind, that reads everything it shows from
the [Analytics API](../analytics_api/README.md).

In a deployment it is built to static files and served by Nginx under `/dashboard/`,
behind the researcher login; nothing needs to be installed on the host to run the
stack (see the [root README](../README.md)). This document is for working on the
interface itself.

---

## Pages

Routed under the `/dashboard` basename (`src/App.tsx`).

| Route                              | Page                 | What it answers                                                       |
| ---------------------------------- | -------------------- | --------------------------------------------------------------------- |
| `/`                                | `OverviewPage`       | What has the study collected, across every phone and both platforms?   |
| `/devices`                         | `DevicesPage`        | Who is enrolled, and when did each phone last upload?                  |
| `/devices/:platform/:deviceId`     | `DeviceDetailPage`   | One participant: sensors, coverage, study events, config diff, consent |
| `/manifest`                        | `ManifestPage`       | A per-sensor inventory of the whole dataset, for archiving or export   |
| `/logs`                            | `LogsPage`           | What the clients reported about their own operation                    |

---

## The live channel

The pages do not poll for changes. The API watches the databases once, on one
shared loop, and pushes a message over a WebSocket when rows arrive; `src/api/live.ts`
is the browser's half of that. Five ideas in it are worth knowing before changing
anything nearby.

**One socket for the whole page.** Readers subscribe to a module-level connection
rather than opening one each. It connects when the first reader appears and closes
a moment after the last one leaves — the moment being what keeps a React remount, or
a move between two pages that both listen, from tearing the connection down and
rebuilding it immediately.

**A change is a reason to refetch, not a number to add.** The counts on screen come
from cache-backed endpoints whose absolute values are the truth. Adding an arriving
delta to a local total would drift from those caches, and a drifted number looks
exactly like a correct one. So an arrival means "ask again", and the answer stays
the API's. Arrivals are coalesced over 1.5 seconds, so a phone delivering forty
tables costs one refetch rather than forty.

**The poll is still there, lengthened.** Five minutes while the channel is open, 60
seconds while it is not. A socket that has quietly stopped delivering looks exactly
like a study where nothing is happening, so a page with no other source of numbers
would leave a researcher unable to tell the difference.

**Silence is measured.** The API heartbeats every 20 seconds through a quiet study.
Hearing nothing at all for 50 seconds is treated as a dead connection — which is
what a laptop returning from sleep leaves behind — and reconnection backs off to 30
seconds with jitter, resuming from the last sequence seen.

Two hooks are the whole public surface:

| Hook                            | For                                                                     |
| ------------------------------- | ------------------------------------------------------------------------ |
| `useLiveRefresh(load, device?)` | A page that should load now, on arrival, and on a timer. Pass a `device_id` and it ignores other phones' arrivals |
| `useLiveChanges(onArrival)`     | A reader that already knows when to fetch and only needs telling that there is something new |

**The state is on screen.** `LiveStatus` sits in the global header and draws a dot
and a label, because a dead channel and a quiet study otherwise look identical —
both are a page that does not change. The counts stay correct either way, but
"nothing is arriving" and "nothing is reaching me" are different facts and only one
is about the study.

Two rules keep it from crying wolf. A recovery is drawn at once, while a drop is
drawn only once it has lasted 2.5 seconds — reconnects are ordinary and a badge
that flipped on each one would be ignored. And a socket closed because no page is
listening is not reported at all: the logs page subscribes no readers, and calling
that an outage would report the interface's own choice back at it.

| Hook                     | Returns                                                              |
| ------------------------ | ---------------------------------------------------------------------- |
| `useLiveState()`         | `"connecting" \| "open" \| "offline"` — the truth now, for deciding how often to poll |
| `useSettledLiveState()`  | The same, or `null` while it is not worth saying — for drawing            |

---

## Layout

| Path              | What lives there                                                        |
| ----------------- | ------------------------------------------------------------------------ |
| `src/pages/`      | One module per route, each owning its own data loading                   |
| `src/components/` | Everything reused across pages, including one card per sensor capability |
| `src/api/`        | `client.ts` for the REST calls, `live.ts` for the WebSocket channel       |
| `src/utils/`      | Formatting, time and timezone handling, coverage colour bands, view state |
| `src/config/`     | The sensor registry the cards and filters are built from                  |
| `src/types.ts`    | The shapes the API returns                                                |

---

## Working on it

```bash
npm install
npm run dev
```

The dev server proxies `/api` to `http://localhost:8000`, so an Analytics API has to
be running there — the compose stack's `dashboard-api` published locally, or the
service started by hand. The proxy forwards WebSocket upgrades as well, which is
what lets the live channel work outside a deployment.

```bash
npm run lint
npm run build
```

`build` runs `tsc -b` before Vite, so a type error fails the build. The bundle
currently exceeds Vite's 500 kB advisory warning; that is known and not an error.

---

## Conventions worth knowing early

- **Timestamps arrive as milliseconds** since the epoch. `src/utils/time.ts`
  normalises them; some older rows hold seconds, and anything below `1e11` is
  treated as such.
- **Everything is stored in UTC.** The researcher picks a display timezone and the
  coverage grids re-bucket from stored hours without refetching.
- **Coverage colours are the API's decision**, not the interface's. The server
  returns the band a cell landed in and `src/utils/coverageScale.ts` holds only the
  mapping from band to colour — so a bucket cannot come out one colour on screen and
  another in the workbook a researcher downloads.
- **The page is behind Nginx's login.** A REST call that meets an expired session
  is redirected to the login page; the socket is simply refused, and the fallback
  poll is what surfaces it.
