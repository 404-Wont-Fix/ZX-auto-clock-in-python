@echo off
REM Windows 快速启动脚本

echo ====================================
echo ZK Admin - 快速启动
echo ====================================
echo.

REM 检查虚拟环境
if not exist "venv\" (
    echo [错误] 虚拟环境不存在
    echo 请先运行: setup_venv.bat
    pause
    exit /b 1
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 检查数据库
if not exist "database\zk_admin.db" (
    echo [初始化] 数据库不存在，正在初始化...
    python scripts/init_db.py
    if errorlevel 1 (
        echo [错误] 数据库初始化失败
        pause
        exit /b 1
    )
)

REM 启动应用
echo.
echo [启动] 正在启动应用...
echo.
echo 访问地址:
echo   - 管理面板: http://localhost:8000/dashboard
echo   - API 文档: http://localhost:8000/docs
echo   - 默认账号: admin / admin
echo.
echo 按 Ctrl+C 停止应用
echo.

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
