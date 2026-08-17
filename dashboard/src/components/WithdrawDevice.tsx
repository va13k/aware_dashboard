import { useState } from "react";
import { reopenDeviceEnrolment, withdrawDevice } from "../api/client";
import type { DeviceEnrolmentSummary, EnrolmentWindow } from "../types";
import { absoluteDate, absoluteTime } from "../utils/time";
import { localInputToTs, tsToLocalInput } from "../utils/timeRange";

/**
 * Recording that a participant has left the study.
 *
 * The reliable path, because a researcher usually finds out by being told rather
 * than by watching a phone go quiet. Silence is information, not enforcement: a
 * participant on holiday with a dead battery has not withdrawn, so nothing here
 * happens on its own.
 *
 * The date is editable and defaults to now, because the two cases differ. Told
 * during the conversation, now is right. Told a week later, the moment the
 * participant *acted* is what the window has to close on — otherwise every day in
 * between reads as expected-and-missing on a grid they had already left.
 *
 * Closing the window is not deletion. It stops the study expecting more data; what
 * happens to the data already collected is a separate and deliberate decision,
 * because consent forms answer that question differently.
 */

function windowLabel(window: EnrolmentWindow): string {
  const from = absoluteDate(window.joined_at);
  return window.left_at == null
    ? `${from} — still in the study`
    : `${from} — ${absoluteDate(window.left_at)}`;
}

export default function WithdrawDevice({
  deviceId,
  enrolment,
  windows,
  onChanged,
}: {
  deviceId: string;
  enrolment: DeviceEnrolmentSummary | null | undefined;
  windows: EnrolmentWindow[];
  /** Called after a change lands, so the page re-reads what the server now holds. */
  onChanged: () => void | Promise<void>;
}) {
  const [asking, setAsking] = useState(false);
  const [when, setWhen] = useState(() => tsToLocalInput(Date.now()));
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const withdrawn = enrolment?.left_at != null;
  // The current window only. A participant marked as having left and then back of
  // their own accord is in the study now, and carrying the mark forward would
  // label an active participant with a correction that no longer applies to them.
  const byResearcher = windows.at(-1)?.left_source === "manual";

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

  function recordWithdrawal() {
    const leftAt = localInputToTs(when);
    if (leftAt == null) {
      setFailed("Choose a valid withdrawal date and time");
      return;
    }
    void act(() => withdrawDevice(deviceId, { leftAt }));
  }

  const buttonClass =
    "inline-flex h-8 shrink-0 items-center justify-center rounded-lg border px-3 text-[11px] font-semibold uppercase tracking-[0.4px] transition-colors disabled:opacity-50";

  if (!enrolment) {
    return (
      <p className="text-[13px] text-sage">
        The study has no record of this phone joining, so there is no enrolment
        window to close.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13px] text-ink">
          {withdrawn ? "Left the study" : "In the study"}
          <span className="ml-1.5 text-sage">
            {windows.length === 1
              ? windowLabel(windows[0])
              : `${windows.length} spells, latest ${windowLabel(
                  windows[windows.length - 1],
                )}`}
          </span>
        </span>
        {byResearcher ? (
          <span
            title="Recorded from the dashboard rather than reported by the phone"
            className="rounded border border-wire px-1.5 py-0.5 text-[10px] uppercase tracking-[0.3px] text-sage"
          >
            marked here
          </span>
        ) : null}
      </div>

      {asking ? (
        <div className="flex flex-col gap-2 rounded-xl border border-wire bg-card-strong p-3">
          <label className="flex flex-col gap-1 text-[11px] font-semibold uppercase tracking-[0.4px] text-sage">
            When they left
            <input
              required
              type="datetime-local"
              value={when}
              onChange={(event) => setWhen(event.target.value)}
              className="h-8 rounded-lg border border-wire bg-card px-2 text-[13px] font-normal normal-case tracking-normal text-ink focus:border-teal focus:outline-none"
            />
          </label>
          <p className="text-[11px] leading-relaxed text-sage">
            The moment the participant acted, not when you were told. A notice that
            arrives late still has to land on the day it happened.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={recordWithdrawal}
              className={`${buttonClass} cursor-pointer border-short/40 bg-short/10 text-short hover:border-short`}
            >
              {busy
                ? "Recording…"
                : withdrawn
                  ? "Update withdrawal"
                  : "Record withdrawal"}
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
            This stops the study expecting more data. It keeps everything already
            collected.
          </p>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setAsking(true);
              setWhen(
                tsToLocalInput(
                  withdrawn && enrolment.left_at
                    ? enrolment.left_at
                    : Date.now(),
                ),
              );
            }}
            className={`${buttonClass} cursor-pointer border-wire bg-card-strong text-sage hover:border-short hover:text-short`}
          >
            {withdrawn ? "Change the date" : "Mark as withdrawn"}
          </button>
          {byResearcher ? (
            <button
              type="button"
              disabled={busy}
              title="Clear this correction and take the enrolment from the phone's own study log again"
              onClick={() => act(() => reopenDeviceEnrolment(deviceId))}
              className={`${buttonClass} cursor-pointer border-wire bg-card-strong text-sage hover:border-teal hover:text-teal`}
            >
              Undo
            </button>
          ) : null}
        </div>
      )}

      {failed ? (
        <p className="text-[12px] text-short" role="alert">
          {failed}
        </p>
      ) : null}

      {withdrawn && enrolment.left_at ? (
        <p className="text-[11px] text-sage">
          Data timestamped after {absoluteTime(enrolment.left_at)} reads as outside
          the study on every grid and export.
        </p>
      ) : null}
    </div>
  );
}
