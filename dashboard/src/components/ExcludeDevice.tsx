import { useState } from "react";
import { excludeDevice, includeDevice } from "../api/client";
import type { DeviceExclusion } from "../types";
import { absoluteTime } from "../utils/time";

/**
 * Taking a participant's data out of the analysis, without taking it out of the
 * database.
 *
 * A separate decision from withdrawal, and deliberately a separate action.
 * Withdrawal stops the study expecting more data; this answers what happens to
 * what was already collected, which consent forms answer differently. The default
 * is the conservative one, so nothing here happens on its own.
 *
 * Excluding is not deleting and not hiding. The device keeps its place in the
 * lists and the coverage grids, marked — a participant the dashboard had quietly
 * dropped would look exactly like one who never took part. What changes is the
 * exports, because that is where the analysis dataset leaves.
 */
export default function ExcludeDevice({
  platform,
  deviceId,
  excluded,
  records,
  onChanged,
}: {
  platform: "android" | "ios";
  deviceId: string;
  excluded: DeviceExclusion | null | undefined;
  /** How many records this device holds, so the decision names its own cost. */
  records?: number;
  /** Called after a change lands, so the page re-reads what the server now holds. */
  onChanged: () => void | Promise<void>;
}) {
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const buttonClass =
    "inline-flex h-8 shrink-0 items-center justify-center rounded-lg border px-3 text-[11px] font-semibold uppercase tracking-[0.4px] transition-colors disabled:opacity-50";

  async function act(run: () => Promise<unknown>) {
    setBusy(true);
    setFailed(null);
    try {
      await run();
      setAsking(false);
      await onChanged();
    } catch (error) {
      setFailed(error instanceof Error ? error.message : "The change was refused");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13px] text-ink">
          {excluded ? "Left out of the analysis" : "Included in the analysis"}
          {records ? (
            <span className="ml-1.5 text-sage">
              {records.toLocaleString()} {records === 1 ? "record" : "records"}
              {excluded ? " held back from exports" : ""}
            </span>
          ) : null}
        </span>
        {excluded ? (
          <span
            title={`Excluded ${absoluteTime(excluded.excluded_at)}`}
            className="rounded border border-short/40 bg-short/10 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.3px] text-short"
          >
            excluded
          </span>
        ) : null}
      </div>

      {excluded?.note ? (
        <p className="text-[12px] text-sage">Reason: {excluded.note}</p>
      ) : null}

      {asking ? (
        <div className="flex flex-col gap-2 rounded-xl border border-wire bg-card-strong p-3">
          <label className="flex flex-col gap-1 text-[11px] font-semibold uppercase tracking-[0.4px] text-sage">
            Why (optional)
            <input
              type="text"
              value={note}
              maxLength={255}
              placeholder="Withdrew consent to analysis"
              onChange={(event) => setNote(event.target.value)}
              className="h-8 rounded-lg border border-wire bg-card px-2 text-[13px] font-normal normal-case tracking-normal text-ink focus:border-teal focus:outline-none"
            />
          </label>
          <p className="text-[11px] leading-relaxed text-sage">
            Consent forms differ on what they permit, so the reason is worth
            keeping beside the decision.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => act(() => excludeDevice(platform, deviceId, note))}
              className={`${buttonClass} cursor-pointer border-short/40 bg-short/10 text-short hover:border-short`}
            >
              {busy ? "Excluding…" : "Exclude from analysis"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setAsking(false)}
              className={`${buttonClass} cursor-pointer border-wire bg-card-strong text-sage hover:border-teal hover:text-teal`}
            >
              Cancel
            </button>
          </div>
          <p className="text-[11px] text-sage">
            Nothing is deleted.{" "}
            {records
              ? `${records.toLocaleString()} ${
                  records === 1 ? "record" : "records"
                } stay in the database and on this page, and stop appearing in exports.`
              : "The data stays in the database and on this page, and stops appearing in exports."}
          </p>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          {excluded ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => act(() => includeDevice(platform, deviceId))}
              className={`${buttonClass} cursor-pointer border-wire bg-card-strong text-sage hover:border-teal hover:text-teal`}
            >
              {busy ? "Including…" : "Put back in the analysis"}
            </button>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setNote("");
                setAsking(true);
              }}
              className={`${buttonClass} cursor-pointer border-wire bg-card-strong text-sage hover:border-short hover:text-short`}
            >
              Exclude from analysis
            </button>
          )}
        </div>
      )}

      {failed ? (
        <p className="text-[12px] text-short" role="alert">
          {failed}
        </p>
      ) : null}

      <p className="text-[11px] text-sage">
        {excluded
          ? "This device is left out of every export. Removing its rows from the database is a database administrator's job — the dashboard reads study data and cannot delete it."
          : "Excluding keeps the data and leaves it out of exports. Deleting it is a separate request to a database administrator."}
      </p>
    </div>
  );
}
