#!/usr/bin/env python3
"""
BLE Server - Bluetooth Low Energy GATT server for WatermelonD
Receives encrypted telemetry and alerts from BerryConnect agents
"""

import asyncio
import logging
from typing import Dict, Optional, Callable
from threading import Thread
import queue

# Import BCP protocol (needs to be in path)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "BerryConnect" / "PiZero"))

from bcp_protocol import (
    BCPProtocol,
    MessageType,
    AlertCode,
    BERRYCONNECT_SERVICE_UUID,
    TELEMETRY_CHAR_UUID,
    ALERTS_CHAR_UUID,
    COMMANDS_CHAR_UUID,
    RESPONSES_CHAR_UUID,
    METADATA_CHAR_UUID,
    KEYEXCHANGE_CHAR_UUID
)

try:
    from bless import BlessServer, BlessGATTCharacteristic, GattCharacteristicsFlags
    BLESS_AVAILABLE = True
except ImportError:
    BLESS_AVAILABLE = False
    logging.warning("bless not installed, BLE server unavailable")


class BLEServer:
    """
    BLE GATT server for receiving encrypted agent data
    Runs in background thread and forwards events to message bus
    """
    
    def __init__(self, event_queue: queue.Queue, server_name: str = "WatermelonD"):
        self.server_name = server_name
        self.event_queue = event_queue
        
        self.server: Optional[BlessServer] = None
        self.protocols: Dict[str, BCPProtocol] = {}  # address -> protocol
        self.running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        
        self.logger = logging.getLogger("BLEServer")
        
        if not BLESS_AVAILABLE:
            self.logger.error("bless library not available, BLE disabled")
    
    async def _setup_gatt_server(self):
        """Setup GATT service and characteristics"""
        self.server = BlessServer(name=self.server_name)
        
        # Add BerryConnect service
        await self.server.add_new_service(BERRYCONNECT_SERVICE_UUID)
        
        # Add characteristics
        
        # 1. Telemetry (Agent -> Server, encrypted)
        await self.server.add_new_characteristic(
            BERRYCONNECT_SERVICE_UUID,
            TELEMETRY_CHAR_UUID,
            GattCharacteristicsFlags.write | GattCharacteristicsFlags.read,
            None,
            self._on_telemetry_write
        )
        
        # 2. Alerts (Agent -> Server, encrypted)
        await self.server.add_new_characteristic(
            BERRYCONNECT_SERVICE_UUID,
            ALERTS_CHAR_UUID,
            GattCharacteristicsFlags.write | GattCharacteristicsFlags.read,
            None,
            self._on_alert_write
        )
        
        # 3. Commands (Server -> Agent, encrypted)
        await self.server.add_new_characteristic(
            BERRYCONNECT_SERVICE_UUID,
            COMMANDS_CHAR_UUID,
            GattCharacteristicsFlags.write | GattCharacteristicsFlags.notify,
            None,
            None
        )
        
        # 4. Responses (Agent -> Server, encrypted)
        await self.server.add_new_characteristic(
            BERRYCONNECT_SERVICE_UUID,
            RESPONSES_CHAR_UUID,
            GattCharacteristicsFlags.write | GattCharacteristicsFlags.read,
            None,
            self._on_response_write
        )
        
        # 5. Metadata (Agent info, plaintext)
        await self.server.add_new_characteristic(
            BERRYCONNECT_SERVICE_UUID,
            METADATA_CHAR_UUID,
            GattCharacteristicsFlags.read,
            b"WatermelonD BLE Server v1.0",
            None
        )
        
        # 6. Key Exchange (ECDH, plaintext)
        await self.server.add_new_characteristic(
            BERRYCONNECT_SERVICE_UUID,
            KEYEXCHANGE_CHAR_UUID,
            GattCharacteristicsFlags.read | GattCharacteristicsFlags.write,
            None,
            self._on_key_exchange
        )
        
        self.logger.info("GATT server configured")
    
    def _get_or_create_protocol(self, address: str) -> BCPProtocol:
        """Get existing protocol or create new one for this agent"""
        if address not in self.protocols:
            self.logger.info(f"Creating new protocol instance for {address}")
            self.protocols[address] = BCPProtocol()
        return self.protocols[address]
    
    # --- Characteristic Callbacks ---
    
    async def _on_key_exchange(self, characteristic: BlessGATTCharacteristic, value: bytes):
        """Handle key exchange from agent"""
        try:
            # Get agent address (simplified, would need proper tracking)
            # For now, use a placeholder
            address = "agent_address"  # TODO: Get from BLE connection
            
            self.logger.info(f"Key exchange from {address}")
            
            # Get protocol for this agent
            protocol = self._get_or_create_protocol(address)
            
            # Process agent's public key
            protocol.process_key_exchange(value)
            
            # Generate and send our public key
            our_kex = protocol.create_key_exchange_packet()
            
            # Update characteristic value so agent can read it
            characteristic.value = our_kex
            
            self.logger.info(f"✓ Key exchange completed with {address}")
            
        except Exception as e:
            self.logger.error(f"Key exchange failed: {e}")
    
    async def _on_telemetry_write(self, characteristic: BlessGATTCharacteristic, value: bytes):
        """Handle encrypted telemetry from agent"""
        try:
            address = "agent_address"  # TODO: Track properly
            protocol = self.protocols.get(address)
            
            if not protocol:
                self.logger.error("Telemetry received before key exchange")
                return
            
            # Decrypt and decode
            decoded = protocol.decode_packet(value)
            
            if decoded['type'] != 'telemetry':
                self.logger.warning(f"Unexpected message type: {decoded['type']}")
                return
            
            self.logger.debug(f"Telemetry: CPU={decoded['cpu_percent']}%, RAM={decoded['ram_percent']}%")
            
            # Forward to message bus
            self.event_queue.put({
                'source': 'ble',
                'agent_id': address,
                'type': 'telemetry',
                'data': decoded
            })
            
        except Exception as e:
            self.logger.error(f"Error processing telemetry: {e}")
    
    async def _on_alert_write(self, characteristic: BlessGATTCharacteristic, value: bytes):
        """Handle encrypted alert from agent"""
        try:
            address = "agent_address"  # TODO: Track properly
            protocol = self.protocols.get(address)
            
            if not protocol:
                self.logger.error("Alert received before key exchange")
                return
            
            # Decrypt and decode
            decoded = protocol.decode_packet(value)
            
            if decoded['type'] != 'alert':
                self.logger.warning(f"Unexpected message type: {decoded['type']}")
                return
            
            alert_name = decoded['alert_code'].name
            message = decoded.get('message', '')
            
            self.logger.warning(f"ALERT from {address}: {alert_name} - {message}")
            
            # Forward to message bus
            self.event_queue.put({
                'source': 'ble',
                'agent_id': address,
                'type': 'alert',
                'data': decoded
            })
            
        except Exception as e:
            self.logger.error(f"Error processing alert: {e}")
    
    async def _on_response_write(self, characteristic: BlessGATTCharacteristic, value: bytes):
        """Handle command response from agent"""
        try:
            address = "agent_address"  # TODO: Track properly
            protocol = self.protocols.get(address)
            
            if not protocol:
                self.logger.error("Response received before key exchange")
                return
            
            # Decrypt and decode
            decoded = protocol.decode_packet(value)
            
            if decoded['type'] != 'response':
                self.logger.warning(f"Unexpected message type: {decoded['type']}")
                return
            
            self.logger.info(f"Command response: ID={decoded['command_id']}, Status={decoded['status_code'].name}")
            
            # Forward to message bus
            self.event_queue.put({
                'source': 'ble',
                'agent_id': address,
                'type': 'response',
                'data': decoded
            })
            
        except Exception as e:
            self.logger.error(f"Error processing response: {e}")
    
    # --- Server Lifecycle ---
    
    async def _run_server(self):
        """Main server loop"""
        try:
            self.logger.info("Setting up BLE server...")
            await self._setup_gatt_server()
            
            self.logger.info("Starting BLE advertising...")
            await self.server.start()
            
            self.running = True
            self.logger.info(f"✓ BLE server '{self.server_name}' is running")
            
            # Keep server running
            while self.running:
                await asyncio.sleep(1)
            
            self.logger.info("Stopping BLE server...")
            await self.server.stop()
            
        except Exception as e:
            self.logger.error(f"Server error: {e}")
            self.running = False
    
    def start(self):
        """Start BLE server in background thread"""
        if not BLESS_AVAILABLE:
            self.logger.error("Cannot start BLE server: bless not installed")
            return False
        
        if self.running:
            self.logger.warning("Server already running")
            return True
        
        def run_in_thread():
            """Run asyncio loop in thread"""
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            try:
                self.loop.run_until_complete(self._run_server())
            except Exception as e:
                self.logger.error(f"Server thread error: {e}")
            finally:
                self.loop.close()
        
        thread = Thread(target=run_in_thread, daemon=True, name="BLEServer")
        thread.start()
        
        self.logger.info("BLE server thread started")
        return True
    
    def stop(self):
        """Stop BLE server"""
        if not self.running:
            return
        
        self.logger.info("Stopping BLE server...")
        self.running = False
        
        # Give it time to clean up
        import time
        time.sleep(2)
    
    async def send_command(self, agent_address: str, command_code: int, command_id: int):
        """
        Send command to agent via BLE
        
        Args:
            agent_address: BLE address of agent
            command_code: Command code (see CommandCode enum)
            command_id: Unique command ID for tracking
        """
        protocol = self.protocols.get(agent_address)
        
        if not protocol:
            self.logger.error(f"No protocol for {agent_address}, key exchange needed")
            return False
        
        try:
            # Encode command
            packet = protocol.encode_command(command_code, command_id)
            
            # Send via notify (would need proper BLE connection tracking)
            # await self.server.notify(agent_address, COMMANDS_CHAR_UUID, packet)
            
            self.logger.info(f"Sent command {command_code} to {agent_address}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send command: {e}")
            return False


# --- Standalone Test ---
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("BLE Server Test")
    print("=" * 50)
    
    if not BLESS_AVAILABLE:
        print("\n❌ ERROR: bless library not installed")
        print("Install with: pip3 install bless")
        sys.exit(1)
    
    # Create event queue
    event_queue = queue.Queue()
    
    # Create and start server
    server = BLEServer(event_queue, server_name="WatermelonD-Test")
    
    print("\nStarting BLE server...")
    server.start()
    
    print("Server is running. Connect from an agent to test.")
    print("Press Ctrl+C to stop\n")
    
    try:
        # Monitor events
        while True:
            try:
                event = event_queue.get(timeout=1)
                print(f"\n📨 Event: {event['type']} from {event['agent_id']}")
                print(f"   Data: {event['data']}")
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        print("\n\nStopping server...")
        server.stop()
        print("Done!")
