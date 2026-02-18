#!/usr/bin/env python3
"""
BLE Client - Bluetooth Low Energy client for BerryConnect agents
Handles connection, encryption, and data transmission via BLE
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from bleak import BleakClient, BleakScanner

from bcp_protocol import (
    BCPProtocol,
    MessageType,
    AlertCode,
    CommandCode,
    StatusCode
)


# BerryConnect Service and Characteristics UUIDs
BERRYCONNECT_SERVICE_UUID = "6ba1b001-90a1-11ec-b909-0242ac120002"
TELEMETRY_CHAR_UUID = "6ba1b002-90a1-11ec-b909-0242ac120002"
ALERTS_CHAR_UUID = "6ba1b003-90a1-11ec-b909-0242ac120002"
COMMANDS_CHAR_UUID = "6ba1b004-90a1-11ec-b909-0242ac120002"
RESPONSES_CHAR_UUID = "6ba1b005-90a1-11ec-b909-0242ac120002"
METADATA_CHAR_UUID = "6ba1b006-90a1-11ec-b909-0242ac120002"
KEYEXCHANGE_CHAR_UUID = "6ba1b007-90a1-11ec-b909-0242ac120002"


class BLEClient:
    """
    BLE client for BerryConnect agents
    Manages connection, key exchange, and encrypted communication
    """
    
    def __init__(self, agent_id: str, server_name: str = "WatermelonD"):
        self.agent_id = agent_id
        self.server_name = server_name
        self.server_address: Optional[str] = None
        
        self.client: Optional[BleakClient] = None
        self.protocol = BCPProtocol()
        self.connected = False
        self.key_exchanged = False
        
        self.logger = logging.getLogger(f"BLEClient[{agent_id}]")
    
    async def discover_server(self, timeout: float = 10.0) -> Optional[str]:
        """
        Scan for BLE server and return its address
        Returns None if not found
        """
        self.logger.info(f"Scanning for BLE server '{self.server_name}'...")
        
        devices = await BleakScanner.discover(timeout=timeout)
        
        for device in devices:
            if device.name and self.server_name.lower() in device.name.lower():
                self.logger.info(f"Found server: {device.name} at {device.address}")
                return device.address
        
        self.logger.warning("BLE server not found")
        return None
    
    async def connect(self, server_address: Optional[str] = None) -> bool:
        """
        Connect to BLE server and perform key exchange
        
        Args:
            server_address: MAC address of server (will scan if None)
        
        Returns:
            True if connection and key exchange successful
        """
        try:
            # Discover server if address not provided
            if server_address is None:
                server_address = await self.discover_server()
                if server_address is None:
                    return False
            
            self.server_address = server_address
            
            # Connect to GATT server
            self.logger.info(f"Connecting to {server_address}...")
            self.client = BleakClient(server_address)
            await self.client.connect()
            
            if not self.client.is_connected:
                self.logger.error("Failed to connect to BLE server")
                return False
            
            self.connected = True
            self.logger.info("Connected to BLE server")
            
            # Perform key exchange
            if not await self._exchange_keys():
                await self.disconnect()
                return False
            
            # Subscribe to notifications
            await self._subscribe_notifications()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.connected = False
            return False
    
    async def _exchange_keys(self) -> bool:
        """
        Perform ECDH key exchange with server
        Returns True if successful
        """
        try:
            self.logger.info("Starting key exchange...")
            
            # Generate and send our public key
            kex_packet = self.protocol.create_key_exchange_packet()
            await self.client.write_gatt_char(KEYEXCHANGE_CHAR_UUID, kex_packet)
            
            self.logger.debug(f"Sent public key ({len(kex_packet)} bytes)")
            
            # Read server's public key
            server_kex = await self.client.read_gatt_char(KEYEXCHANGE_CHAR_UUID)
            
            self.logger.debug(f"Received server public key ({len(server_kex)} bytes)")
            
            # Process key exchange
            self.protocol.process_key_exchange(server_kex)
            
            self.key_exchanged = True
            self.logger.info("✓ Key exchange completed, encryption enabled")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Key exchange failed: {e}")
            return False
    
    async def _subscribe_notifications(self):
        """Subscribe to command notifications"""
        try:
            def command_handler(sender, data):
                """Handle incoming command notifications"""
                try:
                    decoded = self.protocol.decode_packet(data)
                    self.logger.info(f"Received command: {decoded}")
                    # TODO: Process command
                except Exception as e:
                    self.logger.error(f"Error decoding command: {e}")
            
            await self.client.start_notify(COMMANDS_CHAR_UUID, command_handler)
            self.logger.debug("Subscribed to command notifications")
            
        except Exception as e:
            self.logger.warning(f"Failed to subscribe to notifications: {e}")
    
    async def send_telemetry(
        self,
        cpu_percent: float,
        ram_percent: float,
        temp_c: Optional[float] = None,
        battery_percent: Optional[int] = None,
        uptime_seconds: int = 0
    ) -> bool:
        """
        Send encrypted telemetry data
        Returns True if sent successfully
        """
        if not self.connected or not self.key_exchanged:
            self.logger.error("Not connected or key not exchanged")
            return False
        
        try:
            packet = self.protocol.encode_telemetry(
                cpu_percent, ram_percent, temp_c, battery_percent, uptime_seconds
            )
            
            await self.client.write_gatt_char(TELEMETRY_CHAR_UUID, packet)
            
            self.logger.debug(f"Sent telemetry: CPU={cpu_percent}%, RAM={ram_percent}%")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send telemetry: {e}")
            return False
    
    async def send_alert(self, alert_code: AlertCode, message: str = "") -> bool:
        """
        Send encrypted alert
        Returns True if sent successfully
        """
        if not self.connected or not self.key_exchanged:
            self.logger.error("Not connected or key not exchanged")
            return False
        
        try:
            packet = self.protocol.encode_alert(alert_code, message)
            await self.client.write_gatt_char(ALERTS_CHAR_UUID, packet)
            
            self.logger.info(f"Sent alert: {alert_code.name} - {message}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send alert: {e}")
            return False
    
    async def send_heartbeat(self, status: int = 0x00) -> bool:
        """
        Send encrypted heartbeat
        Returns True if sent successfully
        """
        if not self.connected or not self.key_exchanged:
            return False
        
        try:
            packet = self.protocol.encode_heartbeat(status)
            await self.client.write_gatt_char(TELEMETRY_CHAR_UUID, packet)
            
            self.logger.debug("Sent heartbeat")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send heartbeat: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from BLE server"""
        if self.client and self.connected:
            try:
                await self.client.disconnect()
                self.logger.info("Disconnected from BLE server")
            except Exception as e:
                self.logger.error(f"Error disconnecting: {e}")
        
        self.connected = False
        self.key_exchanged = False
        self.client = None
    
    def is_connected(self) -> bool:
        """Check if connected and encrypted"""
        return self.connected and self.key_exchanged


# --- Testing ---
async def test_ble_client():
    """Test BLE client functionality"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("BLE Client Test")
    print("=" * 50)
    
    client = BLEClient(agent_id="test-agent", server_name="WatermelonD")
    
    # Connect
    print("\n1. Connecting to server...")
    if await client.connect():
        print("   ✓ Connected and encrypted")
    else:
        print("   ✗ Connection failed")
        return
    
    # Send telemetry
    print("\n2. Sending telemetry...")
    await client.send_telemetry(
        cpu_percent=45.2,
        ram_percent=62.8,
        temp_c=52.3,
        battery_percent=85,
        uptime_seconds=86400
    )
    
    # Send alert
    print("\n3. Sending alert...")
    await client.send_alert(AlertCode.MOTION, "Test motion detected")
    
    # Send heartbeat
    print("\n4. Sending heartbeat...")
    await client.send_heartbeat()
    
    # Keep alive for a bit
    print("\n5. Keeping connection alive for 30s...")
    for i in range(3):
        await asyncio.sleep(10)
        await client.send_heartbeat()
        print(f"   Heartbeat {i+1}/3")
    
    # Disconnect
    print("\n6. Disconnecting...")
    await client.disconnect()
    print("   ✓ Disconnected")
    
    print("\n" + "=" * 50)
    print("Test completed!")


if __name__ == "__main__":
    asyncio.run(test_ble_client())
