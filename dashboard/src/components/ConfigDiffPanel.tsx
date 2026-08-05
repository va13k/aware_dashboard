import type { ConfigDiff, ConfigDiffKind, ConfigDiffRow } from "../types";
import { isoDateTime } from "../utils/time";

const KIND_LABEL: Record<ConfigDiffKind, string> = {
  changed: "Changed",
  only_on_server: "Only in the deployed config",
  only_on_device: "Only on the device",
};

const KIND_ORDER: ConfigDiffKind[] = [
  "changed",
  "only_on_server",
  "only_on_device",
];

function formatValue(value: unknown): string {
  if (value === undefined) return "—";
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return value === "" ? '""' : value;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function DiffCell({ value }: { value: unknown }) {
  const absent = value === undefined;
  return (
    <td
      className={`px-3 py-2 align-top font-mono text-[11px] wrap-break-word ${
        absent ? "text-sage" : "text-ink"
      }`}
    >
      {formatValue(value)}
    </td>
  );
}

function DiffGroup({
  kind,
  rows,
}: {
  kind: ConfigDiffKind;
  rows: ConfigDiffRow[];
}) {
  if (rows.length === 0) return null;
  return (
    <>
      <tr>
        <th
          colSpan={3}
          className="bg-card-strong/70 px-3 py-1.5 text-left text-[10px] font-semibold uppercase tracking-[0.5px] text-sage"
        >
          {KIND_LABEL[kind]} · {rows.length}
        </th>
      </tr>
      {rows.map((row) => (
        <tr key={row.path} className="border-t border-wire">
          <td className="px-3 py-2 align-top font-mono text-[11px] font-semibold text-ink wrap-break-word">
            {row.path}
          </td>
          <DiffCell value={row.server_value} />
          <DiffCell value={row.device_value} />
        </tr>
      ))}
    </>
  );
}

/**
 * The deployed study config versus the config the phone actually carries.
 *
 * Both sides are compared server-side over an allowlist, so no credential ever
 * reaches this component - a differing secret produces no row at all.
 */
export default function ConfigDiffPanel({ diff }: { diff: ConfigDiff }) {
  const unknown = diff.config_status === "unknown";
  const empty = !unknown && diff.rows.length === 0;

  return (
    <section className="rounded-3xl border border-wire bg-card p-5 shadow-card backdrop-blur-xl">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-bold text-ink">Config differences</h2>
        <p className="text-[11px] text-sage">
          Deployed {isoDateTime(diff.server_updated_at)} · device{" "}
          {isoDateTime(diff.device_updated_at)}
        </p>
      </div>

      <p className="mb-3 text-[12px] text-sage">
        Device-side config updates are{" "}
        <span className="font-semibold text-ink">
          {diff.config_update_enabled ? "enabled" : "disabled"}
        </span>{" "}
        in the deployed config
        {diff.device_config_update_enabled !== diff.config_update_enabled ? (
          <>
            , but the phone still has them{" "}
            <span className="font-semibold text-ink">
              {diff.device_config_update_enabled ? "enabled" : "disabled"}
            </span>
          </>
        ) : null}
        .
      </p>

      {unknown ? (
        <div className="rounded-2xl border border-wire bg-card-strong/70 p-6 text-center text-[13px] text-sage">
          {diff.status_reason === "no_device_config"
            ? "Device has not reported a parseable config."
            : diff.status_reason === "no_server_config"
              ? "No deployed config is available to compare against."
              : "Config state is unknown."}
        </div>
      ) : empty ? (
        <div className="rounded-2xl border border-wire bg-teal-soft/40 p-6 text-center text-[13px] text-teal">
          Device config matches the deployed config.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-wire">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="text-[10px] uppercase tracking-[0.5px] text-sage">
                <th className="px-3 py-2 font-semibold">Setting</th>
                <th className="px-3 py-2 font-semibold">Deployed</th>
                <th className="px-3 py-2 font-semibold">Device</th>
              </tr>
            </thead>
            <tbody>
              {KIND_ORDER.map((kind) => (
                <DiffGroup
                  key={kind}
                  kind={kind}
                  rows={diff.rows.filter((row) => row.kind === kind)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
