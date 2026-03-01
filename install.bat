@echo off
echo ============================================
echo   APTS-Release Tool - Installer
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on PATH.
    echo Download from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo [1/2] Installing apts-release...
pip install "%~dp0apts-release" --user --quiet
if errorlevel 1 (
    echo [ERROR] Installation failed.
    pause
    exit /b 1
)

echo [2/2] Verifying installation...
echo.

:: Try running it
apts-release --version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] apts-release installed but not found on PATH.
    echo.
    echo Run this in PowerShell to fix PATH, then restart your terminal:
    echo.
    echo   $p = python -c "import sysconfig; print(sysconfig.get_path('scripts','nt_user'))"
    echo   [Environment]::SetEnvironmentVariable("Path","$env:Path;$p","User")
    echo.
) else (
    for /f "delims=" %%v in ('apts-release --version') do echo   %%v
    echo.
    echo [SUCCESS] apts-release is ready to use!
)

echo.
echo Usage:
echo   cd your-firmware-project-folder
echo   apts-release
echo.
pause
