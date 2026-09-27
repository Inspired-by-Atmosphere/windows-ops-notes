@echo off
rem Re-enable eGPU after plugging the dock back in.
rem Replace <GPU_INSTANCE_ID> with the real device instance ID.
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
echo Re-enabling external GPU...
pnputil /enable-device "<GPU_INSTANCE_ID>"
echo Done!
pause
