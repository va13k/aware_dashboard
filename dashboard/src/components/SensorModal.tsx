import { useEffect, useMemo, useState } from "react";
import type { SensorConfig, SensorData } from "../config/sensors";
import { sensorDataKeys, sensorHasSeries } from "../config/sensors";
import type { SensorRecord, SeriesBucket } from "../types";
import {
  fetchSensor,
  fetchSensorSeries,
  exportSensorHref,
} from "../api/client";
import {
  DEFAULT_RANGE,
  RANGE_PRESETS,
  rangeFromTs,
  downsample,
  localInputToTs,
  tsToLocalInput,
  type RangeKey,
} from "../utils/timeRange";
import SensorChart from "./SensorChart";
import SeriesChart from "./SeriesChart";
import ExportLink from "./ExportLink";

/**
 * On-demand chart for a single sensor.
 *
 * Nothing is fetched until this opens; then it pulls the selected window (last
 * hour by default) and lets the user widen it. A window is fetched uncapped and
 * downsampled for the plot, while the device's true total is shown in the header.
 */
export default function SensorModal({
  config,
  platform,
  deviceId,
  totalCount,
  anchorTs,
  onClose,
}: {
  config: SensorConfig;
  platform: "android" | "ios";
  deviceId: string;
  totalCount: number;
  /**
   * The sensor's most recent upload (ms). Presets are measured back from here,
   * not from "now" - a study phone that last uploaded days ago should still
   * show its last hour/week of data rather than an empty recent window.
   */
  anchorTs: number | null;
  onClose: () => void;
}) {
  const [range, setRange] = useState<RangeKey | "custom">(DEFAULT_RANGE);
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [raw, setRaw] = useState<SensorData>({});
  const [series, setSeries] = useState<SeriesBucket[]>([]);
  const [fetchedCount, setFetchedCount] = useState(0);
  const [loading, setLoading] = useState(true);

  // Numeric sensors are drawn from a server-bucketed series (consistent point
  // density at any zoom); event/enum sensors keep the raw-record cards.
  const useSeries = sensorHasSeries(platform, config.key);

  // Seed the custom fields with the last 24 h the first time custom is picked,
  // so the chart has something to show before the user narrows it.
  const enableCustom = () => {
    const now = Date.now();
    if (!customFrom) setCustomFrom(tsToLocalInput(now - 24 * 60 * 60 * 1000));
    if (!customTo) setCustomTo(tsToLocalInput(now));
    setRange("custom");
  };

  const keys = useMemo(() => sensorDataKeys(config.key), [config.key]);

  // Fallback anchor for a sensor with no last-upload timestamp, captured once at
  // mount so the window stays stable across re-renders.
  const [mountNow] = useState(() => Date.now());

  // The selected window, shared by the data fetch and the CSV export so the
  // download covers exactly the range on screen (preset back from the sensor's
  // last upload, or the custom bounds). "All" leaves both open.
  const bounds = useMemo<{ fromTs?: number; toTs?: number }>(() => {
    if (range === "custom") {
      return {
        fromTs: localInputToTs(customFrom) ?? undefined,
        toTs: localInputToTs(customTo) ?? undefined,
      };
    }
    const anchor = anchorTs ?? mountNow;
    const fromTs = rangeFromTs(range, anchor);
    // Presets bound the top at the sensor's latest upload so the CSV covers the
    // same window as the chart — a 1 h chart yields the last hour of data.
    // "All" leaves both ends open.
    return { fromTs, toTs: fromTs == null ? undefined : anchor };
  }, [range, customFrom, customTo, anchorTs, mountNow]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;

    const load = () => {
      setLoading(true);
      const { fromTs, toTs } = bounds;

      if (useSeries) {
        fetchSensorSeries(platform, deviceId, config.key, {
          fromTs,
          toTs,
          buckets: 1500,
        })
          .then((data) => {
            if (cancelled) return;
            setSeries(data);
            setFetchedCount(data.reduce((sum, bucket) => sum + bucket.n, 0));
            setLoading(false);
          })
          .catch(() => {
            if (cancelled) return;
            setSeries([]);
            setFetchedCount(0);
            setLoading(false);
          });
        return;
      }

      Promise.all(
        keys.map((key) =>
          fetchSensor(platform, deviceId, key, {
            limit: 1500,
            fromTs,
            toTs,
          }).catch(() => [] as SensorRecord[]),
        ),
      ).then((results) => {
        if (cancelled) return;
        const next: SensorData = {};
        let total = 0;
        keys.forEach((key, index) => {
          next[key] = results[index];
          total += results[index].length;
        });
        setRaw(next);
        setFetchedCount(total);
        setLoading(false);
      });
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [keys, platform, deviceId, config.key, useSeries, bounds]);

  // The plot cannot render a whole window at full resolution; downsample it.
  const plotData = useMemo<SensorData>(() => {
    const out: SensorData = {};
    for (const key of keys) out[key] = downsample(raw[key] ?? []);
    return out;
  }, [keys, raw]);

  const buttonClass = (active: boolean) =>
    `cursor-pointer rounded-[10px] px-3 py-1.5 text-[12px] font-semibold transition-colors ${
      active ? "bg-teal-soft text-teal" : "text-sage hover:text-ink"
    }`;

  // Every raw row in the selected window, at full resolution — the chart draws
  // ~1500 bucketed points of the same window, this downloads all of it.
  const csvHref = exportSensorHref(platform, deviceId, config.key, bounds);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/40 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="my-8 w-full max-w-4xl rounded-3xl border border-wire bg-card p-5 shadow-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ background: config.color }}
            />
            <div>
              <h2 className="text-[15px] font-bold text-ink">{config.label}</h2>
              <p className="text-[11px] text-sage">
                {totalCount.toLocaleString()} records total
                {!loading
                  ? ` · showing ${fetchedCount.toLocaleString()} in range`
                  : ""}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <ExportLink
              href={csvHref}
              label="Download CSV"
              title="Download every raw row in the selected range (CSV)"
              disabled={loading || fetchedCount === 0}
            />
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="cursor-pointer rounded-lg border border-wire bg-card-strong px-2.5 py-1 text-[13px] font-semibold text-sage transition-colors hover:border-teal hover:text-teal"
            >
              ✕
            </button>
          </div>
        </div>

        {useSeries ? (
          <SeriesChart config={config} buckets={series} loading={loading} />
        ) : (
          <SensorChart
            config={config}
            data={plotData}
            loading={loading}
            platform={platform}
          />
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.5px] text-sage">
            Time range
          </span>
          <div className="inline-flex flex-wrap gap-1 rounded-xl border border-wire bg-card-strong p-0.5">
            {RANGE_PRESETS.map((preset) => {
              const active = preset.key === range;
              return (
                <button
                  key={preset.key}
                  type="button"
                  onClick={() => setRange(preset.key)}
                  aria-pressed={active}
                  className={buttonClass(active)}
                >
                  {preset.label}
                </button>
              );
            })}
            <button
              type="button"
              onClick={enableCustom}
              aria-pressed={range === "custom"}
              className={buttonClass(range === "custom")}
            >
              Custom
            </button>
          </div>
          {loading ? (
            <span className="flex items-center gap-1.5 text-[11px] text-sage">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-teal" />
              Loading…
            </span>
          ) : null}
        </div>

        {range === "custom" ? (
          <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px] text-sage">
            <label className="flex items-center gap-1.5">
              From
              <input
                type="datetime-local"
                step="1"
                value={customFrom}
                max={customTo || undefined}
                onChange={(event) => setCustomFrom(event.target.value)}
                className="rounded-lg border border-wire bg-card-strong px-2 py-1 text-[12px] text-ink"
              />
            </label>
            <label className="flex items-center gap-1.5">
              To
              <input
                type="datetime-local"
                step="1"
                value={customTo}
                min={customFrom || undefined}
                onChange={(event) => setCustomTo(event.target.value)}
                className="rounded-lg border border-wire bg-card-strong px-2 py-1 text-[12px] text-ink"
              />
            </label>
          </div>
        ) : null}
      </div>
    </div>
  );
}
