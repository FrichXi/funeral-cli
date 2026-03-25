#!/usr/bin/env bash
set -euo pipefail

# funeralai installer
# https://github.com/FrichXi/funeral-cli
#
# Usage: curl -fsSL https://raw.githubusercontent.com/FrichXi/funeral-cli/main/install.sh | bash

PACKAGE="funeralai"
MIN_PYTHON="3.10"
VENV_DIR="$HOME/.local/funeralai-venv"
BIN_DIR="$HOME/.local/bin"

# --- helpers ---

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
fail()  { printf '\033[1;31m==>\033[0m %s\n' "$*" >&2; exit 1; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

# --- check python ---

find_python() {
    for cmd in python3 python; do
        if command_exists "$cmd"; then
            echo "$cmd"
            return
        fi
    done
    return 1
}

check_python_version() {
    local py="$1"
    "$py" -c "
import sys
v = sys.version_info
req = tuple(int(x) for x in '$MIN_PYTHON'.split('.'))
if (v.major, v.minor) < req:
    print(f'{v.major}.{v.minor}')
    sys.exit(1)
print(f'{v.major}.{v.minor}')
" 2>/dev/null
}

PYTHON=$(find_python) || fail "找不到 Python。请先安装 Python $MIN_PYTHON+
  macOS:  brew install python3
  Linux:  sudo apt install python3  (或你的发行版对应命令)"

PY_VERSION=$(check_python_version "$PYTHON") || fail "Python 版本 $PY_VERSION 太低，需要 $MIN_PYTHON+
  macOS:  brew upgrade python3
  Linux:  sudo apt install python3.12  (或更高版本)"

info "Python $PY_VERSION ✓"

# --- already installed? ---

if command_exists "$PACKAGE"; then
    ok "$PACKAGE 已安装: $(which $PACKAGE)"
    info "如需升级: pipx upgrade $PACKAGE 或 uv tool upgrade $PACKAGE"
    exit 0
fi

# --- install via pipx (preferred) ---

if command_exists pipx; then
    info "检测到 pipx，用 pipx 安装..."
    pipx install "$PACKAGE"
    ok "安装完成！运行 $PACKAGE 开始使用"
    exit 0
fi

# --- install via uv (second choice) ---

if command_exists uv; then
    info "检测到 uv，用 uv 安装..."
    uv tool install "$PACKAGE"
    ok "安装完成！运行 $PACKAGE 开始使用"
    exit 0
fi

# --- try to install pipx ---

info "pipx 和 uv 都没装，尝试安装 pipx..."

install_pipx() {
    if command_exists brew; then
        info "通过 Homebrew 安装 pipx..."
        brew install pipx
        pipx ensurepath
        return 0
    fi

    if command_exists apt-get; then
        info "通过 apt 安装 pipx..."
        sudo apt-get update -qq && sudo apt-get install -y -qq pipx
        pipx ensurepath
        return 0
    fi

    if command_exists dnf; then
        info "通过 dnf 安装 pipx..."
        sudo dnf install -y pipx
        pipx ensurepath
        return 0
    fi

    return 1
}

if install_pipx; then
    # pipx ensurepath 可能改了 PATH，重新加载
    export PATH="$HOME/.local/bin:$PATH"
    if command_exists pipx; then
        info "pipx 安装成功，继续安装 $PACKAGE..."
        pipx install "$PACKAGE"
        ok "安装完成！运行 $PACKAGE 开始使用"
        info "如果提示找不到命令，重新打开终端或执行: source ~/.bashrc (或 ~/.zshrc)"
        exit 0
    fi
fi

# --- fallback: venv + symlink ---

warn "无法安装 pipx，使用 venv 兜底方案..."

info "创建虚拟环境: $VENV_DIR"
"$PYTHON" -m venv "$VENV_DIR"

info "安装 $PACKAGE..."
"$VENV_DIR/bin/pip" install --quiet "$PACKAGE"

# symlink to ~/.local/bin
mkdir -p "$BIN_DIR"
ln -sf "$VENV_DIR/bin/$PACKAGE" "$BIN_DIR/$PACKAGE"

# check if ~/.local/bin is in PATH
if ! echo "$PATH" | tr ':' '\n' | grep -q "^$BIN_DIR$"; then
    warn "$BIN_DIR 不在 PATH 中"
    SHELL_NAME=$(basename "${SHELL:-/bin/bash}")
    case "$SHELL_NAME" in
        zsh)  RC_FILE="$HOME/.zshrc" ;;
        bash) RC_FILE="$HOME/.bashrc" ;;
        *)    RC_FILE="$HOME/.profile" ;;
    esac
    if ! grep -q "$BIN_DIR" "$RC_FILE" 2>/dev/null; then
        echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$RC_FILE"
        info "已添加 $BIN_DIR 到 $RC_FILE"
    fi
    export PATH="$BIN_DIR:$PATH"
fi

# --- verify ---

if command_exists "$PACKAGE"; then
    ok "安装完成！运行 $PACKAGE 开始使用"
    info "如果提示找不到命令，重新打开终端即可"
else
    fail "安装似乎没成功，请手动尝试:
  pipx install $PACKAGE
  或
  pip install $PACKAGE (在虚拟环境中)"
fi
