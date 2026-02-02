import requests
import json
import time
import uuid
import socket
import threading
import sys
import os
import websocket
import subprocess
import platform
import cv2
import base64
import numpy as np
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

SERVER_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"
CONFIG_FILE = "agent_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return None

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def get_system_info():
    hostname = socket.gethostname()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        s.close()
    except:
        ip_address = "127.0.0.1"
    return hostname, ip_address

def get_mac_address():
    mac = uuid.getnode()
    return ':'.join(('%012X' % mac)[i:i+2] for i in range(0, 12, 2))

def register_agent(agent_id, hostname, ip):
    url = f"{SERVER_URL}/register"
    data = {
        "id": agent_id,
        "hostname": hostname,
        "ip_address": ip,
        "mac_address": get_mac_address()
    }
    try:
        response = requests.post(url, json=data)
        if response.status_code == 200:
            print(f"Registered as {agent_id}")
            return True
        return False
    except Exception as e:
        print(f"Registration error: {e}")
        return False

def send_heartbeat(agent_id):
    url = f"{SERVER_URL}/heartbeat"
    data = {"id": agent_id, "status": "online"}
    try:
        requests.post(url, json=data)
    except:
        pass

def send_log(agent_id, level, content):
    url = f"{SERVER_URL}/logs?agent_id={agent_id}"
    data = {"level": level, "content": content}
    try:
        requests.post(url, json=data)
    except Exception as e:
        print(f"Error sending log: {e}")

# --- Command Handling ---

def execute_shutdown(agent_id):
    print("Received SHUTDOWN command...")
    
    # Notify server we are going offline
    send_log(agent_id, "WARNING", "System shutting down via remote command...")
    
    url = f"{SERVER_URL}/heartbeat"
    data = {"id": agent_id, "status": "offline"}
    try:
        requests.post(url, json=data)
    except:
        pass

    # Give some time to log the action
    time.sleep(2)
    system_platform = platform.system().lower()
    
    if "windows" in system_platform:
        subprocess.call(["shutdown", "/s", "/t", "5"])
    elif "linux" in system_platform or "darwin" in system_platform:
        # Requires sudo usually, or properly configured permissions
        subprocess.call(["sudo", "shutdown", "-h", "now"])
    else:
        print("Shutdown not supported on this OS.")

def on_ws_message(ws, message, agent_id):
    # Format: command:agent_id:command_name
    parts = message.split(":")
    if len(parts) >= 3 and parts[0] == "command" and parts[1] == agent_id:
        cmd = parts[2]
        if cmd == "shutdown":
            execute_shutdown(agent_id)

def on_ws_error(ws, error):
    print(f"WebSocket Error: {error}")

def on_ws_close(ws, close_status_code, close_msg):
    print("WebSocket Closed. Reconnecting in 5s...")
    time.sleep(5)
    start_ws_listener(ws.agent_id) # Recursive reconnect

def on_ws_open(ws):
    print("Connected to Command Channel")

def start_ws_listener(agent_id):
    # websocket.enableTrace(True)
    ws = websocket.WebSocketApp(WS_URL,
                              on_open=on_ws_open,
                              on_message=lambda ws, msg: on_ws_message(ws, msg, agent_id),
                              on_error=on_ws_error,
                              on_close=on_ws_close)
    ws.agent_id = agent_id
    ws.run_forever()

# --- Real Log Reading ---

def follow_file(filename):
    file = open(filename, "r")
    file.seek(0, 2) # Go to end
    while True:
        line = file.readline()
        if not line:
            time.sleep(0.1)
            continue
        yield line

def log_monitor(agent_id):
    system_platform = platform.system().lower()
    print(f"Starting Log Monitor for {system_platform}...")

    if "darwin" in system_platform: # MacOS
        # /var/log/system.log is standard, but often requires admin. 
        # Using a simpler user-accessible log or ensuring script runs with sudo
        log_file = "/var/log/system.log"
        if not os.path.exists(log_file):
            print(f"Log file {log_file} not found. Sending test logs instead.")
            return # Or fallback
            
        try:
            for line in follow_file(log_file):
                if "error" in line.lower() or "fail" in line.lower():
                    send_log(agent_id, "ERROR", line.strip())
                else:
                    # Optional: Don't send everything to avoid spam, or send DEBUG/INFO
                    pass 
        except PermissionError:
             send_log(agent_id, "ERROR", "Agent permission denied reading /var/log/system.log")

    elif "linux" in system_platform:
        log_file = "/var/log/syslog"
        # Similar logic to Mac
        try:
            for line in follow_file(log_file):
                if "error" in line.lower():
                    send_log(agent_id, "ERROR", line.strip())
        except Exception as e:
            print(f"Log monitor error: {e}")

    elif "windows" in system_platform:
        # Use PowerShell to tail event log
        cmd = 'Get-EventLog -LogName System -Newest 1 | Select-Object -ExpandProperty Message'
        last_message = ""
        while True:
            try:
                # Polling approach for Windows MVP
                result = subprocess.check_output(["powershell", "/c", cmd], text=True).strip()
                if result != last_message and result:
                    last_message = result
                    send_log(agent_id, "INFO", result) # Just sending latest system event
                time.sleep(5)
            except Exception as e:
                print(f"Windows Log Error: {e}")
                time.sleep(10)

class LogHandler(FileSystemEventHandler):
    def __init__(self, agent_id):
        self.agent_id = agent_id

    def on_deleted(self, event):
        what = 'directory' if event.is_directory else 'file'
        msg = f"Deleted {what}: {event.src_path}"
        print(f"[Watchdog] {msg}")
        send_log(self.agent_id, "WARNING", msg)

    def on_created(self, event):
        what = 'directory' if event.is_directory else 'file'
        # Filter temp files
        if "~" in event.src_path or ".tmp" in event.src_path:
            return
        msg = f"Created {what}: {event.src_path}"
        # send_log(self.agent_id, "INFO", msg) # Too noisy?

class CameraCapture:
    def __init__(self, agent_id, ws_url):
        self.agent_id = agent_id
        self.ws_url = ws_url
        self.running = False
        self.cap = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _capture_loop(self):
        print("Starting Webcam Capture...")
        # Try index 0, then 1
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
             self.cap = cv2.VideoCapture(1)
             
        if not self.cap.isOpened():
            send_log(self.agent_id, "ERROR", "Webcam could not be opened.")
            print("Webcam could not be opened.")
            return

        send_log(self.agent_id, "INFO", "Webcam started successfully.")
        print("Webcam started.")
        
        # We need a NEW WebSocket connection for video, or reuse the command one?
        # The command one waits for messages. 
        # For simplicity, we'll open a dedicated connection or send on the same one if we could access it.
        # But `start_ws_listener` does `ws.run_forever()`.
        # So we should create a separate connection for streaming or modify the architecture.
        # For now, separate connection is easier.
        
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(1)
                continue
                
            # Resize to reduce bandwidth
            frame = cv2.resize(frame, (640, 480))
            
            # Encode
            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            
            # Send via requests? No, too slow.
            # We need to broadcast via WebSocket.
            # Let's open a transient WS or maintain one.
            try:
                # Re-opening valid WS for every frame is bad, but `websocket-client` 
                # doesn't make it easy to share without a class wrapper.
                # Let's iterate: Connect once.
                pass 
            except:
                pass
                
        self.cap.release()

    def start_stream(self):
        # Improved loop with persistent connection
        ws = None
        while self.running:
             try:
                 if not ws or not ws.connected:
                     ws = websocket.create_connection(self.ws_url)
                 
                 ret, frame = self.cap.read()
                 if not ret:
                     time.sleep(0.1)
                     continue
                     
                 frame = cv2.resize(frame, (320, 240)) # Smaller for speed
                 _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 40])
                 jpg_as_text = base64.b64encode(buffer).decode('utf-8')
                 
                 # Prepare payload
                 payload = json.dumps({
                     "type": "video",
                     "agent_id": self.agent_id,
                     "data": jpg_as_text
                 })
                 ws.send(payload)
                 time.sleep(0.1) # 10 FPS
             except Exception as e:
                 # print(f"Stream error: {e}")
                 if ws:
                     try:
                        ws.close()
                     except:
                        pass
                     ws = None
                 time.sleep(2)

def start_file_monitor(agent_id):
    if not HAS_WATCHDOG:
        print("Watchdog not installed. Skipping file monitoring.")
        return

    path_to_watch = os.path.expanduser("~")
    if platform.system().lower() == "windows":
        path_to_watch = os.path.expanduser("~\\Documents") 
    
    print(f"Starting File Monitor on: {path_to_watch}")
    
    event_handler = LogHandler(agent_id)
    observer = Observer()
    observer.schedule(event_handler, path_to_watch, recursive=False) # Recursive is expensive
    observer.start()

def main():
    global SERVER_URL, WS_URL
    config = load_config()
    
    # Allow overriding Server URL from config
    if config and "server_url" in config:
        SERVER_URL = config["server_url"]
        # Derive WS URL from HTTP URL
        WS_URL = SERVER_URL.replace("http", "ws") + "/ws"
        print(f"Using Server URL: {SERVER_URL}")

    if not config or "id" not in config:
        print("Initializing new agent...")
        # If no config, ask for Server URL if not default
        if not config:
            user_url = input(f"Enter Server URL [{SERVER_URL}]: ").strip()
            if user_url:
                if not user_url.startswith("http"):
                    user_url = "http://" + user_url
                SERVER_URL = user_url
                WS_URL = SERVER_URL.replace("http", "ws", 1) + "/ws"

        agent_id = str(uuid.uuid4())
        hostname, ip = get_system_info()
        config = {
            "id": agent_id, 
            "hostname": hostname, 
            "ip": ip, 
            "server_url": SERVER_URL
        }
        
        if register_agent(agent_id, hostname, ip):
            save_config(config)
        else:
            print("Registration failed. Check Server URL and try again.")
            sys.exit(1)
    else:
        agent_id = config["id"]
        hostname = config["hostname"]
        ip = config["ip"]
        register_agent(agent_id, hostname, ip)

    print(f"Agent {agent_id} running on {hostname}")

    # Heartbeat
    hb_thread = threading.Thread(target=lambda: [send_heartbeat(agent_id) or time.sleep(5) for _ in iter(int, 1)], daemon=True)
    hb_thread.start()

    # WebSocket Command Listener
    ws_thread = threading.Thread(target=start_ws_listener, args=(agent_id,), daemon=True)
    ws_thread.start()

    # Real Log Monitor
    log_thread = threading.Thread(target=log_monitor, args=(agent_id,), daemon=True)
    log_thread.start()

    # File Monitor (Watchdog)
    start_file_monitor(agent_id)

    # Webcam
    cam = CameraCapture(agent_id, WS_URL)
    # Monkey patch start to use start_stream for now, or just call it directly if I fixed the class
    # The class has start_stream, let's use it.
    cam.running = True
    cam.cap = cv2.VideoCapture(0)
    if not cam.cap.isOpened():
         cam.cap = cv2.VideoCapture(1)
    
    if cam.cap.isOpened():
        send_log(agent_id, "INFO", "Webcam started.")
        cam.thread = threading.Thread(target=cam.start_stream, daemon=True)
        cam.thread.start()
    else:
        send_log(agent_id, "ERROR", "Webcam failed to start.")

    # Keep alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping agent...")

if __name__ == "__main__":
    main()
