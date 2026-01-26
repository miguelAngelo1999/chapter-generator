#!/usr/bin/env python3
"""
Build script for Chapter Generator application
Creates standalone executable and distribution package
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def clean_build():
    """Clean previous build artifacts"""
    print("🧹 Cleaning previous build artifacts...")
    
    dirs_to_clean = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"  Removed: {dir_name}")
    
    # Clean .pyc files
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.pyc'):
                pyc_path = os.path.join(root, file)
                os.remove(pyc_path)
                print(f"  Removed: {pyc_path}")

def install_dependencies():
    """Install required build dependencies"""
    print("📦 Installing build dependencies...")
    
    dependencies = [
        'pyinstaller',
        'pywebview'
    ]
    
    for dep in dependencies:
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', dep])
            print(f"  ✅ {dep}")
        except subprocess.CalledProcessError:
            print(f"  ❌ Failed to install {dep}")
            return False
    
    return True

def build_executable():
    """Build standalone executable using PyInstaller"""
    print("🔨 Building standalone executable...")
    
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--name=Chapter-Generator',
        '--windowed',  # No console window
        '--onedir',    # Directory mode (not single executable)
        '--add-data=templates;templates',  # Include templates folder
        '--add-data=setup.py;setup.py',  # Include setup script
        '--clean',
        'chapter_generator.py'
    ]
    
    # Add icon if it exists
    if os.path.exists('icon.ico'):
        cmd.insert(-1, '--icon=icon.ico')
    
    try:
        subprocess.check_call(cmd)
        print("  ✅ Build completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Build failed: {e}")
        return False

def create_portable_package():
    """Create portable package with executable and dependencies"""
    print("📦 Creating portable package...")
    
    dist_dir = Path('dist')
    if not dist_dir.exists():
        print("  ❌ dist directory not found - build first")
        return False
    
    # Create package directory
    package_name = "Chapter-Generator-Portable"
    package_dir = dist_dir / package_name
    
    if package_dir.exists():
        shutil.rmtree(package_dir)
    
    package_dir.mkdir()
    
    # Copy entire Chapter-Generator directory contents
    app_dir = dist_dir / "Chapter-Generator"
    if app_dir.exists():
        # Copy all contents from the built directory
        for item in app_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, package_dir / item.name)
            else:
                shutil.copytree(item, package_dir / item.name, dirs_exist_ok=True)
        print("  ✅ Copied application directory")
    else:
        print("  ❌ Application directory not found")
        return False
    
    # Extract setup script from executable if needed
    setup_source = Path("setup.py")
    if setup_source.exists():
        shutil.copy2(setup_source, package_dir / "setup.py")
        print("  ✅ Copied setup script")
    else:
        # Create a simple setup instruction file
        setup_instructions = """# Chapter Generator Setup

## 📥 First Time Setup

This application requires Purfview Whisper for transcription.

### Option 1: Automatic Setup (Recommended)
1. Run: python setup.py
2. Follow the prompts to download Whisper

### Option 2: Manual Setup
1. Download from: https://github.com/Purfview/whisper-standalone-win/releases
2. Extract to: Purfview-Whisper-Faster/
3. Restart Chapter Generator

## 🚀 After Setup

Once Whisper is installed, you can:
- Process video/audio files with transcription
- Generate SRT files from media
- Create chapters from transcribed content

## ⚠️  Important

- Whisper is only needed for video/audio files
- SRT files work without additional setup
- Internet connection required for first-time setup
"""
        with open(package_dir / "SETUP.md", 'w') as f:
            f.write(setup_instructions)
        print("  ✅ Created setup instructions")
    
    # Copy additional files if they exist
    additional_files = ['README.md', 'LICENSE']
    for file_name in additional_files:
        if os.path.exists(file_name):
            shutil.copy2(file_name, package_dir / file_name)
            print(f"  ✅ Copied {file_name}")
    
    # Create launcher script
    launcher_script = """@echo off
title Chapter Generator
echo Checking dependencies...

if not exist "Purfview-Whisper-Faster\faster-whisper-xxl.exe" (
    echo.
    echo ⚠️  Purfview Whisper not found!
    echo.
    echo Please run setup.py first to install Whisper
    echo or download manually from GitHub releases
    echo.
    echo Press any key to continue anyway...
    pause > nul
)

echo Starting Chapter Generator...
echo.
Chapter-Generator.exe
if errorlevel 1 (
    echo.
    echo Error: Application encountered an error
    pause
)
"""
    
    with open(package_dir / "Start.bat", 'w', encoding='utf-8') as f:
        f.write(launcher_script)
    
    print("  ✅ Created launcher script")
    
    # Create ZIP archive
    import zipfile
    zip_path = dist_dir / f"{package_name}.zip"
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in package_dir.rglob('*'):
            if file_path.is_file():
                zipf.write(file_path, file_path.relative_to(package_dir))
    
    print(f"  ✅ Created portable package: {zip_path}")
    return True

def main():
    """Main build process"""
    print("🚀 Chapter Generator Build Process")
    print("=" * 50)
    
    # Skip cleaning to avoid permission issues
    print("⏭️  Skipping clean step (dist folder in use)")
    
    # Step 2: Install dependencies
    if not install_dependencies():
        print("❌ Build failed due to dependency installation")
        return 1
    
    # Step 3: Build executable
    if not build_executable():
        print("❌ Build failed during executable creation")
        return 1
    
    # Step 4: Create portable package
    if not create_portable_package():
        print("❌ Build failed during package creation")
        return 1
    
    # Step 5: Post-build setup
    print("\n🔧 Running post-build setup...")
    try:
        import post_build
        if post_build.copy_dependencies_to_exe():
            print("✅ Post-build setup completed")
        else:
            print("⚠️  Post-build setup had issues")
    except ImportError:
        print("⚠️  Post-build script not found")
    except Exception as e:
        print(f"❌ Post-build setup failed: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Build completed successfully!")
    print("📁 Location: dist/Chapter-Generator-Portable.zip")
    print("🚀 Ready for distribution!")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
