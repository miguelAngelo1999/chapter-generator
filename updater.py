import sys
import os
import requests
import tempfile
import subprocess
import shutil
import time
from packaging.version import parse as parse_version

GITHUB_REPO = "miguelAngelo1999/chapter-generator"
INSTALLER_ASSET_NAME = "ChapterGeneratorInstaller.exe"

def get_launcher_path():
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, 'updater_launcher.exe')

def check_for_updates(current_version_str):
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        response = requests.get(api_url, timeout=10, verify=False)
        response.raise_for_status()
        latest_release = response.json()
        latest_version_str = latest_release.get("tag_name", "v0.0.0").lstrip('v')
        current_version = parse_version(current_version_str)
        latest_version = parse_version(latest_version_str)

        if latest_version > current_version:
            for asset in latest_release.get("assets", []):
                if asset["name"] == INSTALLER_ASSET_NAME:
                    return {
                        "update_available": True,
                        "latest_version": latest_version_str,
                        "download_url": asset["browser_download_url"],
                    }
            return {"update_available": False, "error": "Installer asset not found."}
        else:
            return {"update_available": False, "message": "You are on the latest version."}
    except requests.exceptions.RequestException as e:
        return {"update_available": False, "error": f"Network error: {e}"}
    except Exception as e:
        return {"update_available": False, "error": f"An unexpected error occurred: {e}"}

def download_and_run_installer(download_url):
    try:
        response = requests.get(download_url, stream=True, timeout=300, verify=False)
        response.raise_for_status()
        
        temp_dir = tempfile.gettempdir()
        installer_path = os.path.join(temp_dir, INSTALLER_ASSET_NAME)
        
        with open(installer_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        original_launcher_path = get_launcher_path()
        if not os.path.exists(original_launcher_path):
            return {"success": False, "error": "Updater launcher component (updater_launcher.exe) is missing."}

        temp_launcher_path = os.path.join(temp_dir, f"launcher_{int(time.time())}.exe")
        shutil.copy(original_launcher_path, temp_launcher_path)

        current_pid = os.getpid()
        
        command_to_run = [
            temp_launcher_path,
            installer_path,
            str(current_pid)
        ]
        
        subprocess.Popen(
            command_to_run,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True
        )
        
        return {"success": True, "message": "Update process initiated. This app will now close."}
    except Exception as e:
        return {"success": False, "error": f"Failed to download or run installer: {e}"}
