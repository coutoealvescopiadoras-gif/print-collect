@echo off
setlocal
schtasks /Delete /F /TN "Print Collect Agent"
