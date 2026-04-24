from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Base(BaseModel):
  model_config = ConfigDict(from_attributes=True, populate_by_name=True)

  id: int = Field(validation_alias="_id")
  timestamp: float
  device_id: str


# ---------------------------------------------------------------------------
# Android schemas — flat columns, no JSON blob to resolve
# ---------------------------------------------------------------------------

class AndroidDeviceSchema(_Base):
  board: str | None = None
  brand: str | None = None
  device: str | None = None
  manufacturer: str | None = None
  model: str | None = None
  sdk: str | None = None
  label: str | None = None


class AndroidAccelerometerSchema(_Base):
  double_values_0: float = 0
  double_values_1: float = 0
  double_values_2: float = 0
  accuracy: int = 0
  label: str | None = None


class AndroidBatterySchema(_Base):
  battery_status: int = 0
  battery_level: int = 0
  battery_scale: int = 0
  battery_voltage: int = 0
  battery_temperature: int = 0
  battery_adaptor: int = 0
  battery_health: int = 0
  battery_technology: str | None = None


class AndroidScreenSchema(_Base):
  screen_status: int = 0


class AndroidLocationsSchema(_Base):
  double_latitude: float = 0
  double_longitude: float = 0
  double_bearing: float = 0
  double_speed: float = 0
  double_altitude: float = 0
  provider: str | None = None
  accuracy: float = 0
  label: str | None = None


class AndroidWifiSchema(_Base):
  bssid: str = ""
  ssid: str | None = None
  security: str | None = None
  frequency: int = 0
  rssi: int = 0
  label: str | None = None


class AndroidBluetoothSchema(_Base):
  bt_address: str = ""
  bt_name: str | None = None
  bt_rssi: int = 0
  label: str | None = None


class AndroidNetworkSchema(_Base):
  network_type: int = 0
  network_subtype: str | None = None
  network_state: int = 0


class AndroidCallsSchema(_Base):
  call_type: int = 0
  call_duration: int = 0
  trace: str | None = None


class AndroidGyroscopeSchema(_Base):
  double_values_0: float = 0
  double_values_1: float = 0
  double_values_2: float = 0
  accuracy: int = 0
  label: str | None = None


class AndroidLightSchema(_Base):
  double_values_0: float = 0
  accuracy: int = 0
  label: str | None = None


class AndroidApplicationsForegroundSchema(_Base):
  package_name: str | None = None
  application_name: str | None = None
  is_system_app: int = 0


# ---------------------------------------------------------------------------
# iOS schemas — data is a JSON blob; flatten it into the response.
# extra="allow" surfaces every key from the blob even if not explicitly typed.
# ---------------------------------------------------------------------------

class IosSchema(_Base):
  model_config = ConfigDict(
    from_attributes=True,
    populate_by_name=True,
    extra="allow",
  )

  @model_validator(mode="before")
  @classmethod
  def flatten_data(cls, v: Any) -> Any:
    if isinstance(v, dict):
      data = v.pop("data", None) or {}
      v.update(data)
      return v
    # ORM object
    data = getattr(v, "data", None) or {}
    return {
      "_id": getattr(v, "_id", None),
      "timestamp": getattr(v, "timestamp", None),
      "device_id": getattr(v, "device_id", None),
      **data,
    }
