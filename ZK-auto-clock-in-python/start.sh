#!/bin/bash
# Linux/Mac 快速启动脚本

echo "===================================="
echo "ZK Admin - 快速启动"
echo "===================================="
echo ""

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "[错误] 虚拟环境不存在"
    echo "请先运行: bash setup_venv.sh"
    exit 1
fi

# 激活虚拟环境
source venv/bin/activate

# 检查数据库
if [ ! -f "database/zk_admin.db" ]; then
    echo "[初始化] 数据库不存在，正在初始化..."
    python scripts/init_db.py
    if [ $? -ne 0 ]; then
        echo "[错误] 数据库初始化失败"
        exit 1
    fi
fi

# 启动应用
echo ""
echo "[启动] 正在启动应用..."
echo ""
echo "访问地址:"
echo "  - 管理面板: http://localhost:8000/dashboard"
echo "  - API 文档: http://localhost:8000/docs"
echo "  - 默认账号: admin / admin"
echo ""
echo "按 Ctrl+C 停止应用"
echo ""

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
