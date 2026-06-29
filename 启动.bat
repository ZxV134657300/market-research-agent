@echo off
cd /d "%~dp0"
echo 启动服务中，请稍候...
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
pause