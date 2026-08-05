import type { Device } from "../types";

/** A human-readable name for a phone, falling back to a shortened device id. */
export function deviceLabel(device: Device): string {
  if (device.platform === "android") {
    const name = [device.manufacturer, device.model].filter(Boolean).join(" ");
    return name || device.device_id.slice(0, 12);
  }

  return (
    device.label ||
    device.device ||
    device.model ||
    device.product ||
    device.device_id.slice(0, 16)
  );
}
