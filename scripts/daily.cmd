@echo off
rem One GameAnalyst run. Windows Task Scheduler can call this file once a day.
cd /d "%~dp0.."
if not exist data\logs mkdir data\logs
".venv\Scripts\python.exe" -m gameanalyst collect >> "data\logs\collect.log" 2>&1
