#!/usr/bin/env python3
"""
Camera Monitor Module for BerryConnect
Supports both PiCamera and USB webcams with motion detection
"""

import logging
import time
import os
from typing import Optional, Tuple
from pathlib import Path

logger = logging.getLogger("CameraMonitor")

class CameraMonitor:
    """Motion detection using PiCamera or USB webcam"""
    
    def __init__(self, config: dict, mqtt_client):
        self.config = config.get('camera', {})
        self.mqtt_client = mqtt_client
        self.enabled = self.config.get('enabled', False)
        self.camera_type = self.config.get('type', 'none')
        
        self.camera = None
        self.last_frame = None
        self.motion_detected = False
        
        if self.enabled and self.camera_type != 'none':
            self._init_camera()
    
    def _init_camera(self):
        """Initialize camera based on type"""
        if self.camera_type == 'picamera':
            self._init_picamera()
        elif self.camera_type == 'usb':
            self._init_usb_camera()
        else:
            logger.warning(f"Unknown camera type: {self.camera_type}")
    
    def _init_picamera(self):
        """Initialize Raspberry Pi Camera"""
        try:
            from picamera2 import Picamera2
            import numpy as np
            
            self.camera = Picamera2()
            config = self.camera.create_still_configuration(
                main={"size": (640, 480)}
            )
            self.camera.configure(config)
            self.camera.start()
            time.sleep(2)  # Camera warmup
            
            logger.info("✓ PiCamera initialized")
        except ImportError:
            logger.error("picamera2 library not found")
            self.enabled = False
        except Exception as e:
            logger.error(f"Failed to initialize PiCamera: {e}")
            self.enabled = False
    
    def _init_usb_camera(self):
        """Initialize USB webcam"""
        try:
            import cv2
            
            device_id = self.config.get('device_id', 0)
            self.camera = cv2.VideoCapture(device_id)
            
            if not self.camera.isOpened():
                raise RuntimeError(f"Cannot open camera {device_id}")
            
            # Set resolution
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            logger.info(f"✓ USB Camera {device_id} initialized")
        except ImportError:
            logger.error("opencv-python library not found")
            self.enabled = False
        except Exception as e:
            logger.error(f"Failed to initialize USB camera: {e}")
            self.enabled = False
    
    def capture_frame(self) -> Optional:
        """Capture a single frame"""
        if not self.enabled or not self.camera:
            return None
        
        try:
            if self.camera_type == 'picamera':
                import numpy as np
                frame = self.camera.capture_array()
                # Convert to grayscale
                if len(frame.shape) == 3:
                    import cv2
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                return frame
            
            elif self.camera_type == 'usb':
                ret, frame = self.camera.read()
                if ret:
                    import cv2
                    # Convert to grayscale
                    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                return None
        except Exception as e:
            logger.error(f"Failed to capture frame: {e}")
            return None
    
    def detect_motion(self) -> bool:
        """Detect motion by comparing frames"""
        if not self.enabled:
            return False
        
        try:
            import cv2
            import numpy as np
            
            current_frame = self.capture_frame()
            if current_frame is None:
                return False
            
            # First frame - just save it
            if self.last_frame is None:
                self.last_frame = current_frame
                return False
            
            # Calculate difference
            frame_diff = cv2.absdiff(self.last_frame, current_frame)
            
            # Threshold
            _, thresh = cv2.threshold(frame_diff, 30, 255, cv2.THRESH_BINARY)
            
            # Count changed pixels
            motion_pixels = cv2.countNonZero(thresh)
            total_pixels = current_frame.shape[0] * current_frame.shape[1]
            motion_percent = (motion_pixels / total_pixels) * 100
            
            threshold = self.config.get('motion_threshold', 2.0)
            
            # Update last frame
            self.last_frame = current_frame
            
            return motion_percent > threshold
            
        except Exception as e:
            logger.error(f"Motion detection error: {e}")
            return False
    
    def save_capture(self, reason="motion") -> Optional[str]:
        """Save a capture to disk"""
        if not self.enabled or not self.config.get('save_captures', True):
            return None
        
        try:
            import cv2
            from datetime import datetime
            
            # Create captures directory
            captures_path = Path(self.config.get('captures_path', '/tmp/captures'))
            captures_path.mkdir(parents=True, exist_ok=True)
            
            # Check max captures limit
            max_captures = self.config.get('max_captures', 100)
            existing = list(captures_path.glob('*.jpg'))
            if len(existing) >= max_captures:
                # Delete oldest
                oldest = min(existing, key=lambda p: p.stat().st_mtime)
                oldest.unlink()
            
            # Capture and save
            if self.camera_type == 'picamera':
                frame = self.camera.capture_array()
                # Convert RGB to BGR for cv2
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            elif self.camera_type == 'usb':
                ret, frame = self.camera.read()
                if not ret:
                    return None
            else:
                return None
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{reason}_{timestamp}.jpg"
            filepath = captures_path / filename
            
            # Save
            cv2.imwrite(str(filepath), frame)
            logger.info(f"Saved capture: {filepath}")
            
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Failed to save capture: {e}")
            return None
    
    def check_and_alert(self, agent_id: str, topic_alerts: str):
        """Check for motion and send alert if detected"""
        if not self.enabled:
            return
        
        if self.detect_motion():
            import json
            import datetime
            
            logger.warning("MOTION DETECTED!")
            
            # Save capture
            capture_path = self.save_capture("motion")
            
            # Send alert
            alert_data = {
                "type": "camera_motion",
                "message": "Motion detected by camera",
                "timestamp": datetime.datetime.now().isoformat(),
                "capture_path": capture_path
            }
            
            # TODO: Optionally send image data as base64
            # if self.config.get('send_image_mqtt', False):
            #     with open(capture_path, 'rb') as f:
            #         import base64
            #         alert_data['image_base64'] = base64.b64encode(f.read()).decode()
            
            self.mqtt_client.publish(topic_alerts, json.dumps(alert_data))
    
    def cleanup(self):
        """Release camera resources"""
        if self.camera:
            if self.camera_type == 'picamera':
                self.camera.stop()
            elif self.camera_type == 'usb':
                self.camera.release()
            logger.info("Camera released")
