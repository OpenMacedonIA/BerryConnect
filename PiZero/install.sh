#!/bin/bash
# BerryConnect Agent Installer
# Automated installation for Raspberry Pi satellite agents

set -e

echo "========================================="
echo "=== BerryConnect Agent Installer     ==="
echo "========================================="
echo ""

# Check if we're on a Debian-based system
if ! command -v apt-get &> /dev/null; then
    echo "ERROR: This installer is designed for Debian-based systems (Raspberry Pi OS)"
    echo "Please install dependencies manually and configure config.json"
    exit 1
fi

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required but not installed"
    exit 1
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "[STEP 1/6] Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-pip avahi-utils bluez libbluetooth-dev

echo ""
echo "[STEP 2/6] Installing Python dependencies..."
echo "Installing base dependencies (MQTT, psutil)..."
pip3 install paho-mqtt psutil --break-system-packages || pip3 install paho-mqtt psutil

echo "Installing BLE dependencies (bleak, cryptography)..."
pip3 install bleak cryptography --break-system-packages || pip3 install bleak cryptography

# Enable Bluetooth service
echo "Enabling Bluetooth service..."
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

echo ""
echo "[STEP 3/6] Configuring agent..."

# Check if config.json already exists
if [ -f "$SCRIPT_DIR/config.json" ]; then
    echo "Configuration file already exists: $SCRIPT_DIR/config.json"
    read -p "Do you want to reconfigure? (y/n) [n]: " RECONFIG
    RECONFIG=${RECONFIG:-n}
    
    if [[ ! "$RECONFIG" =~ ^[Yy]$ ]]; then
        echo "Keeping existing configuration."
        SKIP_CONFIG=true
    fi
fi

if [ "$SKIP_CONFIG" != "true" ]; then
    # Try auto-discovery first
    echo ""
    echo "Attempting to auto-discover MQTT broker..."
    
    if python3 "$SCRIPT_DIR/broker_discovery.py" 1883; then
        echo "✓ Broker discovered successfully!"
        # broker_discovery.py will have created config.json if user confirmed
        if [ ! -f "$SCRIPT_DIR/config.json" ]; then
            # User didn't save, ask manually
            read -p "Enter MQTT Broker IP address [192.168.1.100]: " BROKER_IP
            BROKER_IP=${BROKER_IP:-192.168.1.100}
            
            read -p "Enter MQTT Broker Port [1883]: " BROKER_PORT
            BROKER_PORT=${BROKER_PORT:-1883}
            
            read -p "Enter BLE Server Name [WatermelonD]: " BLE_SERVER
            BLE_SERVER=${BLE_SERVER:-WatermelonD}
            
            # Create config.json
            cat > "$SCRIPT_DIR/config.json" <<EOF
{
  "broker_address": "$BROKER_IP",
  "broker_port": $BROKER_PORT,
  "agent_id": "AUTO",
  "telemetry_interval": 10,
  "log_level": "INFO",
  "ble_server_name": "$BLE_SERVER",
  "connectivity_check_interval": 30
}
EOF
        fi
    else
        echo "Auto-discovery failed. Manual configuration required."
        read -p "Enter MQTT Broker IP address [192.168.1.100]: " BROKER_IP
        BROKER_IP=${BROKER_IP:-192.168.1.100}
        
        read -p "Enter MQTT Broker Port [1883]: " BROKER_PORT
        BROKER_PORT=${BROKER_PORT:-1883}
        
        read -p "Enter BLE Server Name [WatermelonD]: " BLE_SERVER
        BLE_SERVER=${BLE_SERVER:-WatermelonD}
        
        # Create config.json
        cat > "$SCRIPT_DIR/config.json" <<EOF
{
  "broker_address": "$BROKER_IP",
  "broker_port": $BROKER_PORT,
  "agent_id": "AUTO",
  "telemetry_interval": 10,
  "log_level": "INFO",
  "ble_server_name": "$BLE_SERVER",
  "connectivity_check_interval": 30
}
EOF
    fi
    
    echo "✓ Configuration saved to $SCRIPT_DIR/config.json"
fi

echo ""
echo "[STEP 4/6] Creating systemd service..."

# Get current user
if [ "$EUID" -eq 0 ]; then
    INSTALL_USER="$SUDO_USER"
else
    INSTALL_USER=$(whoami)
fi

USER_HOME=$(eval echo ~$INSTALL_USER)

# Create systemd service file
SERVICE_FILE="$USER_HOME/.config/systemd/user/berry_agent.service"
mkdir -p "$USER_HOME/.config/systemd/user"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=BerryConnect MQTT Agent
After=network.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 $SCRIPT_DIR/agent.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

echo "✓ Service file created: $SERVICE_FILE"

echo ""
echo "[STEP 5/6] Enabling and starting service..."

# Enable linger for user to allow services to run without login
sudo loginctl enable-linger $INSTALL_USER

# Reload systemd, enable and start service
sudo -u $INSTALL_USER XDG_RUNTIME_DIR=/run/user/$(id -u $INSTALL_USER) systemctl --user daemon-reload
sudo -u $INSTALL_USER XDG_RUNTIME_DIR=/run/user/$(id -u $INSTALL_USER) systemctl --user enable berry_agent.service
sudo -u $INSTALL_USER XDG_RUNTIME_DIR=/run/user/$(id -u $INSTALL_USER) systemctl --user start berry_agent.service

echo ""
echo "========================================="
echo "=== Installation Complete!            ==="
echo "========================================="
echo ""
echo "BerryConnect Agent has been installed and started."
echo ""
echo "✅ WiFi/MQTT connectivity: Enabled"
echo "✅ BLE Fallback: Enabled (automatic)"
echo "✅ Encryption: AES-128-GCM (BLE mode)"
echo ""
echo "Useful commands:"
echo "  Check status:  systemctl --user status berry_agent"
echo "  View logs:     journalctl --user -u berry_agent -f"
echo "  Restart:       systemctl --user restart berry_agent"
echo "  Stop:          systemctl --user stop berry_agent"
echo ""
echo "Configuration file: $SCRIPT_DIR/config.json"
echo ""

# Show current status
sleep 2
echo "Current service status:"
sudo -u $INSTALL_USER XDG_RUNTIME_DIR=/run/user/$(id -u $INSTALL_USER) systemctl --user status berry_agent --no-pager || true
