import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchDevices } from "../api/client";
import { useLiveRefresh } from "../api/live";
import DeviceList from "../components/DeviceList";
import type { DevicesResponse } from "../types";

/**
 * The devices landing page: a full-width list of every phone. Selecting one
 * navigates to its own detail page rather than showing the detail alongside.
 */
export default function DevicesPage() {
  const navigate = useNavigate();
  const [devices, setDevices] = useState<DevicesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    fetchDevices()
      .then((d) => setDevices(d))
      .catch((e) => setError(String(e)));
  };

  // The list carries each phone's last upload, which any arrival moves.
  useLiveRefresh(load);

  if (error)
    return (
      <div className="mt-4 p-4 text-red-700 bg-red-50 border border-red-200 rounded-2xl">
        {error}
      </div>
    );

  return (
    <DeviceList
      devices={devices}
      selected={null}
      onSelect={(device) =>
        navigate(
          `/devices/${device.platform}/${encodeURIComponent(device.device_id)}`,
        )
      }
    />
  );
}
