# applemusic-mcp

[![CI](https://github.com/bwu109-netizen/applemusic-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/bwu109-netizen/applemusic-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[English](README.md) | 简体中文

一个 [MCP](https://modelcontextprotocol.io) 服务器，让 Claude（或任何 MCP 客户端）控制 **Mac 上的「音乐」App**，并分析你的资料库。直接用说的就行：

> 「放点王力宏」
> 「把资料库里的 K-pop 歌整理成一个歌单」
> 「我最常听什么风格？」
> 「把歌单 3、2、1 里的歌从最后一首往前依次标喜爱，让喜爱歌曲按原顺序排好」

所有操作都通过 JavaScript for Automation（JXA）在你的 Mac 本地完成。不需要 Apple 开发者账号和 API key，数据也不会离开你的电脑。

## 功能

| 类别 | 工具 |
|---|---|
| 播放 | `now_playing`、`playback`（播放 / 暂停 / 切换 / 下一首 / 上一首 / 停止）、`set_player_options`（音量、随机、循环） |
| 搜索 | `search_library`、`search_and_play`、`play_track` |
| 歌单 | `list_playlists`、`get_playlist_tracks`、`play_playlist`、`create_playlist`、`add_to_playlist`、`remove_from_playlist`、`compare_playlists` |
| 喜爱 | `set_favorite`、`favorite_playlist`（按顺序分批标记，可设间隔，让"按喜爱日期排序"保持你想要的顺序） |
| 统计 | `listening_stats`（总览、最常听的歌曲 / 歌手 / 专辑 / 风格、最近添加 / 播放）、`artist_stats` |

**限制：**只搜索你的资料库，不搜整个 Apple Music 曲库。播放次数是「音乐」App 在这台 Mac 上记的累计值，没有按周的历史。如果你主要用手机听歌，次数可能会很少。

## 环境要求

- 装有「音乐」App 的 macOS（已在较新的 macOS + Apple 芯片上测试）
- [Claude 桌面版](https://claude.ai/download)或其他 MCP 客户端
- [uv](https://docs.astral.sh/uv/)，安装脚本会自动装好

## 安装

### 一键安装

1. 下载或 clone 本仓库，比如放到 `~/Documents/applemusic-mcp`
2. 双击 **`install.command`**。如果被系统拦截，就右键 > 打开
   它会安装 uv，跑一遍只读自检，再把服务器加进 Claude 桌面版配置（原配置会先备份）
3. 系统弹窗问是否允许控制「音乐」时，点**好**
4. 按 Cmd+Q 完全退出 Claude 再打开，问它「现在在放什么歌」

### 手动安装

```bash
git clone https://github.com/bwu109-netizen/applemusic-mcp.git
cd applemusic-mcp
uv sync
uv run python scripts/smoke_test.py   # 只读自检
```

然后在 `~/Library/Application Support/Claude/claude_desktop_config.json` 里加上下面的配置，路径换成你自己的（`which uv` 可以查 uv 在哪）：

```json
{
  "mcpServers": {
    "apple-music": {
      "command": "/Users/you/.local/bin/uv",
      "args": ["run", "--directory", "/Users/you/applemusic-mcp", "python", "-m", "applemusic_mcp.server"],
      "env": { "PYTHONPATH": "/Users/you/applemusic-mcp/src" }
    }
  }
}
```

## 常见问题

- **提示没有权限（Not authorized to send Apple events）**：打开 系统设置 > 隐私与安全性 > 自动化，给 Claude（或你的终端）打开「音乐」。
- **插件反复断开，或报 `No module named applemusic_mcp`**：项目如果放在「文稿」这类 iCloud 同步的文件夹里，iCloud 可能会破坏里面的 `.venv`。`install.command` 会把虚拟环境放到 `~/.local/share/applemusic-mcp/venv`，重新运行一次就好。
- **改了代码不生效**：Claude 桌面版只在启动时加载一次插件，按 Cmd+Q 退出再打开。

## 工作原理

```
Claude ──MCP (stdio)──▶ server.py ──osascript -l JavaScript──▶ 音乐.app
```

- `jxa.py` 通过 `osascript` 执行 JXA。用户输入以 JSON 形式经 `argv` 传入，不会拼进脚本源码，所以带引号的歌名不会出错，也没法注入代码。出错时会返回看得懂的错误信息。
- `server.py` 定义所有工具。读取资料库时按属性批量读（每个属性一个 Apple Event，而不是每首歌一个），歌再多也很快。
- `stats.py` 是纯 Python 的统计逻辑，资料库数据缓存 5 分钟。

## 开发

```bash
uv sync
uv run pytest
```

测试会模拟「音乐」App，所以在 Linux 上也能跑（CI 用的是 Ubuntu）。测试还会对每段生成的 JXA 脚本跑 `node --check`，语法错误在上 Mac 之前就能发现。

欢迎提 PR。可以做的方向：通过 MusicKit 搜索 Apple Music 曲库、选择 AirPlay 设备、评分、创建智能歌单。

## 许可证

[MIT](LICENSE)
