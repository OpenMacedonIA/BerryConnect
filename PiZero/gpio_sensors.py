#!/usr/bin/env python3
"""
GPIO Sensors Module for BerryConnect
Supports multiple sensor types for home automation
"""

import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger("GPIOSensors")

class GPIOSensorsManager:
    """Manages all GPIO-based sensors"""
    
    def __init__(self, config: Dict, mqtt_client):
        self.config = config.get('sensors', {})
        self.mqtt_client = mqtt_client
        self.sensors_enabled = self.config.get('gpio_enabled', False)
        
        # Sensor instances
        self.sensors = {}
        
        # Last alert times (for cooldown)
        self.last_alert_times = {}
        
        if self.sensors_enabled:
            self._init_sensors()
    
    def _init_sensors(self):
        """Initialize all enabled sensors"""
        logger.info("Initializing GPIO sensors...")
        
        # DHT22 - Temperature and Humidity
        if self.config.get('dht22', {}).get('enabled'):
            try:
                import Adafruit_DHT
                self.sensors['dht22'] = DHT22Sensor(self.config['dht22'], Adafruit_DHT)
                logger.info("✓ DHT22 initialized")
            except ImportError:
                logger.warning("DHT22 library not found (Adafruit_DHT)")
        
        # PIR Motion Sensor
        if self.config.get('pir_motion', {}).get('enabled'):
            try:
                from gpiozero import MotionSensor
                self.sensors['pir_motion'] = PIRSensor(self.config['pir_motion'], MotionSensor)
                logger.info("✓ PIR Motion sensor initialized")
            except ImportError:
                logger.warning("gpiozero library not found")
        
        # MQ-135 Air Quality
        if self.config.get('mq135_air_quality', {}).get('enabled'):
            self.sensors['mq135'] = MQ135Sensor(self.config['mq135_air_quality'])
            logger.info("✓ MQ-135 Air Quality sensor initialized")
        
        # MQ-2 Smoke Detector
        if self.config.get('mq2_smoke', {}).get('enabled'):
            self.sensors['mq2'] = MQ2Sensor(self.config['mq2_smoke'])
            logger.info("✓ MQ-2 Smoke detector initialized")
        
        # BH1750 Light Sensor
        if self.config.get('bh1750_light', {}).get('enabled'):
            try:
                import board
                import adafruit_bh1750
                self.sensors['bh1750'] = BH1750Sensor(self.config['bh1750_light'], board, adafruit_bh1750)
                logger.info("✓ BH1750 Light sensor initialized")
            except ImportError:
                logger.warning("BH1750 library not found")
        
        # Magnetic Door/Window Sensor
        if self.config.get('door_sensor', {}).get('enabled'):
            try:
                from gpiozero import Button
                self.sensors['door_sensor'] = MagneticSensor(self.config['door_sensor'], Button)
                logger.info("✓ Magnetic door sensor initialized")
            except ImportError:
                logger.warning("gpiozero library not found")
        
        # Doorbell Button
        if self.config.get('doorbell', {}).get('enabled'):
            try:
                from gpiozero import Button
                self.sensors['doorbell'] = DoorbellSensor(self.config['doorbell'], Button)
                logger.info("✓ Doorbell initialized")
            except ImportError:
                logger.warning("gpiozero library not found")
        
        # Sound Detector
        if self.config.get('sound_detector', {}).get('enabled'):
            try:
                from gpiozero import DigitalInputDevice
                self.sensors['sound_detector'] = SoundSensor(self.config['sound_detector'], DigitalInputDevice)
                logger.info("✓ Sound detector initialized")
            except ImportError:
                logger.warning("gpiozero library not found")
        
        # DS18B20 Temperature (1-Wire)
        if self.config.get('ds18b20_temp', {}).get('enabled'):
            try:
                from w1thermsensor import W1ThermSensor
                self.sensors['ds18b20'] = DS18B20Sensor(self.config['ds18b20_temp'], W1ThermSensor)
                logger.info("✓ DS18B20 temperature sensor initialized")
            except ImportError:
                logger.warning("w1thermsensor library not found")
        
        # BME280 (Temp + Humidity + Pressure)
        if self.config.get('bme280', {}).get('enabled'):
            try:
                import board
                import adafruit_bme280
                self.sensors['bme280'] = BME280Sensor(self.config['bme280'], board, adafruit_bme280)
                logger.info("✓ BME280 sensor initialized")
            except ImportError:
                logger.warning("BME280 library not found")
    
    def read_all(self) -> Dict[str, Any]:
        """Read all sensors and return telemetry data"""
        data = {}
        
        for name, sensor in self.sensors.items():
            try:
                reading = sensor.read()
                if reading:
                    data[name] = reading
            except Exception as e:
                logger.error(f"Error reading {name}: {e}")
        
        return data
    
    def check_alerts(self, agent_id: str, topic_alerts: str):
        """Check for alert conditions and publish if needed"""
        import json
        import datetime
        
        for name, sensor in self.sensors.items():
            try:
                alert = sensor.check_alert()
                if alert:
                    # Check cooldown
                    cooldown = sensor.get_cooldown()
                    last_time = self.last_alert_times.get(name, 0)
                    
                    if time.time() - last_time >= cooldown:
                        # Publish alert
                        alert_data = {
                            "sensor": name,
                            "alert": alert,
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                        self.mqtt_client.publish(topic_alerts, json.dumps(alert_data))
                        logger.warning(f"ALERT from {name}: {alert}")
                        self.last_alert_times[name] = time.time()
            except Exception as e:
                logger.error(f"Error checking alert for {name}: {e}")

# --- SENSOR CLASSES ---

class BaseSensor:
    """Base class for all sensors"""
    def __init__(self, config: Dict):
        self.config = config
    
    def read(self) -> Optional[Dict]:
        """Read sensor data"""
        raise NotImplementedError
    
    def check_alert(self) -> Optional[str]:
        """Check for alert conditions"""
        return None
    
    def get_cooldown(self) -> int:
        """Get alert cooldown in seconds"""
        return self.config.get('alert_cooldown', 30)

class DHT22Sensor(BaseSensor):
    """DHT22 Temperature and Humidity sensor"""
    def __init__(self, config: Dict, dht_module):
        super().__init__(config)
        self.dht = dht_module
        self.sensor = dht_module.DHT22
        self.pin = config['pin']
        self.interval = config.get('read_interval', 60)
        self.last_read = 0
    
    def read(self) -> Optional[Dict]:
        if time.time() - self.last_read < self.interval:
            return None
        
        humidity, temperature = self.dht.read_retry(self.sensor, self.pin)
        self.last_read = time.time()
        
        if humidity is not None and temperature is not None:
            return {
                'temperature_c': round(temperature, 1),
                'humidity_percent': round(humidity, 1)
            }
        return None

class PIRSensor(BaseSensor):
    """PIR Motion Sensor"""
    def __init__(self, config: Dict, MotionSensor):
        super().__init__(config)
        self.pir = MotionSensor(config['pin'])
        self.motion_detected = False
        self.pir.when_motion = self._on_motion
    
    def _on_motion(self):
        self.motion_detected = True
    
    def read(self) -> Optional[Dict]:
        return {'motion': self.pir.motion}
    
    def check_alert(self) -> Optional[str]:
        if self.motion_detected:
            self.motion_detected = False
            return "Motion detected"
        return None

class MQ135Sensor(BaseSensor):
    """MQ-135 Air Quality Sensor (via I2C ADC)"""
    def __init__(self, config: Dict):
        super().__init__(config)
        self.threshold = config.get('threshold', 400)
        
        # Initialize I2C ADC (ADS1115)
        try:
            import board
            import busio
            import adafruit_ads1x15.ads1115 as ADS
            from adafruit_ads1x15.analog_in import AnalogIn
            
            i2c = busio.I2C(board.SCL, board.SDA)
            ads = ADS.ADS1115(i2c, address=int(config['address'], 16))
            self.chan = AnalogIn(ads, ADS.P0)
        except:
            logger.error("Failed to initialize MQ-135 ADC")
            self.chan = None
    
    def read(self) -> Optional[Dict]:
        if not self.chan:
            return None
        return {'air_quality_ppm': self.chan.value}
    
    def check_alert(self) -> Optional[str]:
        if self.chan and self.chan.value > self.threshold:
            return f"Poor air quality detected: {self.chan.value} ppm"
        return None

class MQ2Sensor(BaseSensor):
    """MQ-2 Smoke Detector"""
    def __init__(self, config: Dict):
        super().__init__(config)
        self.threshold = config.get('alert_threshold', 300)
        
        try:
            import board
            import busio
            import adafruit_ads1x15.ads1115 as ADS
            from adafruit_ads1x15.analog_in import AnalogIn
            
            i2c = busio.I2C(board.SCL, board.SDA)
            ads = ADS.ADS1115(i2c, address=int(config['address'], 16))
            self.chan = AnalogIn(ads, ADS.P1)
        except:
            logger.error("Failed to initialize MQ-2 ADC")
            self.chan = None
    
    def read(self) -> Optional[Dict]:
        if not self.chan:
            return None
        return {'smoke_level': self.chan.value}
    
    def check_alert(self) -> Optional[str]:
        if self.chan and self.chan.value > self.threshold:
            return f"SMOKE DETECTED: {self.chan.value}"
        return None

class BH1750Sensor(BaseSensor):
    """BH1750 Light Sensor"""
    def __init__(self, config: Dict, board_module, bh1750_module):
        super().__init__(config)
        import busio
        
        i2c = busio.I2C(board_module.SCL, board_module.SDA)
        self.sensor = bh1750_module.BH1750(i2c, address=int(config.get('i2c_address', '0x23'), 16))
        self.interval = config.get('read_interval', 60)
        self.last_read = 0
    
    def read(self) -> Optional[Dict]:
        if time.time() - self.last_read < self.interval:
            return None
        
        self.last_read = time.time()
        return {'light_lux': round(self.sensor.lux, 1)}

class MagneticSensor(BaseSensor):
    """Magnetic Door/Window Sensor"""
    def __init__(self, config: Dict, Button):
        super().__init__(config)
        self.sensor = Button(config['pin'], pull_up=True)
        self.alert_on_open = config.get('alert_on_open', True)
        self.name = config.get('name', 'Door')
        self.opened = False
        self.sensor.when_pressed = self._on_open
    
    def _on_open(self):
        self.opened = True
    
    def read(self) -> Optional[Dict]:
        return {
            'state': 'open' if self.sensor.is_pressed else 'closed',
            'name': self.name
        }
    
    def check_alert(self) -> Optional[str]:
        if self.alert_on_open and self.opened:
            self.opened = False
            return f"{self.name} opened"
        return None

class DoorbellSensor(BaseSensor):
    """Doorbell Button"""
    def __init__(self, config: Dict, Button):
        super().__init__(config)
        self.button = Button(config['pin'], pull_up=True)
        self.pressed = False
        self.message = config.get('alert_message', 'Doorbell pressed')
        self.button.when_pressed = self._on_press
    
    def _on_press(self):
        self.pressed = True
    
    def read(self) -> Optional[Dict]:
        return {'doorbell_pressed': self.button.is_pressed}
    
    def check_alert(self) -> Optional[str]:
        if self.pressed:
            self.pressed = False
            return self.message
        return None

class SoundSensor(BaseSensor):
    """Sound Detector"""
    def __init__(self, config: Dict, DigitalInputDevice):
        super().__init__(config)
        self.sensor = DigitalInputDevice(config['pin'])
        self.detected = False
        self.sensor.when_activated = self._on_sound
    
    def _on_sound(self):
        self.detected = True
    
    def read(self) -> Optional[Dict]:
        return {'sound_detected': self.sensor.is_active}
    
    def check_alert(self) -> Optional[str]:
        if self.detected:
            self.detected = False
            return "Loud sound detected"
        return None

class DS18B20Sensor(BaseSensor):
    """DS18B20 Waterproof Temperature Sensor"""
    def __init__(self, config: Dict, W1ThermSensor):
        super().__init__(config)
        device_id = config.get('device_id')
        if device_id:
            self.sensor = W1ThermSensor(sensor_id=device_id)
        else:
            self.sensor = W1ThermSensor()
        self.interval = config.get('read_interval', 60)
        self.last_read = 0
    
    def read(self) -> Optional[Dict]:
        if time.time() - self.last_read < self.interval:
            return None
        
        self.last_read = time.time()
        temp = self.sensor.get_temperature()
        return {'temperature_c': round(temp, 1)}

class BME280Sensor(BaseSensor):
    """BME280 Temperature, Humidity and Pressure Sensor"""
    def __init__(self, config: Dict, board_module, bme280_module):
        super().__init__(config)
        import busio
        
        i2c = busio.I2C(board_module.SCL, board_module.SDA)
        self.sensor = bme280_module.Adafruit_BME280_I2C(
            i2c, 
            address=int(config.get('i2c_address', '0x76'), 16)
        )
        self.interval = config.get('read_interval', 60)
        self.last_read = 0
    
    def read(self) -> Optional[Dict]:
        if time.time() - self.last_read < self.interval:
            return None
        
        self.last_read = time.time()
        return {
            'temperature_c': round(self.sensor.temperature, 1),
            'humidity_percent': round(self.sensor.humidity, 1),
            'pressure_hpa': round(self.sensor.pressure, 1)
        }
