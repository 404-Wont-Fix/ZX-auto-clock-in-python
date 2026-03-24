@echo off
REM Windows 虚拟环境设置脚本

echo ====================================
echo ZK Admin - 虚拟环境设置脚本
echo ====================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.11+
    pause
    exit /b 1
)

REM 创建虚拟环境
if not exist venv (
    echo [1/4] 创建虚拟环境...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo [完成] 虚拟环境创建成功
) else (
    echo [跳过] 虚拟环境已存在
)

REM 激活虚拟环境
echo.
echo [2/4] 激活虚拟环境...
call venv\Scripts\activate.bat

REM 升级 pip
echo.
echo [3/4] 升级 pip...
python -m pip install --upgrade pip

REM 安装依赖
echo.
echo [4/4] 安装项目依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo.
echo ====================================
echo [完成] 虚拟环境设置完成！
echo ====================================
echo.
echo 下一步：
echo 1. 复制 .env.example 到 .env
echo 2. 编辑 .env 配置必要参数
echo 3. 运行: python scripts/init_db.py
echo 4. 运行: uvicorn app.main:app --reload
echo.
echo 激活虚拟环境命令: venv\Scripts\activate.bat
echo.
pause
