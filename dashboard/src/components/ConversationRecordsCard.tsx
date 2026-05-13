import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SensorRecord } from "../types";
import { fmt } from "../utils/stats";
import ExportLink from "./ExportLink";

interface Props {
  records: SensorRecord[];
  loading: boolean;
  exportHref?: string;
}

interface InferencePoint {
  time: number;
  energy: number;
  inference: number;
  label: string;
}

interface ConversationEvent {
  time: number;
  start: number | null;
  end: number | null;
  durationMs: number | null;
}

const INFERENCE_LABELS: Record<number, string> = {
  0: "Silence",
  1: "Voice",
  2: "Noise",
  3: "Unknown",
};

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function normalizeTimestamp(value: number | null): number | null {
  if (value == null || value <= 0) return null;
  return value < 100_000_000_000 ? value * 1000 : value;
}

function makeTickFormatter(spanMs: number) {
  const multiDay = spanMs > 24 * 60 * 60 * 1000;
  return (ts: number) => {
    const date = new Date(ts);
    if (multiDay) {
      return (
        date.toLocaleDateString([], { month: "short", day: "numeric" }) +
        " " +
        date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      );
    }
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };
}

function formatDuration(durationMs: number | null): string {
  if (durationMs == null) return "-";
  const seconds = durationMs / 1000;
  if (seconds < 60) return `${fmt(seconds, 1)} s`;
  return `${fmt(seconds / 60, 1)} min`;
}

function buildInferenceData(records: SensorRecord[]): InferencePoint[] {
  return records
    .map((record): InferencePoint | null => {
      const datatype = numberValue(record.datatype);
      const inference = numberValue(record.inference);
      if (datatype !== 0 || inference == null || inference < 0) return null;
      return {
        time: record.timestamp,
        energy: numberValue(record.double_energy) ?? 0,
        inference,
        label: INFERENCE_LABELS[inference] ?? `Code ${inference}`,
      };
    })
    .filter((point): point is InferencePoint => point != null)
    .sort((a, b) => a.time - b.time);
}

function buildConversationEvents(records: SensorRecord[]): ConversationEvent[] {
  return records
    .map((record): ConversationEvent | null => {
      const datatype = numberValue(record.datatype);
      if (datatype !== 2) return null;
      const start = normalizeTimestamp(numberValue(record.double_convo_start));
      const end = normalizeTimestamp(numberValue(record.double_convo_end));
      return {
        time: record.timestamp,
        start,
        end,
        durationMs: start != null && end != null && end >= start ? end - start : null,
      };
    })
    .filter((event): event is ConversationEvent => event != null)
    .sort((a, b) => a.time - b.time);
}

function countByInference(points: InferencePoint[]) {
  return points.reduce<Record<number, number>>((counts, point) => {
    counts[point.inference] = (counts[point.inference] ?? 0) + 1;
    return counts;
  }, {});
}

export default function ConversationRecordsCard({
  records,
  loading,
  exportHref,
}: Props) {
  const inferenceData = buildInferenceData(records);
  const conversationEvents = buildConversationEvents(records);
  const featureRows = records.filter((record) => numberValue(record.datatype) === 1).length;
  const latestInference = inferenceData.length
    ? inferenceData[inferenceData.length - 1]
    : null;
  const inferenceCounts = countByInference(inferenceData);
  const durations = conversationEvents
    .map((event) => event.durationMs)
    .filter((duration): duration is number => duration != null);
  const totalDurationMs = durations.reduce((sum, duration) => sum + duration, 0);
  const averageDurationMs = durations.length ? totalDurationMs / durations.length : null;
  const recentEvents = conversationEvents.slice(-3).reverse();
  const spanMs =
    inferenceData.length > 1
      ? inferenceData[inferenceData.length - 1].time - inferenceData[0].time
      : 0;
  const tickFormatter = makeTickFormatter(spanMs);

  return (
    <div className="bg-card backdrop-blur-xl border border-wire rounded-3xl shadow-card p-5">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2 h-2 rounded-full shrink-0 bg-[#7c3aed]" />
        <h3 className="text-[13px] font-semibold flex-1 text-ink">
          Conversation
        </h3>
        <span className="text-[11px] text-sage bg-[rgba(48,67,54,0.07)] px-1.5 py-0.5 rounded-md">
          metadata
        </span>
        {exportHref && <ExportLink href={exportHref} />}
      </div>

      {records.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-3 text-[11px] text-sage">
          <span>
            <b className="text-ink">{records.length.toLocaleString()}</b> records
          </span>
          <span>
            samples <b className="text-ink">{inferenceData.length.toLocaleString()}</b>
          </span>
          <span>
            events <b className="text-ink">{conversationEvents.length.toLocaleString()}</b>
          </span>
          {latestInference && (
            <>
              <span>
                latest <b className="text-ink">{latestInference.label}</b>
              </span>
              <span>
                energy <b className="text-ink">{fmt(latestInference.energy, 3)}</b>
              </span>
            </>
          )}
        </div>
      )}

      <div className="mb-3 rounded-lg border border-wire bg-card-strong/70 px-3 py-2 text-[11px] leading-snug text-sage">
        StudentLife audio classifies ambient microphone input into Silence,
        Voice, Noise, or Unknown and stores derived metadata only. Raw audio is
        not uploaded. The sensor needs microphone permission. Rows with
        datatype 0 are audio classification samples; datatype 2 rows are
        conversation start/end events; datatype 1 feature rows are effectively
        unused in this implementation.
      </div>

      {loading ? (
        <div className="h-44 rounded-xl shimmer" />
      ) : !records.length ? (
        <div className="h-44 flex items-center justify-center text-sage text-[13px]">
          No data
        </div>
      ) : (
        <div className="space-y-3">
          {inferenceData.length ? (
            <ResponsiveContainer width="100%" height={190}>
              <LineChart
                data={inferenceData}
                margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(48,67,54,0.12)" />
                <XAxis
                  dataKey="time"
                  tickFormatter={tickFormatter}
                  tick={{ fill: "#5f746b", fontSize: 11 }}
                  minTickGap={60}
                />
                <YAxis
                  yAxisId="classification"
                  tick={{ fill: "#5f746b", fontSize: 10 }}
                  width={76}
                  ticks={[0, 1, 2, 3]}
                  domain={[0, 3]}
                  tickFormatter={(value) =>
                    INFERENCE_LABELS[Number(value)] ?? String(value)
                  }
                />
                <YAxis
                  yAxisId="energy"
                  orientation="right"
                  tick={{ fill: "#5f746b", fontSize: 10 }}
                  width={42}
                  tickFormatter={(value) => fmt(Number(value), 1)}
                />
                <Tooltip
                  labelFormatter={(value) => new Date(value as number).toLocaleString()}
                  formatter={(value: unknown, name: unknown) =>
                    name === "inference"
                      ? [
                          INFERENCE_LABELS[Number(value)] ?? String(value),
                          "Classification",
                        ]
                      : [`${fmt(Number(value), 3)}`, "Energy"]
                  }
                  contentStyle={{
                    background: "#fffdf8",
                    border: "1px solid rgba(48,67,54,0.14)",
                    borderRadius: 10,
                  }}
                  labelStyle={{ color: "#5f746b" }}
                  itemStyle={{ color: "#193229" }}
                />
                <Line
                  yAxisId="classification"
                  type="stepAfter"
                  dataKey="inference"
                  stroke="#7c3aed"
                  dot={false}
                  strokeWidth={2}
                />
                <Line
                  yAxisId="energy"
                  type="monotone"
                  dataKey="energy"
                  stroke="#f97316"
                  dot={false}
                  strokeWidth={1.8}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-40 flex items-center justify-center rounded-xl border border-wire bg-card-strong/60 text-sage text-[13px]">
              No audio classification samples
            </div>
          )}

          <div className="grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-2">
            <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
              <div className="text-[10px] uppercase tracking-[0.5px] text-sage">
                Voice samples
              </div>
              <div className="mt-1 text-[18px] font-semibold text-ink">
                {(inferenceCounts[1] ?? 0).toLocaleString()}
              </div>
            </div>
            <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
              <div className="text-[10px] uppercase tracking-[0.5px] text-sage">
                Conversation events
              </div>
              <div className="mt-1 text-[18px] font-semibold text-ink">
                {conversationEvents.length.toLocaleString()}
              </div>
            </div>
            <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
              <div className="text-[10px] uppercase tracking-[0.5px] text-sage">
                Total duration
              </div>
              <div className="mt-1 text-[18px] font-semibold text-ink">
                {formatDuration(totalDurationMs || null)}
              </div>
            </div>
            <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
              <div className="text-[10px] uppercase tracking-[0.5px] text-sage">
                Avg event
              </div>
              <div className="mt-1 text-[18px] font-semibold text-ink">
                {formatDuration(averageDurationMs)}
              </div>
            </div>
          </div>

          {recentEvents.length > 0 && (
            <div className="rounded-xl border border-wire bg-card-strong/70 px-3 py-2">
              <div className="text-[10px] uppercase tracking-[0.5px] text-sage mb-2">
                Recent conversation events
              </div>
              <div className="space-y-1.5 text-[11px] text-sage">
                {recentEvents.map((event) => (
                  <div
                    key={`${event.time}-${event.start ?? "start"}-${event.end ?? "end"}`}
                    className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1"
                  >
                    <span className="text-ink font-medium">
                      {event.start
                        ? new Date(event.start).toLocaleString()
                        : new Date(event.time).toLocaleString()}
                    </span>
                    <span>{formatDuration(event.durationMs)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {featureRows > 0 && (
            <div className="rounded-lg border border-wire bg-card-strong/70 px-3 py-2 text-[11px] leading-snug text-sage">
              {featureRows.toLocaleString()} datatype 1 feature rows are present.
              Feature payload saving is not expected in the current iOS
              implementation, so inspect blob_feature only if the app was
              modified.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
