@echo off
rem Safe-disconnect eGPU before unplugging the dock.
rem Replace <GPU_INSTANCE_ID> with the real device instance ID
rem (Get-CimInstance Win32_VideoController | PNPDeviceID).
rem NOTE: instance ID changes if you switch ports / reinstall driver.
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
echo Disabling external GPU...
pnputil /disable-device "<GPU_INSTANCE_ID>"
echo.
echo Done! Now safe to unplug the dock / cable.
pause
