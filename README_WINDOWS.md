# Guia de Instalación para Windows (HealthSec Agent)

Si subes este código a GitHub, sigue estos pasos para instalarlo en una PC con Windows.

## Prerrequisitos
1. **Python**: Descarga e instala Python (asegúrate de marcar "Add Python to PATH" durante la instalación).
   - [Descargar Python](https://www.python.org/downloads/)
2. **Acceso a Internet**: La PC debe poder ver al servidor (ya sea en red local o internet).

## Pasos de Instalación

1. **Descargar el Agente**:

2. **Abrir PowerShell (como Administrador)**:
   Haz clic derecho en el botón de Inicio y selecciona **Windows PowerShell (Administrador)** o **Terminal (Admin)**.

3. **Navegar a la carpeta**:
   ```powershell
   cd C:\Ruta\Donde\Descargaste\client-agent
   ```

4. **Instalar Dependencias**:
   ```powershell
   pip install -r requirements.txt
   ```

5. **Configuración Inicial**:
   Ejecuta el agente por primera vez para configurarlo.
   ```powershell
   python agent.py
   ```
   - Te pedirá la **URL del Servidor**.
   - Si el servidor está en la misma red, pon su IP local, ej: `http://192.168.1.50:8000`.
   - Si el servidor está en internet (VPS, Render, etc), pon su dominio, ej: `https://mi-healthsec.com`.
   - El agente intentará registrarse. Si funciona, guardará la configuración en `agent_config.json`.
   - Presiona `q` para salir.

6. **Instalar Auto-arranque**:
   Para que el agente se inicie solo cuando prendes la PC:
   ```powershell
   python install.py
   ```
   Esto agregará el script al registro de inicio de Windows.

## Verificación
1. Reinicia la PC.
2. El agente debería iniciarse automáticamente en segundo plano.
3. Ve a tu **Panel de Administrador** y deberías ver la PC "Online".
