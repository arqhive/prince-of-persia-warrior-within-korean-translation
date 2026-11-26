@echo off
setlocal
set "TEMP=%~dp0"
set "TMP=%~dp0"
set "TMPDIR=%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0patch.ps1" %*
set "exitCode=%ERRORLEVEL%"
echo.
pause
exit /b %exitCode%
