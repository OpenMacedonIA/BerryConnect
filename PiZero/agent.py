import time
import json
import socket
import psutil
import paho.mqtt.client as mqtt
import os

# --- CONFIGURATION ---
BROKER_ADDRESS = "192.168.1.100" # IP of the main TIO server (Mosquitto)
BROKER_PORT = 1883
CLIENT_ID = f"tio_agent_{socket.gethostname()}"
TOPIC_TELEMETRY = f"tio/agents/{socket.gethostname()}/telemetry"
TOPIC_ALERTS = f"tio/agents/{socket.gethostname()}/alerts"

# --- SENSORS ---
def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read()) / 1000.0
    except:
        return 0.0

def get_system_stats():
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "ram_percent": psutil.virtual_memory().percent,
        "cpu_temp": get_cpu_temp(),
        "hostname": socket.gethostname(),
        "ip": socket.gethostbyname(socket.gethostname())
    }

# --- MQTT CALLBACKS ---
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected to MQTT Broker at {BROKER_ADDRESS}")
        client.publish(TOPIC_ALERTS, json.dumps({"status": "online", "msg": "Agent started"}))
    else:
        print(f"Failed to connect, return code {rc}")

# --- MAIN LOOP ---
def main():
    client = mqtt.Client(CLIENT_ID)
    client.on_connect = on_connect

    print(f"Connecting to {BROKER_ADDRESS}...")
    try:
        client.connect(BROKER_ADDRESS, BROKER_PORT, 60)
        client.loop_start()
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    try:
        while True:
            stats = get_system_stats()
            payload = json.dumps(stats)
            
            print(f"Sending telemetry: {payload}")
            client.publish(TOPIC_TELEMETRY, payload)
            
            # Simple Intruder Alert Simulation (e.g., if a specific device is found on network)
            # Here we just simulate a check
            # if check_intruder():
            #     client.publish(TOPIC_ALERTS, json.dumps({"alert": "intruder_detected"}))

            time.sleep(10) # Send every 10 seconds
            
    except KeyboardInterrupt:
        print("Stopping agent...")
        client.publish(TOPIC_ALERTS, json.dumps({"status": "offline", "msg": "Agent stopped"}))
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
