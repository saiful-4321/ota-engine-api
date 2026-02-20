import paho.mqtt.client as mqtt
from typing import Callable
import uuid
from config import MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE, APP_ENV_MQTT, MQTT_USER, MQTT_PASS
from app.helpers.common import write_log
import time

class MqttService:
    def __init__(self, broker: str = MQTT_HOST, port: int = int(MQTT_PORT), client_id: str = None):
        self.broker = broker
        self.port = port
        self.client_id = client_id or f"global_mqtt_{APP_ENV_MQTT}_{str(uuid.uuid4())}"
        self.client = mqtt.Client(self.client_id)
        
        # Set username and password for the MQTT broker
        self.client.username_pw_set(MQTT_USER, MQTT_PASS)
        
        # Set default callbacks (can be overridden)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

        # Retry parameters
        self.retry_delay = 1  # Initial retry delay in seconds
        self.max_retry_delay = 1  # Maximum retry delay in seconds

        # Attempt to connect when the MQTT service is initialized
        self.connect()

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"Connected to MQTT broker: {self.broker}:{self.port}")
            write_log(f"Connected to MQTT broker: {self.broker}:{self.port}", 'oms-api-mqtt', 'info')
        else:
            print(f"Connection to MQTT broker failed with code {rc}")
            write_log(f"Connection to MQTT broker failed with code {rc}", 'oms-api-mqtt')

    def on_disconnect(self, client, userdata, rc):
        print("Disconnected from MQTT broker")
        write_log("Disconnected from MQTT broker", 'oms-api-mqtt')
        # Attempt to reconnect
        self.reconnect()

    def on_message(self, client, userdata, msg):
        print(f"Received message on topic {msg.topic}: {msg.payload}")

    def connect(self):
        # Set the keepalive interval (in seconds)
        keepalive_interval = int(MQTT_KEEPALIVE)
        self.client.connect(self.broker, self.port, keepalive=keepalive_interval)
        self.client.loop_start()  # Start a background thread to handle MQTT communication

    def disconnect(self):
        self.client.loop_stop()  # Stop the background thread
        self.client.disconnect()

    def reconnect(self):
        while not self.client.is_connected():
            print(f"Attempting to reconnect to MQTT broker in {self.retry_delay} seconds...")
            write_log(f"Attempting to reconnect to MQTT broker in {self.retry_delay} seconds...", 'oms-api-mqtt')
            time.sleep(self.retry_delay)
            try:
                self.connect()
                self.retry_delay = 2
            except Exception as e:
                print(f"Reconnection failed: {str(e)}")
                write_log(f"Reconnection failed: {str(e)}", 'oms-api-mqtt')
                # Increase retry delay exponentially, but cap it at max_retry_delay
                self.retry_delay = min(2 * self.retry_delay, self.max_retry_delay)

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False):
        self.client.publish(topic, payload, qos=qos, retain=retain)

    def subscribe(self, topic: str, callback: Callable):
        self.client.subscribe(topic)
        self.client.message_callback_add(topic, callback)

# Create a single instance of MqttService
mqtt_service = MqttService()
