import type { SensorConfig, SensorData } from "../config/sensors";
import SensorTimeSeriesCard from "./SensorTimeSeriesCard";
import NetworkTypeCard from "./NetworkTypeCard";
import ActivityCard from "./ActivityCard";
import ApplicationsCard from "./ApplicationsCard";
import WifiRecordsCard from "./WifiRecordsCard";
import LocationRecordsCard from "./LocationRecordsCard";
import CallsRecordsCard from "./CallsRecordsCard";
import TimezoneRecordsCard from "./TimezoneRecordsCard";
import AccelerometerRecordsCard from "./AccelerometerRecordsCard";
import BluetoothRecordsCard from "./BluetoothRecordsCard";
import GyroscopeRecordsCard from "./GyroscopeRecordsCard";
import LinearAccelerometerRecordsCard from "./LinearAccelerometerRecordsCard";
import ConversationRecordsCard from "./ConversationRecordsCard";
import DeviceUsageRecordsCard from "./DeviceUsageRecordsCard";
import ProcessorCard from "./ProcessorCard";
import BatteryEventsCard from "./BatteryEventsCard";
import AmbientNoiseCard from "./AmbientNoiseCard";

/**
 * Maps a sensor key to its card and renders it from the sensor's already-fetched
 * rows. This is the raw-record view for "plot" sensors that read from raw rows;
 * `SensorModal` chooses this over `SeriesChart` based on `sensorHasSeries`, and
 * picks between plot and logs based on `sensorViewType` (see `config/sensors.ts`).
 */
export default function SensorChart({
  config,
  data,
  loading,
  exportHref,
  platform,
}: {
  config: SensorConfig;
  data: SensorData;
  loading: boolean;
  exportHref?: string;
  platform: "android" | "ios";
}) {
  const rec = (key: string) => data[key] ?? [];
  const key = config.key;

  switch (key) {
    case "calls":
      return (
        <CallsRecordsCard records={rec(key)} loading={loading} exportHref={exportHref} />
      );
    case "accelerometer":
      return (
        <AccelerometerRecordsCard
          records={rec(key)}
          loading={loading}
          exportHref={exportHref}
        />
      );
    case "bluetooth":
      return (
        <BluetoothRecordsCard records={rec(key)} loading={loading} exportHref={exportHref} />
      );
    case "gyroscope":
      return (
        <GyroscopeRecordsCard records={rec(key)} loading={loading} exportHref={exportHref} />
      );
    case "linear-accelerometer":
      return (
        <LinearAccelerometerRecordsCard
          records={rec(key)}
          loading={loading}
          exportHref={exportHref}
        />
      );
    case "timezone":
      return (
        <TimezoneRecordsCard records={rec(key)} loading={loading} exportHref={exportHref} />
      );
    case "wifi":
      return (
        <WifiRecordsCard
          groups={[{ label: platform, records: rec(key) }]}
          loading={loading}
          exportHref={exportHref}
        />
      );
    case "processor":
      return (
        <ProcessorCard records={rec(key)} loading={loading} exportHref={exportHref} />
      );
    case "plugin-ambient-noise":
      return (
        <AmbientNoiseCard records={rec(key)} loading={loading} exportHref={exportHref} />
      );
    case "network":
      return (
        <NetworkTypeCard
          records={rec(key)}
          loading={loading}
          platform={platform}
          exportHref={exportHref}
        />
      );
    case "battery":
      return (
        <BatteryEventsCard
          batteryRecords={rec("battery")}
          batteryLoading={loading}
          batteryExportHref={exportHref}
          chargesRecords={rec("battery-charges")}
          dischargesRecords={rec("battery-discharges")}
          chargesLoading={loading}
          dischargesLoading={loading}
        />
      );
    case "applications":
      return (
        <ApplicationsCard
          foregroundRecords={rec("applications")}
          crashRecords={rec("applications-crashes")}
          historyRecords={rec("applications-history")}
          notificationRecords={rec("applications-notifications")}
          foregroundLoading={loading}
          crashLoading={loading}
          historyLoading={loading}
          notificationLoading={loading}
          exportHref={exportHref}
        />
      );
    case "studentlife-audio":
      return (
        <ConversationRecordsCard
          records={rec(key)}
          loading={loading}
          exportHref={exportHref}
        />
      );
    case "fused-location":
      return (
        <LocationRecordsCard
          title="Fused Location"
          color="#16a34a"
          records={rec(key)}
          loading={loading}
          exportHref={exportHref}
        />
      );
    case "locations":
      return (
        <LocationRecordsCard records={rec(key)} loading={loading} exportHref={exportHref} />
      );
    case "device-usage":
      return (
        <DeviceUsageRecordsCard
          records={rec(key)}
          loading={loading}
          exportHref={exportHref}
        />
      );
    case "activity":
      return (
        <ActivityCard records={rec(key)} loading={loading} exportHref={exportHref} />
      );
    default:
      return (
        <SensorTimeSeriesCard
          config={config}
          records={rec(key)}
          loading={loading}
          exportHref={exportHref}
        />
      );
  }
}
