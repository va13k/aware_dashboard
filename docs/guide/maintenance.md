# Maintenance

What a deployment needs after it is running: taking a new version, minting a
credential again, and the occasional operation against the database itself. None of
it is part of deploying a study or of collecting from it, and none of it is needed
on a schedule.

---

## Updating a deployment

Take the new version and redeploy on the configuration already there:

```bash
git pull
```

Then run `./setup.sh` on macOS or Linux, or `setup.bat` on Windows, and choose
**1) Deploy with current config**. The wizard does not open. The images are rebuilt,
the containers are recreated, and everything the deployment knows about your study is
read from the files it already holds.

**What is kept.** The collected data, which lives in a Docker volume nothing here
touches. The study in `source.json`: the deploy fills in the credentials it generates
and applies the choices already declared there, and what a researcher set in the
Configurator stays as they left it. And `.env`, which is rewritten but keeps every
variable holding a value, including ones you added by hand such as `SETUP_BIND` or a
broker port of your own. Comments you wrote in that file are not kept, since it is
rewritten as settings rather than edited.

**The database catches up on its own.** There is no migration step to run and no
version to check. The whole schema is applied every time the database starts, and
columns added in a later version arrive through guarded statements that leave a table
already matching it alone. The study's accounts have their passwords re-applied from
`.env` on the same run, which is what keeps the file and the server from drifting
apart.

**Participants do nothing.** Their phones hold a study address and a key that an
update does not change, so an upgrade is invisible to them. Two things would not be
invisible, and neither is part of updating: rotating the study key, below, and
changing the dataflow, which are the two changes that make every participant join
again.

**There is a short interruption** while the containers are recreated, and a longer one
the first time, since the images are built from source on your machine. Nothing is
lost by it: a phone that cannot reach the server keeps its data and delivers it on the
next upload.

When it finishes, the deploy runs its two checks and says whether the database still
answers for this study and whether a phone's data would still arrive. Both are worth
reading rather than scrolling past.

---

## Rotating a credential

Two credentials can be minted again, and both live on phones that are out in the
field. Name one in `.env` and redeploy:

```bash
echo "ROTATE=study-key" >> .env
```

| Name | Replaces | What it costs |
| --- | --- | --- |
| `study-key` | The key in the address a phone uploads to and reads its configuration from | **Every participant rejoins**, by scanning the study's QR code again. Until they do, their phone holds an address that answers nothing |
| `broker` | The two passwords the message broker holds | Prompts stop reaching a phone until it has read its configuration again, which it does on its own schedule |

Both at once is `ROTATE=study-key,broker`. A name the deployment does not mint stops
the run and says which names it has, rather than deploying something you did not ask
for.

Then redeploy the way an update does, with **1) Deploy with current config**. The
deploy prints what it replaced and what that costs:

```
minted again: study-key
  every phone holds the old address: a participant rejoins by scanning the study's QR code again
```

The request is cleared once it has been acted on, so a rotation happens on the deploy
that asked for it and not on every deploy afterwards. That matters more than it
sounds: a study whose address changed on every redeploy would collect nothing.

Rotate when a credential has been somewhere it should not have been, and reckon with
the cost first. A study key is not a password a researcher types; it is the address
participants are holding.

---

## Reclaiming sensor label space

The ten physical sensor tables are created without a `label` column. The client
fills that column from an Android broadcast a study never sends, so on a database
created before it was dropped it holds one empty string per row across the
highest-volume tables. `db/reclaim-sensor-label.sql` removes it there:

```bash
docker exec -i aware_mysql mysql -uroot -p<root-password> aware_android < db/reclaim-sensor-label.sql
```

The script reports each table it touches and can be re-run: a table already
matching the schema is left alone. `bluetooth`, `locations` and `wifi` keep their
`label`, which the client writes.
