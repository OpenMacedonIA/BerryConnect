# Network Bros (Mini TIOs) - Agentes Satélite

Este directorio contiene el código y las instrucciones para desplegar "Network Bros", pequeños agentes satélite que extienden los sentidos de TIO por toda la casa u oficina.

## Arquitectura

El sistema utiliza **MQTT** para la comunicación. TIO (el servidor central) debe tener un broker MQTT corriendo (como Mosquitto). Los agentes publican telemetría y alertas en topics específicos.

### Estructura de Topics
- `tio/agents/{id}/telemetry`: Datos periódicos (temp, cpu, ram).
- `tio/agents/{id}/alerts`: Eventos críticos (intruso detectado, caída).

## Requisitos Previos (Servidor Central)

1.  Instalar Mosquitto en la Raspberry Pi principal (donde corre TIO):
    ```bash
    sudo apt update
    sudo apt install mosquitto mosquitto-clients
    sudo systemctl enable mosquitto
    sudo systemctl start mosquitto
    ```

---

## 1. Despliegue en Raspberry Pi Zero (Python)

Ideal para monitorización de red avanzada (NetAlertX) o habitaciones secundarias.

### Hardware
- Raspberry Pi Zero W / 2 / 3 / 4.
- Tarjeta SD con Raspberry Pi OS Lite.

### Instalación

1.  Copiar la carpeta `PiZero` a la Raspberry Pi satélite.
2.  Instalar dependencias:
    ```bash
    sudo apt install python3-pip
    pip3 install paho-mqtt psutil
    ```
3.  Editar `agent.py`:
    - Cambiar `BROKER_ADDRESS` por la IP de tu servidor TIO principal.
4.  Ejecutar:
    ```bash
    python3 agent.py
    ```
5.  (Opcional) Crear servicio systemd para arranque automático.

---

## 2. Despliegue en ESP32 (MicroPython)

Ideal para sensores de bajo consumo (Temperatura, Humedad, Movimiento).

### Hardware
- Placa ESP32 (DevKit V1 o similar).
- Sensor DHT22 (conectado a GPIO 15).

### Instalación

1.  **Flashear MicroPython**:
    - Descargar firmware desde [micropython.org](https://micropython.org/download/esp32/).
    - Usar `esptool.py` para borrar y flashear:
      ```bash
      esptool.py --chip esp32 erase_flash
      esptool.py --chip esp32 --baud 460800 write_flash -z 0x1000 esp32-xxxx.bin
      ```
2.  **Subir Código**:
    - Editar `main.py` con tu `WIFI_SSID`, `WIFI_PASS` y `BROKER_ADDRESS`.
    - Usar una herramienta como `ampy` o Thonny IDE para subir `boot.py` y `main.py` a la placa.
    - Necesitarás la librería `umqtt.simple`. Si no viene incluida, descárgala de [micropython-lib](https://github.com/micropython/micropython-lib).

---

## Integración con TIO (Futuro)

Para que TIO reaccione a estos mensajes, se debe implementar un cliente MQTT en `NeoCore.py` que se suscriba a `tio/agents/#` y procese los mensajes entrantes, guardándolos en la base de datos o lanzando alertas de voz.
