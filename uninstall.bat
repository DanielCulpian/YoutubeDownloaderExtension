@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0extension-vivaldi\uninstall.ps1" -CleanGenerated
if errorlevel 1 echo Uninstallation failed. Review the message above.
pause
