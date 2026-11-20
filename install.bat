@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0extension-vivaldi\install.ps1" %*
if errorlevel 1 echo Installation failed. Review the message above.
pause
