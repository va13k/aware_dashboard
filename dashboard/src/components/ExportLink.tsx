import { useCallback, useEffect, useRef, useState } from "react";

interface Props {
  href: string;
  label?: string;
  title?: string;
  className?: string;
  disabled?: boolean;
}

const POLL_MS = 700;

/**
 * A CSV/ZIP download button that reports what it is doing.
 *
 * Exports large enough to be worth watching announce themselves first: a POST
 * to the same URL registers a job and settles the row count, the browser is
 * then handed the download as an ordinary navigation, and this polls the job to
 * fill a bar underneath. Letting the browser fetch the file — rather than
 * reading it here and assembling a blob — is what keeps a multi-gigabyte export
 * off the page's heap.
 *
 * Endpoints that do not offer a job (the ZIP exports) answer the POST with 405
 * and the click falls through to the plain navigation it has always been, with
 * a brief "starting" state so the button still acknowledges the press.
 */
export default function ExportLink({
  href,
  label = "CSV",
  title = "Export CSV",
  className = "",
  disabled = false,
}: Props) {
  const [percent, setPercent] = useState<number | null>(null);
  const [done, setDone] = useState(0);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const cancelled = useRef(false);
  const anchor = useRef<HTMLAnchorElement>(null);
  // The label is replaced by a percentage while the export runs, so the button
  // is held at the width it had when idle. Without it every tick would resize
  // the control and nudge whatever sits beside it in the row.
  const [heldWidth, setHeldWidth] = useState<number | null>(null);

  useEffect(() => () => {
    cancelled.current = true;
  }, []);

  /** Hands the file to the browser, which streams it straight to disk. */
  const download = useCallback((url: string) => {
    const link = document.createElement("a");
    link.href = url;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }, []);

  const follow = useCallback(async (jobId: string) => {
    for (;;) {
      if (cancelled.current) return;
      const response = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
      if (!response.ok) return;
      const job = await response.json();
      if (cancelled.current) return;
      setPercent(job.percent);
      setDone(job.done ?? 0);
      if (job.state === "error") {
        setFailed(job.error || "Export failed");
        return;
      }
      if (job.state === "done") {
        setPercent(100);
        return;
      }
      // Anything else that is no longer running — a cancelled download, say —
      // ends the watch quietly and hands the button back, rather than spinning
      // over work that stopped.
      if (job.state !== "running") return;
      await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    }
  }, []);

  const onClick = useCallback(
    async (event: React.MouseEvent<HTMLAnchorElement>) => {
      if (busy) {
        event.preventDefault();
        return;
      }
      event.preventDefault();
      setHeldWidth(anchor.current?.offsetWidth ?? null);
      setBusy(true);
      setFailed(null);
      setPercent(null);
      setDone(0);

      let jobId: string | null = null;
      try {
        const response = await fetch(href, { method: "POST" });
        if (response.ok) {
          jobId = (await response.json()).id ?? null;
        } else if (response.status === 404) {
          const body = await response.json().catch(() => ({}));
          setFailed(body.detail || "Nothing to export");
          setBusy(false);
          return;
        }
      } catch {
        // Offering progress is best-effort; the download still has to happen.
      }

      const separator = href.includes("?") ? "&" : "?";
      download(jobId ? `${href}${separator}job=${jobId}` : href);

      if (jobId) {
        await follow(jobId);
      }
      if (!cancelled.current) {
        setBusy(false);
        setHeldWidth(null);
        // Let a finished bar stand briefly, then clear it.
        setTimeout(() => !cancelled.current && setPercent(null), 1200);
      }
    },
    [busy, download, follow, href],
  );

  const base = `inline-flex h-7 items-center justify-center gap-1.5 rounded-lg border px-2 text-[10px] font-semibold uppercase tracking-[0.4px] ${className}`;

  /** While it runs the button says so itself — a hairline bar alone is easy to
      miss on a control this small, and an export can last minutes.
   *
   *  A percentage needs a trustworthy total. The row count behind it comes from
   *  the record-count cache, which lags whatever arrived since its last refresh,
   *  so once the export passes that figure the server stops reporting a
   *  percentage and this counts rows instead — moving, honest, and never
   *  claiming to be finished before it is. */
  const rows =
    done >= 1_000_000
      ? `${(done / 1_000_000).toFixed(1)}M rows`
      : done >= 1_000
        ? `${Math.round(done / 1000)}K rows`
        : `${done} rows`;
  const runningLabel =
    percent != null
      ? percent >= 100
        ? "Done"
        : `${Math.floor(percent)}%`
      : done > 0
        ? rows
        : "Preparing…";

  if (disabled) {
    return (
      <span
        title="No records to export"
        className={`${base} cursor-not-allowed border-wire bg-card-strong text-sage/30`}
      >
        {label}
      </span>
    );
  }

  const showBar = busy || percent !== null;

  return (
    // `relative` with an absolutely-placed bar keeps every card's header row
    // exactly the height it was: the bar is drawn under the button, not in flow.
    <span className="relative inline-flex">
      <a
        ref={anchor}
        href={href}
        onClick={onClick}
        style={heldWidth ? { minWidth: heldWidth } : undefined}
        title={failed || title}
        aria-busy={busy}
        className={`${base} ${
          failed
            ? "border-red-300 bg-red-50 text-red-600"
            : showBar
              ? "border-teal bg-teal-soft text-teal"
              : "border-wire bg-card-strong text-sage transition-colors hover:border-teal hover:text-teal"
        }`}
      >
        {showBar && !failed && (
          <span
            aria-hidden
            className="h-2.5 w-2.5 shrink-0 animate-spin rounded-full border-[1.5px] border-teal/30 border-t-teal"
          />
        )}
        {failed ? "Failed" : showBar ? runningLabel : label}
      </a>

      {showBar && !failed && (
        <span
          aria-hidden
          className="pointer-events-none absolute -bottom-[3px] left-0 right-0 h-[3px] overflow-hidden rounded-full bg-wire"
        >
          <span
            className={`block h-full rounded-full bg-teal ${
              percent == null ? "w-1/3 animate-pulse" : "transition-[width] duration-300"
            }`}
            style={percent == null ? undefined : { width: `${percent}%` }}
          />
        </span>
      )}
    </span>
  );
}
