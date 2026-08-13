import type { Device } from "../types";

/** A human-readable name for a phone, falling back to a shortened device id. */
export function deviceLabel(device: Device): string {
  if (device.platform === "android") {
    const name = [device.manufacturer, device.model].filter(Boolean).join(" ");
    return name || device.device_id.slice(0, 12);
  }

  // An iPhone reports "iPhone" for its model, product and device, and its exact
  // identity only in `hardware` ("iPhone16,1"). Two phones in a study are told
  // apart by that, so it leads when it says more than the model does.
  const identity =
    device.hardware && device.hardware !== device.model
      ? device.hardware
      : device.label || device.device || device.model || device.product;

  return identity || device.device_id.slice(0, 16);
}

/** The operating system the phone runs, as that platform reports it.
 *
 * Android puts its version in `release` and its API level in `sdk`; an iPhone
 * puts the iOS version in `sdk` and its Darwin kernel in `release`. Reading the
 * same field for both would label an iPhone with a kernel version.
 */
export function deviceOsVersion(device: Device): string | null {
  if (device.platform === "android") {
    return device.release ? `Android ${device.release}` : null;
  }
  return device.sdk ? `iOS ${device.sdk}` : null;
}
