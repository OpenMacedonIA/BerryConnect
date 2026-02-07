import time
import json
import socket
import psutil
import paho.mqtt.client as mqtt
import os
import sys
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BerryConnect-Agent")

# --- CONFIGURATION LOADING ---
def load_config():
    """Load configuration from config.json or use defaults"""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    
    # Default configuration
    config = {
        "broker_address": os.environ.get("MQTT_BROKER", "192.168.1.100"),
        "broker_port": int(os.environ.get("MQTT_PORT", "1883")),
        "agent_id": socket.gethostname(),
        "telemetry_interval": 10,
        "log_level": "INFO"
    }
    
    # Try to load from file
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
            logger.info(f"Configuration loaded from {config_path}")
        except Exception as e:
            logger.warning(f"Could not load config file: {e}. Using defaults.")
    else:
        logger.warning(f"Config file not found: {config_path}. Using defaults.")
    
    # Handle AUTO settings
    if config["broker_address"] == "AUTO":
        logger.info("AUTO broker discovery requested...")
        try:
            from broker_discovery import discover_broker
            host, port = discover_broker(config["broker_port"], verbose=False)
            if host:
                config["broker_address"] = host
                config["broker_port"] = port
                logger.info(f"Auto-discovered broker: {host}:{port}")
            else:
                logger.error("Could not auto-discover broker. Please configure manually.")
                sys.exit(1)
        except ImportError:
            logger.error("broker_discovery module not found. Cannot auto-discover.")
            sys.exit(1)
    
    if config["agent_id"] == "AUTO":
        config["agent_id"] = socket.gethostname()
    
    # Set log level
    if config["log_level"] in ["DEBUG", "INFO", "WARNING", "ERROR"]:
        logging.getLogger().setLevel(getattr(logging, config["log_level"]))
    
    return config

# Load configuration
config = load_config()
BROKER_ADDRESS = config["broker_address"]
BROKER_PORT = config["broker_port"]
CLIENT_ID = f"tio_agent_{config['agent_id']}"
TOPIC_TELEMETRY = f"tio/agents/{config['agent_id']}/telemetry"
TOPIC_ALERTS = f"tio/agents/{config['agent_id']}/alerts"
TELEMETRY_INTERVAL = config["telemetry_interval"]

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
        logger.info(f"Connected to MQTT Broker at {BROKER_ADDRESS}")
        client.publish(TOPIC_ALERTS, json.dumps({"status": "online", "msg": "Agent started"}))
    else:
        logger.error(f"Failed to connect, return code {rc}")

# --- MAIN LOOP ---
def main():
    client = mqtt.Client(CLIENT_ID)
    client.on_connect = on_connect

    logger.info(f"Connecting to {BROKER_ADDRESS}...")
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
            
            logger.debug(f"Sending telemetry: {payload}")
            client.publish(TOPIC_TELEMETRY, payload)
            
            # Simple Intruder Alert Simulation (e.g., if a specific device is found on network)
            # Here we just simulate a check
            # if check_intruder():
            #     client.publish(TOPIC_ALERTS, json.dumps({"alert": "intruder_detected"}))

            time.sleep(TELEMETRY_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("Stopping agent...")
        client.publish(TOPIC_ALERTS, json.dumps({"status": "offline", "msg": "Agent stopped"}))
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
