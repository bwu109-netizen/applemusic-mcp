#!/bin/bash
# Double-click to install: uv -> self-test -> register with Claude Desktop.
# 双击安装：装 uv -> 自检 -> 注册到 Claude 桌面版。
set -u
cd "$(dirname "$0")" || exit 1
PROJECT="$(pwd)"
pause() { read -r -p "Press Enter to close / 按回车关闭 "; }

echo "== 1/3  Installing uv (Python toolchain) / 安装 uv"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh || { echo "uv install failed / uv 安装失败"; pause; exit 1; }
  export PATH="$HOME/.local/bin:$PATH"
fi
UV="$(command -v uv)"
echo "uv: $UV"

# Keep the virtualenv outside the project: ~/Documents is often synced by iCloud,
# which can hide or evict files inside a venv and break it.
# 虚拟环境放在项目外：文稿文件夹常被 iCloud 同步，会破坏里面的虚拟环境。
VENV="$HOME/.local/share/applemusic-mcp/venv"
export UV_PROJECT_ENVIRONMENT="$VENV"
export PYTHONPATH="$PROJECT/src"
rm -rf "$PROJECT/.venv"
"$UV" sync --reinstall-package applemusic-mcp || { echo "Dependency install failed / 依赖安装失败"; pause; exit 1; }

echo
echo "== 2/3  Read-only self-test / 只读自检"
echo "   If macOS asks to allow control of Music, click OK. / 弹窗询问能否控制「音乐」时点「好」。"
if ! "$UV" run python scripts/smoke_test.py; then
  echo
  echo "Self-test failed. See README > Troubleshooting. / 自检未通过，见 README 的常见问题。"
  pause; exit 1
fi

echo
echo "== 3/3  Registering with Claude Desktop / 写入 Claude 桌面版配置"
CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
mkdir -p "$(dirname "$CFG")"
[ -f "$CFG" ] && cp "$CFG" "$CFG.bak" && echo "Backup / 备份: $CFG.bak"
"$UV" run python - "$CFG" "$UV" "$PROJECT" "$VENV" <<'PY'
import json, os, sys
cfg, uv, project, venv = sys.argv[1:5]
data = {}
if os.path.exists(cfg) and os.path.getsize(cfg) > 0:
    with open(cfg) as f:
        data = json.load(f)
data.setdefault("mcpServers", {})["apple-music"] = {
    "command": uv,
    "args": ["run", "--directory", project, "python", "-m", "applemusic_mcp.server"],
    "env": {"UV_PROJECT_ENVIRONMENT": venv, "PYTHONPATH": os.path.join(project, "src")},
}
with open(cfg, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print("Updated / 已写入:", cfg)
PY

echo
echo "Done! Quit Claude Desktop (Cmd+Q), reopen it, and ask: \"What's playing?\""
echo "完成！按 Cmd+Q 完全退出 Claude 再打开，问它「现在在放什么歌」。"
pause
