import { useEffect } from "react";
import LogsPanel from "./LogsPanel";

/**
 * Full-screen modal wrapping the logs table for one device. The body scrolls,
 * so the pinned pager and the table stay usable on a long page; 50 rows a page
 * keeps each page light.
 */
export default function LogsModal({
  deviceId,
  platform,
  title,
  onClose,
}: {
  deviceId: string;
  platform: "android" | "ios";
  title?: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="my-6 flex max-h-[88vh] w-full max-w-6xl flex-col rounded-3xl border border-wire bg-card p-5 shadow-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-[16px] font-bold text-ink">Client logs</h2>
            {title ? <p className="text-[12px] text-sage">{title}</p> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 cursor-pointer rounded-lg border border-wire bg-card-strong px-2.5 py-1 text-[14px] font-semibold text-sage transition-colors hover:border-teal hover:text-teal"
          >
            ✕
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <LogsPanel deviceId={deviceId} platform={platform} pageSize={50} />
        </div>
      </div>
    </div>
  );
}
