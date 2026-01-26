#!/usr/bin/env python3
"""
Chapter Generator Build Script
Automates PyInstaller build and Purfview Whisper setup
"""

import os
import sys
import shutil
import subprocess
import time

def run_command(cmd, cwd=None):
    """Run a command and handle errors"""
    try:
        print(f"Running: {cmd}")
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: Command failed with return code {result.returncode}")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            return False
        print(f"Success: {cmd}")
        return True
    except Exception as e:
        print(f"Error running command: {e}")
        return False

def kill_existing_processes():
    """Kill any existing Chapter Generator processes"""
    print("Killing existing Chapter Generator processes...")
    try:
        # Try to kill onefile executable
        subprocess.run("taskkill /F /IM Chapter-Generator.exe", shell=True, capture_output=True)
        time.sleep(2)
        # Try to kill onedir executable
        subprocess.run("taskkill /F /IM Chapter-Generator-Fixed.exe", shell=True, capture_output=True)
        time.sleep(2)
    except:
        pass

def clean_dist_directory():
    """Clean the dist directory"""
    print("Cleaning dist directory...")
    dist_dir = os.path.join(os.getcwd(), "dist")
    if os.path.exists(dist_dir):
        try:
            shutil.rmtree(dist_dir)
            print(f"Removed: {dist_dir}")
        except Exception as e:
            print(f"Warning: Could not remove {dist_dir}: {e}")
            print("Trying to remove individual directories...")
            for item in os.listdir(dist_dir):
                item_path = os.path.join(dist_dir, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                    print(f"Removed: {item_path}")
                except Exception as e2:
                    print(f"Could not remove {item_path}: {e2}")

def build_onedir():
    """Build the onedir executable"""
    print("Building onedir executable...")
    cmd = (
        'python -m PyInstaller '
        '--name=Chapter-Generator-Fixed '
        '--windowed '
        '--onedir '
        '--add-data="templates;templates" '
        '--add-data="setup.py;setup.py" '
        '-y '
        'chapter_generator.py'
    )
    
    if not run_command(cmd):
        print("Build failed!")
        return False
    
    return True

def copy_purfview():
    """Copy Purfview Whisper directory to the build"""
    print("Copying Purfview Whisper...")
    
    source_dir = os.path.join(os.getcwd(), "Purfview-Whisper-Faster")
    target_dir = os.path.join(os.getcwd(), "dist", "Chapter-Generator-Fixed", "Purfview-Whisper-Faster")
    
    if not os.path.exists(source_dir):
        print(f"Error: Source directory not found: {source_dir}")
        return False
    
    try:
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        
        shutil.copytree(source_dir, target_dir)
        print(f"Copied Purfview from {source_dir} to {target_dir}")
        return True
    except Exception as e:
        print(f"Error copying Purfview: {e}")
        return False

def create_launcher():
    """Create a simple launcher script"""
    print("Creating launcher script...")
    
    launcher_content = """@echo off
cd /d "%~dp0"
echo Starting Chapter Generator...
Chapter-Generator-Fixed.exe
pause
"""
    
    launcher_path = os.path.join(os.getcwd(), "dist", "Chapter-Generator-Fixed", "Start.bat")
    
    try:
        with open(launcher_path, 'w') as f:
            f.write(launcher_content)
        print(f"Created launcher: {launcher_path}")
        return True
    except Exception as e:
        print(f"Error creating launcher: {e}")
        return False

def show_build_info():
    """Show build completion information"""
    print("\n" + "="*60)
    print("BUILD COMPLETED SUCCESSFULLY!")
    print("="*60)
    
    build_dir = os.path.join(os.getcwd(), "dist", "Chapter-Generator-Fixed")
    executable = os.path.join(build_dir, "Chapter-Generator-Fixed.exe")
    launcher = os.path.join(build_dir, "Start.bat")
    
    print(f"Build Directory: {build_dir}")
    print(f"Executable: {executable}")
    print(f"Launcher: {launcher}")
    
    if os.path.exists(executable):
        size_mb = os.path.getsize(executable) / (1024 * 1024)
        print(f"Executable Size: {size_mb:.1f} MB")
    
    purfview_dir = os.path.join(build_dir, "Purfview-Whisper-Faster")
    if os.path.exists(purfview_dir):
        print(f"Purfview Directory: {purfview_dir}")
    
    print("\nTo run the application:")
    print("1. Double-click: Chapter-Generator-Fixed.exe")
    print("2. Or run: Start.bat")
    print("3. Web interface will open at: http://127.0.0.1:5000")
    
    print("\nFeatures included:")
    print("✅ Simplified pipeline (Video → SRT → Chapters)")
    print("✅ Purfview Whisper transcription")
    print("✅ LLM-powered chapter generation")
    print("✅ SRT file downloads")
    print("✅ Copy button (chapters only)")
    print("✅ Enhanced debugging")
    print("="*60)

def main():
    """Main build process"""
    print("Chapter Generator Build Script")
    print("="*40)
    
    # Step 1: Kill existing processes
    kill_existing_processes()
    
    # Step 2: Clean dist directory
    clean_dist_directory()
    
    # Step 3: Build onedir executable
    if not build_onedir():
        print("Build failed!")
        return False
    
    # Step 4: Copy Purfview Whisper
    if not copy_purfview():
        print("Purfview copy failed!")
        return False
    
    # Step 5: Create launcher
    if not create_launcher():
        print("Launcher creation failed!")
        return False
    
    # Step 6: Show completion info
    show_build_info()
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\nBuild completed successfully!")
        else:
            print("\nBuild failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nBuild interrupted by user!")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)
