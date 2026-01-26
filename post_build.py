#!/usr/bin/env python3
"""
Post-build script for Chapter Generator
Copies required dependencies to the executable location
"""

import os
import sys
import shutil
from pathlib import Path

def copy_dependencies_to_exe():
    """Copy Purfview Whisper to the executable directory"""
    
    # Find the executable
    exe_path = Path("dist/Chapter-Generator.exe")
    if not exe_path.exists():
        print("❌ Chapter-Generator.exe not found in dist/")
        return False
    
    exe_dir = exe_path.parent
    portable_dir = exe_dir / "Chapter-Generator-Portable"
    
    print(f"📁 Found executable at: {exe_path}")
    print(f"📁 Target directory: {portable_dir}")
    
    # Create portable directory if it doesn't exist
    portable_dir.mkdir(exist_ok=True)
    
    # Copy executable
    shutil.copy2(exe_path, portable_dir / "Chapter-Generator.exe")
    print("✅ Copied executable")
    
    # Copy Purfview Whisper
    whisper_source = Path("Purfview-Whisper-Faster")
    whisper_target = portable_dir / "Purfview-Whisper-Faster"
    
    if whisper_source.exists():
        if whisper_target.exists():
            shutil.rmtree(whisper_target)
        shutil.copytree(whisper_source, whisper_target)
        print("✅ Copied Purfview Whisper")
    else:
        print("⚠️  Purfview Whisper not found - transcription won't work")
    
    # Copy other files
    files_to_copy = [
        "README.md",
        "setup.py",
        "templates/index.html"
    ]
    
    for file_path in files_to_copy:
        source = Path(file_path)
        if source.exists():
            if file_path == "templates/index.html":
                # Create templates directory in portable package
                templates_dir = portable_dir / "templates"
                templates_dir.mkdir(exist_ok=True)
                shutil.copy2(source, templates_dir / "index.html")
                print("✅ Copied templates")
            else:
                shutil.copy2(source, portable_dir / source.name)
                print(f"✅ Copied {source.name}")
    
    # Create launcher script
    launcher_content = """@echo off
title Chapter Generator
echo Checking dependencies...

if not exist "Purfview-Whisper-Faster\\faster-whisper-xxl.exe" (
    echo.
    echo WARNING: Purfview Whisper not found!
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
    
    with open(portable_dir / "Start.bat", 'w', encoding='utf-8') as f:
        f.write(launcher_content)
    print("✅ Created launcher script")
    
    return True

def main():
    """Main post-build process"""
    print("🔧 Chapter Generator Post-Build Setup")
    print("=" * 50)
    
    if copy_dependencies_to_exe():
        print("\n" + "=" * 50)
        print("🎉 Post-build setup completed!")
        print("📁 Portable package ready at: dist/Chapter-Generator-Portable/")
        print("🚀 You can now distribute the portable package!")
        return 0
    else:
        print("\n❌ Post-build setup failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
