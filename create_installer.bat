@echo off
echo Building Chapter Generator Installer...
echo.

REM Check if WinRAR is installed
if not exist "C:\Program Files\WinRAR\WinRAR.exe" (
    echo ERROR: WinRAR not found at C:\Program Files\WinRAR\WinRAR.exe
    echo Please install WinRAR first.
    pause
    exit /b 1
)

REM Set paths
set WINRAR="C:\Program Files\WinRAR\WinRAR.exe"
set SOURCE_DIR=dist\Chapter-Generator-Fixed
set OUTPUT_NAME=ChapterGeneratorInstaller.exe
set SFX_CONFIG=installer_setup.txt

REM Check if source directory exists
if not exist "%SOURCE_DIR%" (
    echo ERROR: Source directory not found: %SOURCE_DIR%
    echo Please build the application first using: pyinstaller ChapterGeneratorFixed.spec
    pause
    exit /b 1
)

REM Create temporary archive
echo Creating archive...
%WINRAR% a -r -ep1 -m5 temp_installer.rar "%SOURCE_DIR%\*"

REM Create SFX installer
echo Creating self-extracting installer...
copy /b "C:\Program Files\WinRAR\Default.SFX" + "%SFX_CONFIG%" + temp_installer.rar %OUTPUT_NAME%

REM Clean up
del temp_installer.rar
if exist temp_installer.exe del temp_installer.exe

echo.
echo ========================================
echo Installer created successfully!
echo Output: %OUTPUT_NAME%
echo ========================================
echo.
pause
