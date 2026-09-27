@echo off
rem Restore default clocks (and optionally power limit).
rem Replace <GPU_INDEX> with the eGPU's nvidia-smi index.
rem <DEFAULT_POWER_LIMIT_W>: leave -pl out unless a power limit was
rem actually changed manually; check default with 'nvidia-smi -q -d POWER'.
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
echo Resetting GPU <GPU_INDEX> to default clocks...
nvidia-smi -i <GPU_INDEX> -rgc
rem nvidia-smi -i <GPU_INDEX> -pl <DEFAULT_POWER_LIMIT_W>
echo Done.
pause
