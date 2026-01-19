import network
import time
import json
import ubinascii
import machine
from umqtt.simple import MQTTClient
import bluetooth
from machine import Timer

# --- CONFIGURATION ---
SSID = "CHANGE_ME"
PASSWORD = "CHANGE_ME"
BRAIN_IP = "192.168.1.100" # IP of NeoCore
HOSTNAME = "mnb-device-01"
MQTT_PORT = 1883

# --- GLOBAL VARS ---
wlan = network.WLAN(network.STA_IF)
mqtt_client = None
bt_sock = None
using_bluetooth = False

# --- BLUETOOTH SETUP (Simplified RFCOMM Serial) ---
# Note: Full RFCOMM implementation in MicroPython can be complex.
# This is a placeholder for the logic structure.
# Actual implementation requires a BLE wrapper or specific ESP32 BT Serial lib.

def connect_wifi():
    global wlan
    wlan.active(True)
    if not wlan.isconnected():
        print('Connecting to network...')
        wlan.connect(SSID, PASSWORD)
        for _ in range(20): # Wait 10s
            if wlan.isconnected(): break
            time.sleep(0.5)
            
    if wlan.isconnected():
        print('WiFi Config:', wlan.ifconfig())
        return True
    return False

def connect_mqtt():
    global mqtt_client
    try:
        client = MQTTClient(HOSTNAME, BRAIN_IP, port=MQTT_PORT)
        client.set_last_will(f"tio/agents/{HOSTNAME}/status", "offline", retain=True)
        client.connect()
        client.publish(f"tio/agents/{HOSTNAME}/status", "online", retain=True)
        print("Connected to MQTT")
        return client
    except Exception as e:
        print(f"MQTT Error: {e}")
        return None

def send_telemetry(data):
    msg = json.dumps(data)
    if not using_bluetooth and mqtt_client:
        try:
            mqtt_client.publish(f"tio/agents/{HOSTNAME}/telemetry", msg)
        except:
            print("MQTT Publish Failed")
    elif using_bluetooth:
        # Send via BT Serial
        print(f"BT Send: {msg}")
        # bt_sock.send(msg + "\n") 
        pass

def main():
    global mqtt_client, using_bluetooth
    
    # 1. Try WiFi
    if connect_wifi():
        mqtt_client = connect_mqtt()
        if not mqtt_client:
            print("WiFi OK but MQTT Failed. Continuing...")
    else:
        print("WiFi Failed. Activating Bluetooth Fallback...")
        using_bluetooth = True
        # activate_bluetooth_stack()

    # 2. Main Loop
    counter = 0
    while True:
        try:
            # Simulated Sensor Data
            data = {"temp": 25 + (counter % 5), "uptime": counter}
            send_telemetry(data)
            
            if mqtt_client:
                mqtt_client.check_msg()
                
            counter += 1
            time.sleep(5)
            
        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(5)
            # Try reconnect logic here

if __name__ == "__main__":
    main()
