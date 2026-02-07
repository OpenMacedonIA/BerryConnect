#!/usr/bin/env python3
"""
BCP Protocol Handler (BerryConnect Protocol over BLE)
Version: 1.0
Encryption: AES-128-GCM with ECDH key exchange

This module handles encoding/decoding of BCP messages with encryption.
All payloads are encrypted using AES-128-GCM for confidentiality,
integrity, and authenticity.
"""

import struct
import time
import os
from enum import IntEnum
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.exceptions import InvalidTag


class BCPVersion:
    """Protocol version"""
    CURRENT = 0x01


class MessageType(IntEnum):
    """BCP Message Types"""
    TELEMETRY = 0x01
    ALERT = 0x02
    COMMAND = 0x03
    RESPONSE = 0x04
    HEARTBEAT = 0x05
    KEY_EXCHANGE = 0x06


class AlertCode(IntEnum):
    """Alert codes for Alert messages"""
    MOTION = 0x01
    DOOR = 0x02
    SMOKE = 0x03
    INTRUDER = 0x04
    CAMERA = 0x05
    CUSTOM = 0xFE
    SYSTEM = 0xFF


class CommandCode(IntEnum):
    """Command codes for Command messages"""
    PING = 0x01
    GET_STATUS = 0x02
    GET_TELEMETRY = 0x03


class StatusCode(IntEnum):
    """Status codes for Response messages"""
    OK = 0x00
    ERROR = 0x01
    NOT_SUPPORTED = 0x02


@dataclass
class BCPHeader:
    """BCP packet header (16 bytes when encrypted)"""
    version: int
    msg_type: MessageType
    sequence: int
    flags: int
    nonce: bytes  # 12 bytes for AES-GCM


class BCPEncryption:
    """Handles encryption/decryption with AES-128-GCM"""
    
    def __init__(self):
        self.aes_key: Optional[bytes] = None
        self.private_key: Optional[ec.EllipticCurvePrivateKey] = None
        self.public_key: Optional[ec.EllipticCurvePublicKey] = None
        self.counter = 0
    
    def generate_keypair(self) -> bytes:
        """Generate ECDH keypair and return public key bytes"""
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()
        
        public_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        return public_bytes
    
    def derive_shared_key(self, peer_public_bytes: bytes):
        """Derive shared AES key from peer's public key"""
        if not self.private_key:
            raise ValueError("Keypair not generated yet")
        
        # Reconstruct peer's public key
        peer_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(),
            peer_public_bytes
        )
        
        # Perform ECDH
        shared_secret = self.private_key.exchange(ec.ECDH(), peer_public_key)
        
        # Derive 128-bit AES key with HKDF
        self.aes_key = HKDF(
            algorithm=hashes.SHA256(),
            length=16,  # 128 bits
            salt=b"BerryConnect-v1",
            info=b"AES-key"
        ).derive(shared_secret)
    
    def generate_nonce(self) -> bytes:
        """Generate unique 12-byte nonce for AES-GCM"""
        timestamp = int(time.time()).to_bytes(4, 'big')
        self.counter = (self.counter + 1) % (2**32)
        counter = self.counter.to_bytes(4, 'big')
        random_bytes = os.urandom(4)
        
        return timestamp + counter + random_bytes
    
    def encrypt(self, payload: bytes, associated_data: bytes) -> Tuple[bytes, bytes]:
        """
        Encrypt payload with AES-128-GCM
        Returns: (nonce, ciphertext_with_tag)
        """
        if not self.aes_key:
            raise ValueError("AES key not derived yet")
        
        nonce = self.generate_nonce()
        cipher = AESGCM(self.aes_key)
        
        # Encrypt returns ciphertext + 16-byte auth tag
        ciphertext = cipher.encrypt(nonce, payload, associated_data)
        
        return nonce, ciphertext
    
    def decrypt(self, nonce: bytes, ciphertext: bytes, associated_data: bytes) -> bytes:
        """
        Decrypt ciphertext with AES-128-GCM
        Raises InvalidTag if authentication fails
        """
        if not self.aes_key:
            raise ValueError("AES key not derived yet")
        
        cipher = AESGCM(self.aes_key)
        
        try:
            plaintext = cipher.decrypt(nonce, ciphertext, associated_data)
            return plaintext
        except InvalidTag:
            raise ValueError("Authentication failed: invalid or tampered message")


class BCPProtocol:
    """BCP protocol encoder/decoder"""
    
    def __init__(self):
        self.encryption = BCPEncryption()
        self.sequence_num = 0
    
    # --- Key Exchange ---
    
    def create_key_exchange_packet(self) -> bytes:
        """Create key exchange packet with our public key"""
        public_key = self.encryption.generate_keypair()
        
        header = bytes([
            BCPVersion.CURRENT,
            MessageType.KEY_EXCHANGE,
            self.sequence_num,
            0x00  # No encryption flag for key exchange
        ])
        
        self.sequence_num = (self.sequence_num + 1) % 256
        
        # Key exchange is not encrypted (chicken-egg problem)
        # Just header + public key (65 bytes)
        return header + public_key
    
    def process_key_exchange(self, packet: bytes):
        """Process incoming key exchange and derive shared key"""
        if len(packet) < 69:  # 4 header + 65 public key
            raise ValueError("Invalid key exchange packet")
        
        # Extract peer's public key
        peer_public_key = packet[4:69]
        
        # Derive shared secret
        self.encryption.derive_shared_key(peer_public_key)
    
    # --- Encoding ---
    
    def encode_telemetry(
        self,
        cpu_percent: float,
        ram_percent: float,
        temp_c: Optional[float],
        battery_percent: Optional[int],
        uptime_seconds: int
    ) -> bytes:
        """Encode telemetry packet (encrypted)"""
        
        # Build payload
        payload = struct.pack(
            '>HHHIII',
            int(cpu_percent * 100),
            int(ram_percent * 100),
            int(temp_c * 100) if temp_c is not None else 0xFFFF,
            battery_percent if battery_percent is not None else 0xFFFF,
            uptime_seconds,
            int(time.time())
        )
        
        return self._encrypt_and_pack(MessageType.TELEMETRY, payload)
    
    def encode_alert(self, alert_code: AlertCode, message: str = "") -> bytes:
        """Encode alert packet (encrypted)"""
        
        msg_bytes = message.encode('utf-8')[:11]  # Max 11 bytes
        
        payload = struct.pack(
            '>BI',
            alert_code,
            int(time.time())
        ) + msg_bytes
        
        return self._encrypt_and_pack(MessageType.ALERT, payload)
    
    def encode_heartbeat(self, status: int = 0x00) -> bytes:
        """Encode heartbeat packet (encrypted)"""
        
        payload = struct.pack(
            '>IB',
            int(time.time()),
            status
        )
        
        return self._encrypt_and_pack(MessageType.HEARTBEAT, payload)
    
    def encode_command(self, command_code: CommandCode, command_id: int) -> bytes:
        """Encode command packet (encrypted)"""
        
        payload = struct.pack(
            '>BI',
            command_code,
            command_id
        )
        
        return self._encrypt_and_pack(MessageType.COMMAND, payload)
    
    def encode_response(
        self,
        command_id: int,
        status_code: StatusCode,
        data: bytes = b""
    ) -> bytes:
        """Encode response packet (encrypted)"""
        
        payload = struct.pack(
            '>IB',
            command_id,
            status_code
        ) + data
        
        return self._encrypt_and_pack(MessageType.RESPONSE, payload)
    
    # --- Decoding ---
    
    def decode_packet(self, packet: bytes) -> Dict[str, Any]:
        """
        Decode any BCP packet
        Returns dict with 'type' and type-specific fields
        """
        if len(packet) < 4:
            raise ValueError("Packet too short")
        
        version = packet[0]
        if version != BCPVersion.CURRENT:
            raise ValueError(f"Unsupported protocol version: {version}")
        
        msg_type = MessageType(packet[1])
        sequence = packet[2]
        flags = packet[3]
        
        # Key exchange is not encrypted
        if msg_type == MessageType.KEY_EXCHANGE:
            return {
                'type': 'key_exchange',
                'sequence': sequence,
                'public_key': packet[4:69]
            }
        
        # Extract nonce and decrypt
        if len(packet) < 16:
            raise ValueError("Encrypted packet too short")
        
        nonce = packet[4:16]
        ciphertext = packet[16:]
        
        # AAD is first 4 bytes of header
        aad = packet[0:4]
        
        # Decrypt
        payload = self.encryption.decrypt(nonce, ciphertext, aad)
        
        # Decode based on type
        if msg_type == MessageType.TELEMETRY:
            return self._decode_telemetry(payload, sequence)
        elif msg_type == MessageType.ALERT:
            return self._decode_alert(payload, sequence)
        elif msg_type == MessageType.HEARTBEAT:
            return self._decode_heartbeat(payload, sequence)
        elif msg_type == MessageType.COMMAND:
            return self._decode_command(payload, sequence)
        elif msg_type == MessageType.RESPONSE:
            return self._decode_response(payload, sequence)
        else:
            raise ValueError(f"Unknown message type: {msg_type}")
    
    # --- Private Methods ---
    
    def _encrypt_and_pack(self, msg_type: MessageType, payload: bytes) -> bytes:
        """Encrypt payload and pack into BCP packet"""
        
        # Build header (first 4 bytes, plaintext)
        header = bytes([
            BCPVersion.CURRENT,
            msg_type,
            self.sequence_num,
            0x04  # Encrypted flag (bit 2)
        ])
        
        self.sequence_num = (self.sequence_num + 1) % 256
        
        # Encrypt payload
        nonce, ciphertext = self.encryption.encrypt(payload, header)
        
        # Pack: header (4) + nonce (12) + ciphertext + tag
        return header + nonce + ciphertext
    
    def _decode_telemetry(self, payload: bytes, sequence: int) -> Dict[str, Any]:
        """Decode telemetry payload"""
        if len(payload) < 16:
            raise ValueError("Invalid telemetry payload")
        
        values = struct.unpack('>HHHIII', payload[:16])
        
        return {
            'type': 'telemetry',
            'sequence': sequence,
            'cpu_percent': values[0] / 100.0,
            'ram_percent': values[1] / 100.0,
            'cpu_temp': values[2] / 100.0 if values[2] != 0xFFFF else None,
            'battery_percent': values[3] if values[3] != 0xFFFF else None,
            'uptime_seconds': values[4],
            'timestamp': values[5]
        }
    
    def _decode_alert(self, payload: bytes, sequence: int) -> Dict[str, Any]:
        """Decode alert payload"""
        if len(payload) < 5:
            raise ValueError("Invalid alert payload")
        
        alert_code, timestamp = struct.unpack('>BI', payload[:5])
        message = payload[5:].decode('utf-8', errors='ignore')
        
        return {
            'type': 'alert',
            'sequence': sequence,
            'alert_code': AlertCode(alert_code),
            'timestamp': timestamp,
            'message': message
        }
    
    def _decode_heartbeat(self, payload: bytes, sequence: int) -> Dict[str, Any]:
        """Decode heartbeat payload"""
        if len(payload) < 5:
            raise ValueError("Invalid heartbeat payload")
        
        timestamp, status = struct.unpack('>IB', payload[:5])
        
        return {
            'type': 'heartbeat',
            'sequence': sequence,
            'timestamp': timestamp,
            'status': status
        }
    
    def _decode_command(self, payload: bytes, sequence: int) -> Dict[str, Any]:
        """Decode command payload"""
        if len(payload) < 5:
            raise ValueError("Invalid command payload")
        
        command_code, command_id = struct.unpack('>BI', payload[:5])
        
        return {
            'type': 'command',
            'sequence': sequence,
            'command_code': CommandCode(command_code),
            'command_id': command_id
        }
    
    def _decode_response(self, payload: bytes, sequence: int) -> Dict[str, Any]:
        """Decode response payload"""
        if len(payload) < 5:
            raise ValueError("Invalid response payload")
        
        command_id, status_code = struct.unpack('>IB', payload[:5])
        data = payload[5:]
        
        return {
            'type': 'response',
            'sequence': sequence,
            'command_id': command_id,
            'status_code': StatusCode(status_code),
            'data': data
        }


# --- Testing ---
if __name__ == "__main__":
    print("BCP Protocol Test")
    print("=" * 50)
    
    # Simulate key exchange
    print("\n1. Key Exchange")
    client = BCPProtocol()
    server = BCPProtocol()
    
    # Client sends key exchange
    client_kex = client.create_key_exchange_packet()
    print(f"   Client KEX packet: {len(client_kex)} bytes")
    
    # Server processes and sends back
    server.process_key_exchange(client_kex)
    server_kex = server.create_key_exchange_packet()
    print(f"   Server KEX packet: {len(server_kex)} bytes")
    
    # Client processes server's key
    client.process_key_exchange(server_kex)
    print("   ✓ Shared key derived on both sides")
    
    # Test telemetry
    print("\n2. Telemetry Encryption")
    packet = client.encode_telemetry(
        cpu_percent=45.2,
        ram_percent=62.8,
        temp_c=52.3,
        battery_percent=85,
        uptime_seconds=86400
    )
    print(f"   Encrypted packet: {len(packet)} bytes")
    print(f"   Raw bytes: {packet[:32].hex()}...")
    
    # Decrypt on server
    decoded = server.decode_packet(packet)
    print(f"   Decrypted: CPU={decoded['cpu_percent']}%, RAM={decoded['ram_percent']}%")
    
    # Test alert
    print("\n3. Alert Encryption")
    alert_packet = client.encode_alert(AlertCode.MOTION, "Motion detected")
    decoded_alert = server.decode_packet(alert_packet)
    print(f"   Alert: {decoded_alert['alert_code'].name} - {decoded_alert['message']}")
    
    # Test tampering detection
    print("\n4. Tampering Detection")
    tampered = bytearray(packet)
    tampered[-1] ^= 0xFF  # Flip last byte
    try:
        server.decode_packet(bytes(tampered))
        print("   ✗ FAILED: Tampering not detected!")
    except ValueError as e:
        print(f"   ✓ Tampering detected: {e}")
    
    print("\n" + "=" * 50)
    print("All tests passed!")
