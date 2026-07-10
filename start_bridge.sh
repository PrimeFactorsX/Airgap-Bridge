#!/bin/bash
cd "$(dirname "$0")"

echo "========================================"
echo "     桥接服务器 - 启动中"
echo "========================================"

if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "[错误] 未找到 Python，请先安装 Python 3.8+"
    read -n 1 -p "按任意键退出..."
    exit 1
fi

echo "[信息] 使用 Python: $($PYTHON --version)"
mkdir -p cache 2>/dev/null

echo "[信息] 启动服务器..."
$PYTHON bridge_server.py

if [ $? -ne 0 ]; then
    echo "[错误] 服务器异常退出，请检查上方日志。"
    read -n 1 -p "按任意键退出..."
fi