"""Publishing to the study broker, which is the one thing this system does outward.

Everything else here reads. This sends, and the difference matters enough to keep in
one place: a prompt is an intervention on a participant rather than an observation of
one, so what leaves is recorded before anybody sees a success, and the rate limit is
asked first rather than trusted to the interface.

The broker is reached over the compose network on its plaintext listener. The port a
participant's phone uses is a different question, decided by the study's protocol,
and does not concern a publisher that never leaves the deployment.
"""

import os

import paho.mqtt.client as mqtt

HOST = os.getenv("MQTT_HOST", "aware_mqtt")
PORT = int(os.getenv("MQTT_PORT", "1883"))
USER = os.getenv("MQTT_PUBLISHER_USER", "aware_publisher")
PASSWORD = os.getenv("MQTT_PUBLISHER_PASSWORD", "")

#: Long enough for a broker on the same network, short enough that a request does
#: not hang on one that has stopped answering.
TIMEOUT_SECONDS = 5


class BrokerUnavailable(RuntimeError):
    """The broker could not be reached, so nothing was sent."""


def publish(topic: str, payload: str) -> None:
    """One message, at least once, or an exception naming why not.

    Synchronous on purpose. The caller records what was sent and answers a
    researcher with it, and both of those are lies if the publish is still in
    flight when they happen.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(USER, PASSWORD)
    try:
        client.connect(HOST, PORT, keepalive=TIMEOUT_SECONDS * 2)
        client.loop_start()
        info = client.publish(topic, payload, qos=1)
        info.wait_for_publish(timeout=TIMEOUT_SECONDS)
        if not info.is_published():
            raise BrokerUnavailable(f"{HOST}:{PORT} did not confirm the message")
    except BrokerUnavailable:
        raise
    except (OSError, ValueError) as error:
        raise BrokerUnavailable(f"{HOST}:{PORT} could not be reached: {error}") from error
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass
