@echo off
rem ECO mode: cap core clock only.
rem WARNING for modded-VRAM cards (e.g. modded 16GB): NEVER set a power
rem limit (-pl) - extra VRAM needs its power budget or the card drops offline.
rem Replace <GPU_INDEX> with the eGPU's nvidia-smi index (check with -L).
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
echo ================================================
echo   ECO MODE (clock cap only, power limit untouched)
echo ================================================
echo NOTE: modded VRAM cards - do NOT set -pl, VRAM
echo needs its power budget or the card can drop.
nvidia-smi -i <GPU_INDEX> -lgc 300,1650
echo.
echo Done. GPU <GPU_INDEX> core capped at 1650 MHz.
echo To tune: edit the -lgc values (max clock = check
echo 'nvidia-smi -q -d SUPPORTED_CLOCKS').
pause
