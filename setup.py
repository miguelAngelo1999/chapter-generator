#!/usr/bin/env python3
"""
Setup script for Chapter Generator
Downloads required dependencies on first run
"""

import os
import sys
import urllib.request
import zipfile
import shutil
from pathlib import Path

def download_whisper():
    """Download Purfview Whisper for Windows"""
    print("📥 Downloading Purfview Whisper...")
    
    # URL for Purfview Whisper (faster-whisper-xxl)
    whisper_url = "https://github.com/Purfview/whisper-standalone-win/releases/download/v2.0.2/whisper-standalone-win-v2.0.2.zip"
    
    try:
        # Create SSL context to handle certificate issues
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Download zip file with SSL context
        zip_path = "whisper-standalone-win.zip"
        with urllib.request.urlopen(whisper_url, context=ssl_context) as response:
            with open(zip_path, 'wb') as f:
                f.write(response.read())
        print("  ✅ Download completed")
        
        # Extract zip file
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")
        print("  ✅ Extraction completed")
        
        # Rename to expected directory name
        extracted_dir = Path("whisper-standalone-win-v2.0.2")
        if extracted_dir.exists():
            target_dir = Path("Purfview-Whisper-Faster")
            if target_dir.exists():
                shutil.rmtree(target_dir)
            extracted_dir.rename(target_dir)
            print("  ✅ Renamed to Purfview-Whisper-Faster")
        
        # Clean up zip file
        os.remove(zip_path)
        print("  ✅ Cleanup completed")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Failed to download Whisper: {e}")
        print("  💡 You can download manually from:")
        print("     https://github.com/Purfview/whisper-standalone-win/releases")
        return False

def check_whisper():
    """Check if Purfview Whisper is available"""
    whisper_dir = Path("Purfview-Whisper-Faster")
    if whisper_dir.exists():
        exe_path = whisper_dir / "faster-whisper-xxl.exe"
        if exe_path.exists():
            print("✅ Purfview Whisper is already installed")
            return True
    
    return False

def main():
    """Main setup process"""
    print("🚀 Chapter Generator Setup")
    print("=" * 40)
    
    # Check if Whisper is already installed
    if check_whisper():
        print("🎉 Setup complete! Ready to use.")
        return 0
    
    # Ask user to download Whisper
    print("⚠️  Purfview Whisper not found")
    print("📥 This is required for audio/video transcription")
    
    response = input("\nDownload Purfview Whisper now? (y/n): ").lower().strip()
    if response not in ['y', 'yes']:
        print("❌ Setup cancelled. Transcription will not work.")
        return 1
    
    # Download Whisper
    if download_whisper():
        print("\n" + "=" * 40)
        print("🎉 Setup completed successfully!")
        print("🚀 Chapter Generator is ready to use!")
        print("\n💡 You can now run Chapter-Generator.exe")
        return 0
    else:
        print("\n❌ Setup failed. Please check your internet connection.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
