from sqlalchemy import BigInteger, Column, Double, Integer, JSON, String, Text
from app.database import AndroidBase, IosBase


# ---------------------------------------------------------------------------
# Android models — each table has its own explicit columns
# ---------------------------------------------------------------------------

class AndroidDevice(AndroidBase):
  __tablename__ = "aware_device"
  _id = Column(BigInteger, primary_key=True, autoincrement=True)
  timestamp = Column(Double, default=0)
  device_id = Column(String(150), default="")
  board = Column(Text)
  brand = Column(Text)
  device = Column(Text)
  manufacturer = Column(Text)
  model = Column(Text)
  sdk = Column(Text)
  label = Column(Text)


class AndroidAccelerometer(AndroidBase):
  __tablename__ = "accelerometer"
  _id = Column(BigInteger, primary_key=True, autoincrement=True)
  timestamp = Column(Double, default=0)
  device_id = Column(String(150), default="")
  double_values_0 = Column(Double, default=0)
  double_values_1 = Column(Double, default=0)
  double_values_2 = Column(Double, default=0)
  accuracy = Column(Integer, default=0)
  label = Column(Text)


class AndroidBattery(AndroidBase):
  __tablename__ = "battery"
  _id = Column(BigInteger, primary_key=True, autoincrement=True)
  timestamp = Column(Double, default=0)
  device_id = Column(String(150), default="")
  battery_status = Column(Integer, default=0)
  battery_level = Column(Integer, default=0)
  battery_scale = Column(Integer, default=0)
  battery_voltage = Column(Integer, default=0)
  battery_temperature = Column(Integer, default=0)
  battery_adaptor = Column(Integer, default=0)
  battery_health = Column(Integer, default=0)
  battery_technology = Column(Text)


class AndroidScreen(AndroidBase):
  __tablename__ = "screen"
  _id = Column(BigInteger, primary_key=True, autoincrement=True)
  timestamp = Column(Double, default=0)
  device_id = Column(String(150), default="")
  screen_status = Column(Integer, default=0)


class AndroidLocations(AndroidBase):
  __tablename__ = "locations"
  _id = Column(BigInteger, primary_key=True, autoincrement=True)
  timestamp = Column(Double, default=0)
  device_id = Column(String(150), default="")
  double_latitude = Column(Double, default=0)
  double_longitude = Column(Double, default=0)
  double_bearing = Column(Double, default=0)
  double_speed = Column(Double, default=0)
  double_altitude = Column(Double, default=0)
  provider = Column(Text)
  accuracy = Column(Double, default=0)
  label = Column(Text)


class AndroidWifi(AndroidBase):
  __tablename__ = "wifi"
  _id = Column(BigInteger, primary_key=True, autoincrement=True)
  timestamp = Column(Double, default=0)
  device_id = Column(String(150), default="")
  bssid = Column(String(255), default="")
  ssid = Column(Text)
  security = Column(Text)
  frequency = Column(Integer, default=0)
  rssi = Column(Integer, default=0)
  label = Column(Text)


class AndroidBluetooth(AndroidBase):
  __tablename__ = "bluetooth"
  _id = Column(BigInteger, primary_key=True, autoincrement=True)
  timestamp = Column(Double, default=0)
  device_id = Column(String(150), default="")
  bt_address = Column(String(150), default="")
  bt_name = Column(Text)
  bt_rssi = Column(Integer, default=0)
  label = Column(Text)


class AndroidNetwork(AndroidBase):
  __tablename__ = "network"
  _id = Column(BigInteger, primary_key=True, autoincrement=True)
  timestamp = Column(Double, default=0)
  device_id = Column(String(150), default="")
  network_type = Column(Integer, default=0)
  network_subtype = Column(Text)
  network_state = Column(Integer, default=0)


class AndroidCalls(AndroidBase):
  __tablename__ = "calls"
  _id = Column(BigInteger, primary_key=True, autoincrement=True)
  timestamp = Column(Double, default=0)
  device_id = Column(String(150), default="")
  call_type = Column(Integer, default=0)
  call_duration = Column(Integer, default=0)
  trace = Column(Text)


class AndroidGyroscope(AndroidBase):
  __tablename__ = "gyroscope"
  _id = Column(BigInteger, primary_key=True, autoincrement=True)
  timestamp = Column(Double, default=0)
  device_id = Column(String(150), default="")
  double_values_0 = Column(Double, default=0)
  double_values_1 = Column(Double, default=0)
  double_values_2 = Column(Double, default=0)
  accuracy = Column(Integer, default=0)
  label = Column(Text)


class AndroidLight(AndroidBase):
  __tablename__ = "light"
  _id = Column(BigInteger, primary_key=True, autoincrement=True)
  timestamp = Column(Double, default=0)
  device_id = Column(String(150), default="")
  double_values_0 = Column(Double, default=0)
  accuracy = Column(Integer, default=0)
  label = Column(Text)


class AndroidApplicationsForeground(AndroidBase):
  __tablename__ = "applications_foreground"
  _id = Column(BigInteger, primary_key=True, autoincrement=True)
  timestamp = Column(Double, default=0)
  device_id = Column(String(150), default="")
  package_name = Column(Text)
  application_name = Column(Text)
  is_system_app = Column(Integer, default=0)


# ---------------------------------------------------------------------------
# iOS models — all tables share (_id, timestamp, device_id, data JSON).
# A factory avoids repeating the same 4 columns for every table.
# ---------------------------------------------------------------------------

def _ios_model(table_name: str):
  return type(
    f"Ios{table_name.replace('_', ' ').title().replace(' ', '')}",
    (IosBase,),
    {
      "__tablename__": table_name,
      "_id": Column(Integer, primary_key=True, autoincrement=True),
      "timestamp": Column(Double, nullable=False),
      "device_id": Column(String(128), nullable=False),
      "data": Column(JSON, nullable=False),
    },
  )


IosAccelerometer              = _ios_model("accelerometer")
IosBarometer                  = _ios_model("barometer")
IosBattery                    = _ios_model("battery")
IosBluetooth                  = _ios_model("bluetooth")
IosCalls                      = _ios_model("calls")
IosGyroscope                  = _ios_model("gyroscope")
IosLight                      = _ios_model("light")
IosLocations                  = _ios_model("locations")
IosLocationGps                = _ios_model("location_gps")
IosMagnetometer               = _ios_model("magnetometer")
IosNetwork                    = _ios_model("network")
IosProximity                  = _ios_model("proximity")
IosRotation                   = _ios_model("rotation")
IosScreen                     = _ios_model("screen")
IosTelephony                  = _ios_model("telephony")
IosTemperature                = _ios_model("temperature")
IosTimezone                   = _ios_model("timezone")
IosWifi                       = _ios_model("wifi")
IosDevice                     = _ios_model("aware_device")
IosApplications               = _ios_model("applications")
IosApplicationsHistory        = _ios_model("applications_history")
IosHealthKit                  = _ios_model("health_kit")
IosHealthKitQuantity          = _ios_model("health_kit_quantity")
IosPluginAmbientNoise         = _ios_model("plugin_ambient_noise")
IosPluginActivityRecognition  = _ios_model("plugin_ios_activity_recognition")
IosPedometer                  = _ios_model("plugin_ios_pedometer")
