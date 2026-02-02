import os
import sys
import platform
import shutil

def install_mac(agent_path):
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.healthsec.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{agent_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
"""
    dest = os.path.expanduser("~/Library/LaunchAgents/com.healthsec.agent.plist")
    with open(dest, "w") as f:
        f.write(plist)
    
    print(f"Created LaunchAgent at {dest}")
    print("To load now: launchctl load " + dest)

def install_linux(agent_path):
    # Simplified service file
    service = f"""[Unit]
Description=HealthSec Agent
After=network.target

[Service]
ExecStart={sys.executable} {agent_path}
Restart=always
User={os.getlogin()}

[Install]
WantedBy=multi-user.target
"""
    print("--- Create a file at /etc/systemd/system/healthsec.service with: ---")
    print(service)
    print("-------------------------------------------------------------------")
    print("Then run: sudo systemctl enable healthsec && sudo systemctl start healthsec")

def install_windows(agent_path):
    print("For Windows, adding to Registry Run key via PowerShell...")
    cmd = f'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v HealthSecAgent /t REG_SZ /d "{sys.executable} {agent_path}" /f'
    os.system(cmd)
    print("Added to startup registry.")

def main():
    agent_path = os.path.abspath("agent.py")
    system = platform.system().lower()
    
    print(f"Installing agent from {agent_path} for {system}...")
    
    if "darwin" in system:
        install_mac(agent_path)
    elif "linux" in system:
        install_linux(agent_path)
    elif "windows" in system:
        install_windows(agent_path)
    else:
        print("Unknown OS")

if __name__ == "__main__":
    main()
