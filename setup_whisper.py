#!/usr/bin/env python3

import os
import sys
import platform
import subprocess
import urllib.request
import zipfile
import tarfile
import shutil
from pathlib import Path

def run_command(cmd, shell=False):
    """Run command and return success status"""
    try:
        result = subprocess.run(cmd, shell=shell, check=True, capture_output=True, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def install_whisper_cpp():
    """Install whisper.cpp"""
    system = platform.system()
    
    if system == "Darwin":  # macOS
        print("Installing whisper.cpp via Homebrew...")
        success, output = run_command(["brew", "install", "whisper-cpp"])
        if success:
            print("✓ whisper.cpp installed successfully")
            return True
        else:
            print(f"✗ Failed to install whisper.cpp: {output}")
            return False
            
    elif system == "Windows":
        print("Installing whisper.cpp for Windows...")
        # Download precompiled binary
        url = "https://github.com/ggerganov/whisper.cpp/releases/latest/download/whisper-bin-Win32.zip"
        zip_path = "whisper-cpp.zip"
        
        try:
            print("Downloading whisper.cpp...")
            urllib.request.urlretrieve(url, zip_path)
            
            # Extract to local directory
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall("whisper-cpp")
            
            os.remove(zip_path)
            print("✓ whisper.cpp installed successfully")
            return True
        except Exception as e:
            print(f"✗ Failed to install whisper.cpp: {e}")
            return False
    
    else:  # Linux
        print("Installing whisper.cpp for Linux...")
        # Build from source
        try:
            run_command(["git", "clone", "https://github.com/ggerganov/whisper.cpp.git"])
            os.chdir("whisper.cpp")
            run_command(["make"])
            print("✓ whisper.cpp built successfully")
            return True
        except Exception as e:
            print(f"✗ Failed to build whisper.cpp: {e}")
            return False

def check_rtx_50xx():
    """Check if RTX 50xx series GPU is present"""
    try:
        import subprocess
        result = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], 
                              capture_output=True, text=True, check=True)
        gpu_names = result.stdout.strip().split('\n')
        return any('RTX 50' in gpu for gpu in gpu_names)
    except:
        return False

def install_faster_whisper():
    """Install faster-whisper with RTX 50xx compatibility"""
    system = platform.system()
    
    # Check for RTX 50xx series
    has_rtx_50xx = check_rtx_50xx()
    
    if has_rtx_50xx:
        print("RTX 50xx series detected - installing latest CTranslate2...")
        # Install latest CTranslate2 first for RTX 50xx support
        success, output = run_command([sys.executable, "-m", "pip", "install", "--upgrade", "ctranslate2>=4.0.0"])
        if not success:
            print(f"Warning: Could not upgrade CTranslate2: {output}")
    
    if system == "Windows":
        print("Installing faster-whisper for Windows...")
        success, output = run_command([sys.executable, "-m", "pip", "install", "faster-whisper>=1.0.0"])
    else:
        print("Installing faster-whisper...")
        success, output = run_command([sys.executable, "-m", "pip", "install", "faster-whisper>=1.0.0"])
    
    if success:
        print("✓ faster-whisper installed successfully")
        if has_rtx_50xx:
            print("✓ RTX 50xx compatibility enabled")
        return True
    else:
        print(f"✗ Failed to install faster-whisper: {output}")
        return False

def download_whisper_model(model_size="medium"):
    """Download whisper model"""
    system = platform.system()
    
    if system == "Darwin" and shutil.which("whisper-cpp-download-ggml-model"):
        print(f"Downloading {model_size} model for whisper.cpp...")
        success, output = run_command(["whisper-cpp-download-ggml-model", model_size])
        if success:
            print(f"✓ {model_size} model downloaded")
        else:
            print(f"✗ Failed to download model: {output}")
    else:
        print("Model will be downloaded automatically on first use")

def main():
    print("Whisper Auto-Installer")
    print("=" * 30)
    
    system = platform.system()
    print(f"Detected OS: {system}")
    
    # Try to install whisper.cpp first (fastest)
    whisper_cpp_success = install_whisper_cpp()
    
    # Install faster-whisper as backup
    faster_whisper_success = install_faster_whisper()
    
    if whisper_cpp_success:
        download_whisper_model()
    
    print("\nInstallation Summary:")
    print(f"whisper.cpp: {'✓' if whisper_cpp_success else '✗'}")
    print(f"faster-whisper: {'✓' if faster_whisper_success else '✗'}")
    
    if whisper_cpp_success or faster_whisper_success:
        print("\n✓ At least one Whisper backend installed successfully!")
    else:
        print("\n✗ No Whisper backends could be installed")
        sys.exit(1)

if __name__ == "__main__":
    main()