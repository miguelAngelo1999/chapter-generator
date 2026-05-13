"""Chapter Generator updater - checks version and applies patch from Google Drive"""
import sys
import os
import ssl
import urllib3
import warnings
import requests
import tempfile
import zipfile
import shutil
import time
from packaging.version import parse as parse_version

# SSL bypass + proxy
os.environ.update({
    'PYTHONHTTPSVERIFY': '0',
    'HTTP_PROXY': 'http://127.0.0.1:1090',
    'HTTPS_PROXY': 'http://127.0.0.1:1090',
})
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings()
_orig_request = requests.Session.request
def _patched_request(self, method, url, **kwargs):
    kwargs['verify'] = False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _orig_request(self, method, url, **kwargs)
requests.Session.request = _patched_request

VERSION_FILE_ID   = "1D9MMV-z6EjX8D6M9dHl44_JHlMaxtBNT"
INSTALLER_FILE_ID = "15NLsYpfRhxBVyiZ_lZmy1gxAcdY5qf7d"


def get_install_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def gdrive_download(file_id, destination):
    import re
    session = requests.Session()
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    resp = session.get(url, stream=True, verify=False)
    if 'text/html' in resp.headers.get('Content-Type', ''):
        html = resp.text
        action_match = re.search(r'action="([^"]+)"', html)
        if action_match:
            action = action_match.group(1).replace('&amp;', '&')
            inputs = re.findall(r'<input[^>]*name="([^"]*)"[^>]*value="([^"]*)"', html)
            params = {name: val for name, val in inputs}
            resp = session.get(action, params=params, stream=True, verify=False)
    with open(destination, 'wb') as f:
        for chunk in resp.iter_content(32768):
            if chunk:
                f.write(chunk)


def check_for_updates(current_version_str):
    try:
        url = f"https://drive.google.com/uc?export=download&id={VERSION_FILE_ID}"
        resp = requests.get(url, timeout=10, verify=False)
        latest_str = resp.text.strip()
        if latest_str.startswith('<'):
            return {"update_available": False, "error": "Could not read version from server"}
        current = parse_version(current_version_str)
        latest = parse_version(latest_str)
        if latest > current:
            return {
                "update_available": True,
                "latest_version": latest_str,
                "download_url": f"gdrive:{INSTALLER_FILE_ID}",
            }
        return {"update_available": False, "message": "You are on the latest version."}
    except Exception as e:
        return {"update_available": False, "error": f"Update check failed: {e}"}


def download_and_apply_update(download_url, new_version):
    """Download patch zip and hot-swap app files. No restart needed."""
    try:
        if download_url.startswith('gdrive:'):
            file_id = download_url.replace('gdrive:', '')
        else:
            return {"success": False, "error": "Invalid download URL"}

        temp_dir = os.environ.get('TEMP') or os.environ.get('TMP') or tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, f"ChapterGenPatch_{int(time.time())}.zip")

        gdrive_download(file_id, zip_path)

        if not os.path.exists(zip_path) or os.path.getsize(zip_path) < 1000:
            return {"success": False, "error": "Download failed or file too small"}

        install_dir = get_install_dir()

        # Extract patch files over existing install
        with zipfile.ZipFile(zip_path, 'r') as zf:
            members = zf.namelist()
            for member in members:
                dest = os.path.join(install_dir, member.replace('/', os.sep))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                try:
                    with zf.open(member) as src, open(dest, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                except PermissionError:
                    # Skip locked files (e.g. running exe) — they'll update on next restart
                    pass

        os.remove(zip_path)

        # Write new version
        import json
        version_file = os.path.join(install_dir, 'version.json')
        info = {"version": new_version, "major": int(new_version.split('.')[0])}
        with open(version_file, 'w') as f:
            json.dump(info, f)

        return {"success": True, "message": f"Updated to v{new_version}. Restart the app to apply."}
    except Exception as e:
        return {"success": False, "error": f"Update failed: {e}"}
