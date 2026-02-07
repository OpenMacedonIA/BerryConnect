#!/usr/bin/env python3
"""
BerryConnect Agent - Enhanced Version
Satellite agent for WatermelonD with bidirectional communication
"""

import json
import os
import sys
import time
import socket
import logging
import subprocess
import datetime
from pathlib import Path

import psutil
import paho.mqtt.client as mqtt

# --- CONFIGURATION ---
def load_config():
    """Load configuration from config.json or environment variables"""
    config = {
        "broker_address": os.getenv("MQTT_BROKER_ADDRESS", "AUTO"),
        "broker_port": int(os.getenv("MQTT_BROKER_PORT", 1883)),
        "agent_id": os.getenv("AGENT_ID", "AUTO"),
        "telemetry_interval": int(os.getenv("TELEMETRY_INTERVAL", 10)),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
    }
    
    # Try to load from config.json
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            print(f"Warning: Could not load config.json: {e}")
    
    # Auto-discover broker if set to AUTO
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
    
    # Set agent ID
    if config["agent_id"] == "AUTO":
        config["agent_id"] = socket.gethostname()
    
    return config

# Initialize config and logging
CONFIG = load_config()

# Setup logging
logging.basicConfig(
    level=getattr(logging, CONFIG["log_level"]),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BerryAgent")

# Extract config values
BROKER_ADDRESS = CONFIG["broker_address"]
BROKER_PORT = CONFIG["broker_port"]
AGENT_ID = CONFIG["agent_id"]
TELEMETRY_INTERVAL = CONFIG["telemetry_interval"]
CLIENT_ID = f"berry_agent_{AGENT_ID}"

# MQTT Topics
TOPIC_TELEMETRY = f"tio/agents/{AGENT_ID}/telemetry"
TOPIC_ALERTS = f"tio/agents/{AGENT_ID}/alerts"
TOPIC_COMMANDS = f"tio/agents/{AGENT_ID}/commands"
TOPIC_RESPONSES = f"tio/agents/{AGENT_ID}/responses"

# --- TELEMETRY FUNCTIONS ---
def get_cpu_temp():
    """Get CPU temperature (Raspberry Pi specific)"""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read()) / 1000.0
    except:
        return None

def get_system_stats():
    """Collect comprehensive system telemetry"""
    stats = {
        # Basic stats
        "hostname": socket.gethostname(),
        "ip": socket.gethostbyname(socket.gethostname()),
        "timestamp": datetime.datetime.now().isoformat(),
        
        # CPU & RAM
        "cpu_percent": psutil.cpu_percent(interval=1),
        "ram_percent": psutil.virtual_memory().percent,
        "ram_total_mb": psutil.virtual_memory().total / (1024**2),
        "ram_used_mb": psutil.virtual_memory().used / (1024**2),
        
        # Temperature
        "cpu_temp": get_cpu_temp(),
        
        # Disk Usage
        "disk_total_gb": psutil.disk_usage('/').total / (1024**3),
        "disk_used_gb": psutil.disk_usage('/').used / (1024**3),
        "disk_percent": psutil.disk_usage('/').percent,
        
        # Network I/O
        "net_bytes_sent": psutil.net_io_counters().bytes_sent,
        "net_bytes_recv": psutil.net_io_counters().bytes_recv,
        "net_packets_sent": psutil.net_io_counters().packets_sent,
        "net_packets_recv": psutil.net_io_counters().packets_recv,
        
        # Uptime
        "uptime_seconds": time.time() - psutil.boot_time(),
        "boot_time": datetime.datetime.fromtimestamp(psutil.boot_time()).isoformat(),
    }
    
    # Battery (if available)
    battery = psutil.sensors_battery()
    if battery:
        stats.update({
            "battery_percent": battery.percent,
            "battery_plugged": battery.power_plugged,
            "battery_time_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else -1
        })
    
    return stats

# --- COMMAND HANDLERS ---
def handle_reboot(params):
    """Reboot the system"""
    logger.warning("Reboot command received!")
    subprocess.run(["sudo", "reboot"])
    return {"status": "rebooting"}

def handle_shutdown(params):
    """Shutdown the system"""
    logger.warning("Shutdown command received!")
    subprocess.run(["sudo", "shutdown", "-h", "now"])
    return {"status": "shutting_down"}

def handle_ping(params):
    """Respond to ping"""
    return {"status": "pong", "uptime": time.time() - psutil.boot_time()}

def handle_get_status(params):
    """Get immediate telemetry"""
    return {"status": "ok", "data": get_system_stats()}

def handle_restart_agent(params):
    """Restart the agent service"""
    logger.info("Restart agent command received")
    subprocess.run(["systemctl", "--user", "restart", "berry_agent"])
    return {"status": "restarting"}

def handle_update_config(params):
    """Update configuration dynamically"""
    global CONFIG, TELEMETRY_INTERVAL
    
    try:
        config_path = Path(__file__).parent / "config.json"
        
        # Update in-memory config
        if "telemetry_interval" in params:
            TELEMETRY_INTERVAL = int(params["telemetry_interval"])
            CONFIG["telemetry_interval"] = TELEMETRY_INTERVAL
        
        if "log_level" in params:
            new_level = params["log_level"].upper()
            logger.setLevel(getattr(logging, new_level))
            CONFIG["log_level"] = new_level
        
        # Save to file
        with open(config_path, 'w') as f:
            json.dump(CONFIG, f, indent=2)
        
        return {"status": "config_updated", "new_config": CONFIG}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Command dispatch table
COMMAND_HANDLERS = {
    "reboot": handle_reboot,
    "shutdown": handle_shutdown,
    "ping": handle_ping,
    "get_status": handle_get_status,
    "restart_agent": handle_restart_agent,
    "update_config": handle_update_config,
}

# --- MQTT CALLBACKS ---
def on_connect(client, userdata, flags, rc):
    """Called when connected to MQTT broker"""
    if rc == 0:
        logger.info(f"Connected to MQTT Broker at {BROKER_ADDRESS}")
        
        # Subscribe to commands topic
        client.subscribe(TOPIC_COMMANDS)
        logger.info(f"Subscribed to {TOPIC_COMMANDS}")
        
        # Publish online status
        client.publish(TOPIC_ALERTS, json.dumps({
            "status": "online",
            "msg": "Agent started",
            "timestamp": datetime.datetime.now().isoformat()
        }))
    else:
        logger.error(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    """Called when a message is received"""
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode())
        
        logger.info(f"Received command: {payload}")
        
        command = payload.get("command")
        params = payload.get("params", {})
        command_id = payload.get("id", "unknown")
        
        if command in COMMAND_HANDLERS:
            # Execute command
            response = COMMAND_HANDLERS[command](params)
            response["command"] = command
            response["command_id"] = command_id
            response["timestamp"] = datetime.datetime.now().isoformat()
            
            # Send response
            client.publish(TOPIC_RESPONSES, json.dumps(response))
            logger.info(f"Executed command '{command}': {response}")
        else:
            # Unknown command
            response = {
                "status": "error",
                "message": f"Unknown command: {command}",
                "command_id": command_id
            }
            client.publish(TOPIC_RESPONSES, json.dumps(response))
            logger.warning(f"Unknown command received: {command}")
            
    except Exception as e:
        logger.error(f"Error processing command: {e}")
        error_response = {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.datetime.now().isoformat()
        }
        client.publish(TOPIC_RESPONSES, json.dumps(error_response))

# --- MAIN LOOP ---
def main():
    """Main agent loop"""
    client = mqtt.Client(CLIENT_ID)
    client.on_connect = on_connect
    client.on_message = on_message

    logger.info(f"Connecting to {BROKER_ADDRESS}:{BROKER_PORT}...")
    try:
        client.connect(BROKER_ADDRESS, BROKER_PORT, 60)
        client.loop_start()
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return

    try:
        while True:
            # Collect and send telemetry
            stats = get_system_stats()
            payload = json.dumps(stats)
            
            logger.debug(f"Sending telemetry: {payload}")
            client.publish(TOPIC_TELEMETRY, payload)
            
            time.sleep(TELEMETRY_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("Stopping agent...")
        client.publish(TOPIC_ALERTS, json.dumps({
            "status": "offline",
            "msg": "Agent stopped",
            "timestamp": datetime.datetime.now().isoformat()
        }))
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
