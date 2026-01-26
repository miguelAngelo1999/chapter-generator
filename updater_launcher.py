import sys
import os
import time
import psutil
import subprocess
from pathlib import Path

LOG_FILE = Path.home() / "Desktop" / "updater_launcher_log.txt"
INSTALLER_PASSWORD = "123"

def write_log(message):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")
    except Exception:
        pass

def main():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    write_log("Launcher started in 'wait' mode.")
    
    current_pid = os.getpid()
    write_log(f"Current launcher PID is {current_pid}.")

    write_log("Searching for other launcher processes...")
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] and proc.info['name'].startswith('launcher_') and proc.pid != current_pid:
            try:
                write_log(f"Found and terminating old launcher process: PID {proc.pid}")
                psutil.Process(proc.pid).terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    write_log("Old launcher cleanup complete.")
    time.sleep(1)
    
    try:
        if len(sys.argv) < 3:
            write_log("FATAL ERROR: Not enough arguments. Expected: installer_path, parent_pid")
            return

        installer_path = sys.argv[1]
        parent_pid = int(sys.argv[2])

        write_log(f"Installer path: {installer_path}")
        write_log(f"Parent PID to wait for: {parent_pid}")

        timeout = 15
        start_time = time.time()
        write_log(f"Waiting for parent process PID {parent_pid} to exit...")
        while psutil.pid_exists(parent_pid):
            time.sleep(0.5)
            if time.time() - start_time > timeout:
                write_log(f"FATAL ERROR: Timeout waiting for parent PID {parent_pid} to exit.")
                return
        write_log("Parent process PID has disappeared.")

        wait_duration = 10
        write_log(f"Now performing a simple, fixed wait of {wait_duration} seconds for all file locks to clear...")
        time.sleep(wait_duration)
        write_log("Wait finished. Proceeding to launch installer.")

        if os.path.exists(installer_path):
            try:
                subprocess.Popen([installer_path, f"-p{INSTALLER_PASSWORD}"], creationflags=subprocess.DETACHED_PROCESS)
                write_log("SUCCESS: Installer launched.")
            except Exception as e:
                write_log(f"FATAL ERROR: Launching installer failed: {e}")
        else:
            write_log(f"FATAL ERROR: Installer not found at '{installer_path}'.")

    except Exception as e:
        write_log(f"FATAL UNHANDLED ERROR in launcher: {e}")
    
    write_log("Launcher finished.")

if __name__ == "__main__":
    main()
