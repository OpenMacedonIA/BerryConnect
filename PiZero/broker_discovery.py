#!/usr/bin/env python3
"""
Broker Discovery Module for BerryConnect Agents
Auto-discovers MQTT broker on the local network using multiple methods
"""

import socket
import subprocess
import time
import json

def get_local_ip():
    """Get the local IP address of this device"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def get_network_prefix():
    """Get network prefix from local IP (e.g., '192.168.1')"""
    local_ip = get_local_ip()
    parts = local_ip.split('.')
    return '.'.join(parts[:3])

def test_mqtt_connection(host, port=1883, timeout=2):
    """Test if MQTT broker is accessible at given host:port"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

def discover_via_mdns():
    """Try to discover MQTT broker via mDNS/Avahi"""
    try:
        # Try using avahi-browse if available
        result = subprocess.run(
            ['avahi-browse', '-t', '_mqtt._tcp', '-r', '-p'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # Parse avahi output
            for line in result.stdout.split('\n'):
                if 'IPv4' in line and 'address' in line.lower():
                    parts = line.split(';')
                    if len(parts) > 7:
                        ip = parts[7]
                        port = parts[8] if len(parts) > 8 else 1883
                        if test_mqtt_connection(ip, int(port)):
                            return ip, int(port)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return None, None

def discover_via_scan(port=1883):
    """Scan common IPs on the local network for MQTT broker"""
    network_prefix = get_network_prefix()
    
    # Common router/server IPs to try first
    common_ips = [1, 100, 10, 2, 254]
    
    print(f"Scanning network {network_prefix}.x for MQTT broker...")
    
    for ip_suffix in common_ips:
        host = f"{network_prefix}.{ip_suffix}"
        print(f"  Trying {host}:{port}...", end=" ")
        if test_mqtt_connection(host, port):
            print("✓ Found!")
            return host, port
        print("✗")
    
    return None, None

def discover_broker(port=1883, verbose=True):
    """
    Discover MQTT broker using multiple methods
    Returns: (host, port) tuple or (None, None) if not found
    """
    if verbose:
        print("=" * 50)
        print("BerryConnect Broker Discovery")
        print("=" * 50)
    
    # Method 1: mDNS/Avahi
    if verbose:
        print("\n[1/2] Trying mDNS/Avahi discovery...")
    host, port = discover_via_mdns()
    if host:
        if verbose:
            print(f"✓ Found broker via mDNS: {host}:{port}")
        return host, port
    if verbose:
        print("  No broker found via mDNS")
    
    # Method 2: Network scan
    if verbose:
        print("\n[2/2] Scanning local network...")
    host, port = discover_via_scan(port)
    if host:
        if verbose:
            print(f"✓ Found broker: {host}:{port}")
        return host, port
    
    if verbose:
        print("\n✗ Could not auto-discover MQTT broker")
        print("  Please configure manually in config.json")
    
    return None, None

def save_broker_config(host, port, config_path="config.json"):
    """Save discovered broker configuration to file"""
    config = {
        "broker_address": host,
        "broker_port": port,
        "agent_id": "AUTO",
        "telemetry_interval": 10
    }
    
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"\n✓ Configuration saved to {config_path}")

if __name__ == "__main__":
    import sys
    
    # Allow custom port via command line
    port = 1883
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            sys.exit(1)
    
    host, port = discover_broker(port)
    
    if host:
        print("\n" + "=" * 50)
        print(f"Broker: {host}:{port}")
        print("=" * 50)
        
        # Ask if user wants to save
        try:
            response = input("\nSave this configuration? (y/n): ").strip().lower()
            if response == 'y':
                save_broker_config(host, port)
        except (KeyboardInterrupt, EOFError):
            print("\n\nConfiguration not saved.")
        
        sys.exit(0)
    else:
        sys.exit(1)
