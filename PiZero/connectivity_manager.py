#!/usr/bin/env python3
"""
Connectivity Manager - Auto-switching between WiFi/MQTT and BLE
Monitors connectivity and switches transport layer automatically
"""

import socket
import time
import logging
import asyncio
from typing import Optional, Callable
from enum import Enum
from threading import Thread, Event


class ConnectionMode(Enum):
    """Connection modes"""
    OFFLINE = "offline"
    MQTT = "mqtt"
    BLE = "ble"


class ConnectivityManager:
    """
    Manages connectivity state and auto-switching between MQTT and BLE
    """
    
    def __init__(
        self,
        mqtt_broker: str,
        mqtt_port: int,
        ble_server_name: str = "WatermelonD",
        check_interval: int = 30
    ):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.ble_server_name = ble_server_name
        self.check_interval = check_interval
        
        self.current_mode = ConnectionMode.OFFLINE
        self.is_monitoring = False
        self.stop_event = Event()
        self.monitor_thread: Optional[Thread] = None
        self.callback: Optional[Callable] = None
        
        self.logger = logging.getLogger("ConnectivityManager")
    
    def check_mqtt_connectivity(self) -> bool:
        """
        Check if MQTT broker is reachable
        Returns True if broker responds to TCP connection
        """
        if self.mqtt_broker == "AUTO":
            self.logger.debug("Broker set to AUTO, skipping MQTT check")
            return False
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((self.mqtt_broker, self.mqtt_port))
            sock.close()
            
            if result == 0:
                self.logger.debug(f"MQTT broker {self.mqtt_broker}:{self.mqtt_port} is reachable")
                return True
            else:
                self.logger.debug(f"MQTT broker not reachable (error code: {result})")
                return False
                
        except socket.gaierror:
            self.logger.warning(f"DNS resolution failed for {self.mqtt_broker}")
            return False
        except Exception as e:
            self.logger.error(f"Error checking MQTT connectivity: {e}")
            return False
    
    async def check_ble_connectivity(self) -> bool:
        """
        Check if BLE server is advertising
        Returns True if server found via BLE scan
        """
        try:
            from bleak import BleakScanner
            
            # Scan for 5 seconds
            devices = await BleakScanner.discover(timeout=5.0)
            
            for device in devices:
                # Check if device name matches
                if device.name and self.ble_server_name.lower() in device.name.lower():
                    self.logger.debug(f"Found BLE server: {device.name} ({device.address})")
                    return True
            
            self.logger.debug("BLE server not found in scan")
            return False
            
        except ImportError:
            self.logger.warning("bleak not installed, BLE unavailable")
            return False
        except Exception as e:
            self.logger.error(f"Error checking BLE connectivity: {e}")
            return False
    
    def check_connectivity(self) -> ConnectionMode:
        """
        Check current connectivity and return best available mode
        Priority: MQTT > BLE > OFFLINE
        """
        # Try MQTT first (preferred)
        if self.check_mqtt_connectivity():
            return ConnectionMode.MQTT
        
        # Try BLE as fallback
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            ble_available = loop.run_until_complete(self.check_ble_connectivity())
            loop.close()
            
            if ble_available:
                return ConnectionMode.BLE
        except Exception as e:
            self.logger.error(f"BLE check failed: {e}")
        
        # No connectivity
        return ConnectionMode.OFFLINE
    
    def _monitor_loop(self):
        """Background monitoring loop (runs in thread)"""
        self.logger.info("Starting connectivity monitoring")
        
        while not self.stop_event.is_set():
            # Check connectivity
            new_mode = self.check_connectivity()
            
            # If mode changed, trigger callback
            if new_mode != self.current_mode:
                old_mode = self.current_mode
                self.current_mode = new_mode
                
                self.logger.warning(f"Connection mode changed: {old_mode.value} → {new_mode.value}")
                
                if self.callback:
                    try:
                        self.callback(old_mode, new_mode)
                    except Exception as e:
                        self.logger.error(f"Error in mode change callback: {e}")
            
            # Wait for next check
            self.stop_event.wait(self.check_interval)
        
        self.logger.info("Connectivity monitoring stopped")
    
    def start_monitoring(self, callback: Callable[[ConnectionMode, ConnectionMode], None]):
        """
        Start monitoring connectivity in background thread
        
        Args:
            callback: Function called when mode changes (old_mode, new_mode)
        """
        if self.is_monitoring:
            self.logger.warning("Monitoring already started")
            return
        
        self.callback = callback
        self.is_monitoring = True
        self.stop_event.clear()
        
        self.monitor_thread = Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        self.logger.info("Connectivity monitoring started")
    
    def stop_monitoring(self):
        """Stop monitoring"""
        if not self.is_monitoring:
            return
        
        self.logger.info("Stopping connectivity monitoring...")
        self.stop_event.set()
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        self.is_monitoring = False
        self.logger.info("Monitoring stopped")
    
    def force_mode(self, mode: ConnectionMode):
        """
        Force a specific connection mode (for testing)
        Stops monitoring if active
        """
        if self.is_monitoring:
            self.stop_monitoring()
        
        self.logger.info(f"Forcing connection mode to: {mode.value}")
        old_mode = self.current_mode
        self.current_mode = mode
        
        if self.callback and old_mode != mode:
            self.callback(old_mode, mode)
    
    def get_current_mode(self) -> ConnectionMode:
        """Get current connection mode"""
        return self.current_mode


# --- Testing ---
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("Connectivity Manager Test")
    print("=" * 50)
    
    # Create manager
    manager = ConnectivityManager(
        mqtt_broker="localhost",  # Change to your broker
        mqtt_port=1883,
        ble_server_name="WatermelonD",
        check_interval=10
    )
    
    # Check initial connectivity
    print(f"\nInitial check: {manager.check_connectivity().value}")
    
    # Define callback
    def on_mode_change(old_mode, new_mode):
        print(f"\n🔄 MODE CHANGE: {old_mode.value} → {new_mode.value}")
    
    # Start monitoring
    print("\nStarting monitoring (will check every 10s)...")
    print("Try disconnecting/reconnecting WiFi to test auto-switch")
    print("Press Ctrl+C to stop\n")
    
    manager.start_monitoring(on_mode_change)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping...")
        manager.stop_monitoring()
        print("Done!")
