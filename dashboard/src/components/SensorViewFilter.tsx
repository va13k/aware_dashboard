import type { SensorView } from "../utils/sensorView";

const OPTIONS: { value: SensorView; label: string }[] = [
  { value: "all", label: "All sensors" },
  { value: "records", label: "With records" },
  { value: "required", label: "Required by config" },
];

export default function SensorViewFilter({
  value,
  onChange,
}: {
  value: SensorView;
  onChange: (view: SensorView) => void;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Sensor view"
      className="inline-flex self-start rounded-xl border border-wire bg-card p-0.5 text-[13px] font-semibold shadow-card sm:self-auto"
    >
      {OPTIONS.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={`cursor-pointer rounded-[10px] px-3 py-1.5 transition-colors ${
              active ? "bg-teal-soft text-teal" : "text-sage hover:text-ink"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
