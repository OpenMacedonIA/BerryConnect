import network
import time
from machine import Pin
import dht
import ujson
from umqtt.simple import MQTTClient

# --- CONFIGURATION ---
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASS = "YOUR_WIFI_PASSWORD"
BROKER_ADDRESS = "192.168.1.100"
CLIENT_ID = "tio_esp32_sensor_1"
TOPIC_TELEMETRY = b"tio/agents/esp32_1/telemetry"

# --- HARDWARE ---
# DHT22 connected to GPIO 15
sensor = dht.DHT22(Pin(15))

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('Connecting to network...')
        wlan.connect(WIFI_SSID, WIFI_PASS)
        while not wlan.isconnected():
            pass
    print('Network config:', wlan.ifconfig())

def connect_mqtt():
    client = MQTTClient(CLIENT_ID, BROKER_ADDRESS)
    client.connect()
    print('Connected to MQTT Broker')
    return client

def main():
    connect_wifi()
    
    try:
        client = connect_mqtt()
    except OSError as e:
        print('Failed to connect to MQTT broker. Reconnecting...')
        time.sleep(5)
        return

    while True:
        try:
            sensor.measure()
            temp = sensor.temperature()
            hum = sensor.humidity()
            
            payload = ujson.dumps({
                "device": CLIENT_ID,
                "temp": temp,
                "humidity": hum,
                "uptime": time.ticks_ms() // 1000
            })
            
            print("Publishing:", payload)
            client.publish(TOPIC_TELEMETRY, payload)
            
        except OSError as e:
            print('Failed to read sensor or publish.')
            
        time.sleep(10)

if __name__ == "__main__":
    main()
