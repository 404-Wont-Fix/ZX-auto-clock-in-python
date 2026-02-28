#!/bin/bash
# Linux/Mac 虚拟环境设置脚本

set -e

echo "===================================="
echo "ZK Admin - 虚拟环境设置脚本"
echo "===================================="
echo ""

# 检查 Python 是否安装
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 Python3，请先安装 Python 3.11+"
    exit 1
fi

echo "[检测] Python 版本: $(python3 --version)"

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo ""
    echo "[1/4] 创建虚拟环境..."
    python3 -m venv venv
    echo "[完成] 虚拟环境创建成功"
else
    echo ""
    echo "[跳过] 虚拟环境已存在"
fi

# 激活虚拟环境
echo ""
echo "[2/4] 激活虚拟环境..."
source venv/bin/activate

# 升级 pip
echo ""
echo "[3/4] 升级 pip..."
pip install --upgrade pip

# 安装依赖
echo ""
echo "[4/4] 安装项目依赖..."
pip install -r requirements.txt

echo ""
echo "===================================="
echo "[完成] 虚拟环境设置完成！"
echo "===================================="
echo ""
echo "下一步："
echo "1. 复制 .env.example 到 .env"
echo "2. 编辑 .env 配置必要参数"
echo "3. 运行: python scripts/init_db.py"
echo "4. 运行: uvicorn app.main:app --reload"
echo ""
echo "激活虚拟环境命令: source venv/bin/activate"
echo ""
