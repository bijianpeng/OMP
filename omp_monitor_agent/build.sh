#!/bin/bash
# ============================================================
# build.sh - 从源码构建 monitor_agent_exporter
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/src"
BUILD_DIR="$SCRIPT_DIR/build"
DIST_DIR="$SCRIPT_DIR/dist"
SPEC_FILE="$BUILD_DIR/monitor_agent_exporter.spec"

# Python 解释器 - 优先使用虚拟环境中的 python3.8
PYTHON=""
for p in "$SCRIPT_DIR/venv/bin/python3.8" \
         "$SCRIPT_DIR/venv/bin/python3" \
         "$(which python3.8 2>/dev/null)" \
         "$(which python3 2>/dev/null)"; do
    if [ -x "$p" ]; then
        PYTHON="$p"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "错误: 找不到 Python 3.8+ 解释器"
    echo "请安装 Python 3.8 并创建虚拟环境:"
    echo "  python3.8 -m venv venv"
    echo "  source venv/bin/activate"
    exit 1
fi

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "=== OMP Monitor Agent 构建脚本 ==="
echo "Python: $PYTHON ($PY_VERSION)"
echo "源码目录: $SRC_DIR"
echo ""

# Step 1: 检查虚拟环境
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "[1/6] 创建虚拟环境..."
    $PYTHON -m venv "$SCRIPT_DIR/venv"
    PYTHON="$SCRIPT_DIR/venv/bin/python"
fi

# Step 2: 安装依赖
echo "[2/6] 安装依赖..."
$PYTHON -m pip install --upgrade pip --quiet
$PYTHON -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
$PYTHON -m pip install pyinstaller --quiet

# Step 3: 语法验证
echo "[3/6] 验证源码..."
FAILED=0
for f in "$SRC_DIR"/main.py "$SRC_DIR"/ext.py "$SRC_DIR"/lib/*.py; do
    if ! $PYTHON -m py_compile "$f" 2>/dev/null; then
        echo "  语法错误: $f"
        FAILED=1
    fi
done
if [ $FAILED -ne 0 ]; then
    echo "错误: 源码语法验证失败"
    exit 1
fi
echo "  所有源文件语法正确"

# Step 4: 生成 PyInstaller spec 文件
echo "[4/6] 生成 PyInstaller spec..."
mkdir -p "$BUILD_DIR"

cat > "$SPEC_FILE" << 'SPEC'
# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

hiddenimports = [
    'sanic',
    'sanic.response',
    'sanic.routing',
    'sanic_routing',
    'aiohttp',
    'uvloop',
    'psutil',
    'ruamel.yaml',
    'ujson',
    'multidict',
    'yarl',
    'httptools',
    'websockets',
    'attrs',
    'ext',
    'lib',
    'lib.webapp',
    'lib.views',
    'lib.scheduler',
    'lib.job',
    'lib.boot',
    'lib.utils',
    'lib.constants',
    'scripts',
    'scripts.core',
    'scripts.host_check',
    'scripts.inspection_common',
    'scripts.redis_check',
    'scripts.test',
    'configparser',
    'asyncio',
    'json',
    'pickle',
    'importlib',
]

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='monitor_agent_exporter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir='./lib/executions',
    console=True,
)
SPEC

# PyInstaller 以 spec 所在目录为基准解析 spec 内相对路径，改为绝对路径
sed -i "s|\['src/main.py'\]|['$SRC_DIR/main.py']|; s|pathex=\['src'\]|pathex=['$SRC_DIR']|" "$SPEC_FILE"

# Step 5: 构建
echo "[5/6] 使用 PyInstaller 构建..."
cd "$SCRIPT_DIR"
$PYTHON -m PyInstaller "$SPEC_FILE" \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR/temp" \
    --clean \
    --noconfirm \
    2>&1 | tail -5

# Step 6: 验证和复制
echo "[6/6] 验证构建产物..."
if [ -f "$DIST_DIR/monitor_agent_exporter" ]; then
    cp "$DIST_DIR/monitor_agent_exporter" "$SCRIPT_DIR/monitor_agent_exporter.new"
    chmod +x "$SCRIPT_DIR/monitor_agent_exporter.new"

    echo ""
    echo "=== 构建成功 ==="
    echo "原始文件大小: $(wc -c < "$SCRIPT_DIR/monitor_agent_exporter") bytes"
    echo "新文件大小:   $(wc -c < "$SCRIPT_DIR/monitor_agent_exporter.new") bytes"
    echo ""
    echo "新二进制文件: $SCRIPT_DIR/monitor_agent_exporter.new"
    echo ""
    echo "部署方法:"
    echo "  1. 停止服务: bash monitor_agent.sh stop"
    echo "  2. 替换文件: cp monitor_agent_exporter.new monitor_agent_exporter"
    echo "  3. 启动服务: bash monitor_agent.sh start"
else
    echo "错误: 构建产物未找到"
    exit 1
fi
