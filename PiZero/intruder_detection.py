#!/usr/bin/env python3
"""
Intruder Detection Module for BerryConnect
Network scanning and unknown device detection
"""

import logging
import json
import time
from pathlib import Path
from typing import Set, Dict, List

logger = logging.getLogger("IntruderDetection")

class IntruderDetector:
    """Detect unknown devices on the local network"""
    
    def __init__(self, config: dict, mqtt_client):
        self.config = config.get('intruder_detection', {})
        self.mqtt_client = mqtt_client
        self.enabled = self.config.get('enabled', False)
        
        self.known_devices = set()
        self.last_scan_time = 0
        self.scan_interval = self.config.get('scan_interval', 300)  # 5 minutes
        self.whitelist_path = Path(self.config.get('whitelist_path', 'known_devices.json'))
        
        if self.enabled:
            self._load_whitelist()
    
    def _load_whitelist(self):
        """Load known devices from whitelist file"""
        if self.whitelist_path.exists():
            try:
                with open(self.whitelist_path, 'r') as f:
                    data = json.load(f)
                    self.known_devices = set(data.get('known_macs', []))
                logger.info(f"Loaded {len(self.known_devices)} known devices")
            except Exception as e:
                logger.error(f"Failed to load whitelist: {e}")
        else:
            logger.warning(f"Whitelist not found: {self.whitelist_path}")
    
    def _save_whitelist(self):
        """Save known devices to whitelist file"""
        try:
            with open(self.whitelist_path, 'w') as f:
                json.dump({
                    'known_macs': list(self.known_devices),
                    'last_updated': time.time()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save whitelist: {e}")
    
    def scan_network(self) -> Set[str]:
        """Scan local network for devices using ARP"""
        try:
            from scapy.all import ARP, Ether, srp
            import socket
            
            # Get local IP range
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            
            # Assume /24 subnet
            network = '.'.join(local_ip.split('.')[0:3]) + '.0/24'
            
            logger.debug(f"Scanning network: {network}")
            
            # Create ARP request
            arp = ARP(pdst=network)
            ether = Ether(dst="ff:ff:ff:ff:ff:ff")
            packet = ether/arp
            
            # Send and receive
            result = srp(packet, timeout=2, verbose=0)[0]
            
            # Extract MAC addresses
            devices = set()
            for sent, received in result:
                devices.add(received.hwsrc.lower())
            
            logger.debug(f"Found {len(devices)} devices")
            return devices
            
        except ImportError:
            logger.error("scapy library not installed")
            return set()
        except Exception as e:
            logger.error(f"Network scan failed: {e}")
            return set()
    
    def detect_intruders(self) -> List[str]:
        """Detect unknown devices on the network"""
        if not self.enabled:
            return []
        
        # Check scan interval
        if time.time() - self.last_scan_time < self.scan_interval:
            return []
        
        self.last_scan_time = time.time()
        
        # Scan network
        current_devices = self.scan_network()
        
        # Find new devices
        new_devices = current_devices - self.known_devices
        
        if new_devices and self.config.get('alert_on_new', True):
            return list(new_devices)
        
        return []
    
    def add_device(self, mac: str):
        """Add device to known list"""
        mac = mac.lower()
        self.known_devices.add(mac)
        self._save_whitelist()
        logger.info(f"Added device to whitelist: {mac}")
    
    def remove_device(self, mac: str):
        """Remove device from known list"""
        mac = mac.lower()
        if mac in self.known_devices:
            self.known_devices.remove(mac)
            self._save_whitelist()
            logger.info(f"Removed device from whitelist: {mac}")
    
    def check_and_alert(self, agent_id: str, topic_alerts: str):
        """Check for intruders and send alerts"""
        intruders = self.detect_intruders()
        
        if intruders:
            import datetime
            
            alert_data = {
                "type": "intruder_alert",
                "message": f"Detected {len(intruders)} unknown device(s) on network",
                "unknown_macs": intruders,
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            self.mqtt_client.publish(topic_alerts, json.dumps(alert_data))
            logger.warning(f"INTRUDER ALERT: {intruders}")
