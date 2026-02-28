@echo off
REM CI Clone Testbed -- Daily Experiment Launcher
REM Create a desktop shortcut to this file for easy daily access.
REM
REM Safety checks built in:
REM   - Won't run if too late in UTC day (past 5 PM EST)
REM   - Won't run if last experiment was less than 20 hours ago
REM   - Requires confirmation before triggering

cd /d "%~dp0"
python run_experiment.py %*
echo.
pause
