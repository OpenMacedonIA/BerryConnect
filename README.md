# Network Bros (Mini TIOs) - Agentes Satélite

Este directorio contiene el código y las instrucciones para desplegar "Network Bros", pequeños agentes satélite que extienden los sentidos de TIO por toda la casa u oficina.

> **✨ NUEVO:** El sistema ahora está completamente automatizado. No necesitas editar código manualmente.

## Arquitectura

El sistema utiliza **MQTT** para la comunicación. TIO (el servidor central) debe tener un broker MQTT corriendo (como Mosquitto). Los agentes publican telemetría y alertas en topics específicos.

### Estructura de Topics
- `tio/agents/{id}/telemetry`: Datos periódicos (temp, cpu, ram).
- `tio/agents/{id}/alerts`: Eventos críticos (intruso detectado, caída).

## Requisitos Previos (Servidor Central)

El instalador principal de WatermelonD (`install.sh`) ya configura automáticamente:
1. Mosquitto MQTT broker
2. Configuración de servicios
3. Interfaz web de gestión

Si instalaste WatermelonD correctamente, no necesitas configurar nada más en el servidor.

---

## Instalación de Agentes Satélite

### Método 1: Instalador Automático (Recomendado)

1. **Desde la Interfaz Web:**
   - Accede a `http://tu-servidor:5000/agents`
   - Haz clic en "Generate Installer Script"
   - Se descargará un script preconfigurado con la IP del broker

2. **Copia el directorio completo a la Raspberry Pi satélite:**
   ```bash
   scp -r modules/BerryConnect/PiZero pi@raspberry-satellite:~/
   # Tambien puedes copiarlo de manera manual o con otro metodo
   ```

3. **Copia el instalador generado (opcional, si usas el generico):**
   ```bash
   scp berry_install_*.sh pi@raspberry-satellite:~/PiZero/
   ```

4. **Ejecuta en la Raspberry Pi satélite:**
   ```bash
   cd ~/PiZero
   chmod +x install.sh
   ./install.sh
   ```

El instalador:
- ✅ Detecta automáticamente el broker MQTT (o pregunta si falla)
- ✅ Instala dependencias
- ✅ Crea configuración automática
- ✅ Configura servicio systemd
- ✅ Inicia el agente automáticamente

### Método 2: Configuración Manual

Si el auto-descubrimiento falla, puedes crear `config.json` manualmente:

1. Copiar el directorio `PiZero` a la Raspberry Pi satélite
2. Crear `config.json`:
```json
{
  "broker_address": "192.168.1.100",
  "broker_port": 1883,
  "agent_id": "AUTO",
  "telemetry_interval": 10,
  "log_level": "INFO"
}
```
3. Ejecutar `./install.sh`

---

## Despliegue en ESP32 (MicroPython)

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

## Gestión desde la Interfaz Web

Accede a `http://tu-servidor:5000/agents` para:

- Ver agentes conectados en tiempo real
- Monitorizar telemetría (CPU, RAM, temperatura)
- Revisar alertas
- Generar scripts de instalación personalizados
- Eliminar agentes registrados

Los agentes aparecen automáticamente cuando se conectan. No requiere configuración adicional.

---

## Comandos Útiles

```bash
# Ver estado del agente
systemctl --user status berry_agent

# Ver logs en tiempo real
journalctl --user -u berry_agent -f

# Reiniciar agente
systemctl --user restart berry_agent

# Detener agente
systemctl --user stop berry_agent

# Editar configuración
nano ~/PiZero/config.json
# Luego reiniciar el servicio
systemctl --user restart berry_agent
```

---

## Configuración Avanzada

El archivo `config.json` soporta las siguientes opciones:

```json
{
  "broker_address": "192.168.1.100",  // IP del broker MQTT
  "broker_port": 1883,                 // Puerto del broker
  "agent_id": "AUTO",                  // Hostname automático o ID personalizado
  "telemetry_interval": 10,            // Intervalo de telemetría (segundos)
  "log_level": "INFO"                  // DEBUG, INFO, WARNING, ERROR
}
```

### Auto-descubrimiento

Configura `"broker_address": "AUTO"` para que el agente busque automáticamente el broker en la red mediante mDNS/Avahi.

---

## Solución de Problemas

### El agente no se conecta

1. Verifica que Mosquitto esté corriendo en el servidor:
   ```bash
   sudo systemctl status mosquitto
   ```

2. Verifica la conectividad de red:
   ```bash
   ping <IP_del_broker>
   telnet <IP_del_broker> 1883
   ```

3. Revisa los logs del agente:
   ```bash
   journalctl --user -u berry_agent -n 50
   ```

### Auto-descubrimiento falla

Si el auto-descubrimiento no funciona:
- Asegúrate de que Avahi está instalado: `sudo apt install avahi-utils`
- Configura manualmente la IP en `config.json`
- Verifica que estén en la misma red local

---

## Seguridad

Por defecto, MQTT no tiene autenticación. Para entornos de producción:

1. Configura autenticación en Mosquitto
2. Añade usuarios y contraseñas  
3. Considera usar TLS/SSL para comunicación cifrada

Consulta la documentación de Mosquitto para más detalles.
