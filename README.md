# Airgap-Bridge
单文件、零依赖的本地桥接服务器，让AI Agent通过网页版 AI 完成对话和工具调用。仅供学习参考，请于下载后24h内删除，使用时请严格遵循服务商用户协议，请勿自动化访问、大规模商用或去除 AI 生成内容标识。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-green.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()
[![No Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)]()

一个**单文件、零依赖**的 Python HTTP 服务器，作为 AI 工具与本地文件系统之间的桥梁。通过 HTTP API 接收请求，写入本地文件供 AI 工具读取，再将 AI 的响应返回给调用方。

## 为什么需要它？

当你需要在本地将任意 HTTP 客户端（或支持自定义 API 端点的 AI 工具）与手动操作的 AI 网页界面串联时，这个桥接服务器充当中间人：

- 客户端发送 POST 请求到服务器
- 服务器将请求内容写入 `request.txt`
- 你（或 AI 工具）读取并处理请求，将响应写入 `response.txt`
- 服务器检测到响应后，将其作为 JSON 返回给客户端

整个过程完全本地，不依赖任何外部 API 服务，也不需要 API 密钥。

## 核心功能

- **零依赖**：仅使用 Python 3.8+ 标准库，无需 pip 安装任何第三方包
- **自动初始化**：首次运行自动生成 `config.json`、缓存目录和启动脚本
- **多用户支持**：可选多用户模式，通过 HTTP 请求头或 URL 参数隔离数据
- **会话记录**：可配置的对话历史 JSON 保存功能
- **CORS 支持**：内置跨域请求处理
- **隐私安全**：日志不记录用户输入内容，所有数据存储于本地
- **跨平台**：Windows、macOS、Linux 均可运行
- **可配置端点**：自定义 API 路径和包装模板

## 快速开始

### 环境要求
- Python 3.8 或更高版本
- 任何操作系统（Windows / macOS / Linux）

### 1. 下载项目

将仓库文件下载或克隆到本地文件夹，确保包含：
- `bridge_server.py` — 主程序
- `start_bridge.bat` — Windows 启动脚本
- `start_bridge.sh` — macOS/Linux 启动脚本

### 2. 启动服务器

**Windows 用户**

直接双击 `start_bridge.bat`。

**macOS / Linux 用户**

打开终端，进入项目目录，运行：
```bash
chmod +x start_bridge.sh
./start_bridge.sh
```

或直接运行：
```bash
python3 bridge_server.py
```

首次运行会自动创建 `config.json` 及所需目录。启动成功后显示：
```
服务器已启动: http://localhost:5000/bridge/messages
健康检查: http://localhost:5000/health
```

### 3. 测试连接

```bash
# 健康检查
curl http://localhost:5000/health

# 发送消息
curl -X POST http://localhost:5000/bridge/messages \
  -H "Content-Type: application/json" \
  -d '{"message": "请写一个 Python 的 Hello World"}'
```

### 4. 使用流程

服务器收到 POST 请求后：
1. 将包装后的请求写入 `user_data/default/request.txt`
2. 轮询等待 `user_data/default/response.txt` 被写入非空内容
3. 读取响应并作为 JSON 返回

你可以手动操作，也可以配合支持文件读写的 AI 工具自动完成。

## 配置说明

首次运行自动生成 `config.json`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `port` | `5000` | HTTP 服务器监听端口 |
| `cache_folder` | `"./cache"` | 缓存目录路径 |
| `endpoint` | `"/bridge/messages"` | API 端点路径 |
| `wrapper_template` | (预设模板) | 包装用户消息的 Prompt 模板，使用 `{user_message}` 占位符 |
| `multi_user` | `false` | 是否启用多用户模式 |
| `user_data_folder` | `"./user_data"` | 用户数据存储根目录 |
| `save_sessions` | `false` | 是否保存对话历史 |
| `session_folder` | `"./sessions"` | 会话记录存储目录 |
| `clear_cache_on_start` | `true` | 启动时是否清空缓存 |

修改配置后重启服务器生效。配置损坏或缺失时，服务器会使用内置默认值并自动重建。

### 多用户模式

设置 `"multi_user": true` 启用：
- 通过请求头 `X-User-ID: alice` 指定用户
- 或通过 URL 参数 `?user=alice` 指定
- 每个用户拥有独立的 `user_data/<user_id>/` 目录

> ⚠️ **安全警告**：多用户模式不包含身份认证，仅适用于本地信任环境，请勿在公网或共享服务器上启用。

## 项目结构

```
Bridge_Serve_Open/
├── bridge_server.py       # 主程序（单文件，零依赖）
├── start_bridge.bat       # Windows 启动脚本
├── start_bridge.sh        # macOS/Linux 启动脚本
├── config.json            # （自动生成）用户配置文件
├── bridge_server.log      # （自动生成）日志文件
├── cache/                 # （自动生成）缓存目录
├── user_data/             # （自动生成）用户数据目录
│   └── default/
│       ├── request.txt
│       └── response.txt
├── sessions/              # （可选）会话记录
├── README.md
└── LICENSE
```

## 常见问题

**Q: 端口被占用？**

A: 修改 `config.json` 中的 `port` 为其他值（如 `8080`），重启服务器。

**Q: 中文乱码？**

A: 服务器所有文件操作均使用 UTF-8 编码。Windows 用户请确保 `start_bridge.bat` 包含 `chcp 65001`（默认已提供）。

**Q: 请求超时？**

A: 服务器默认等待 300 秒。请确保在超时前将响应写入 `response.txt`。

**Q: 如何同时服务多个客户端？**

A: 启用多用户模式，为每个客户端分配不同的用户名。

## 贡献

欢迎提交 Issue 和 Pull Request！

本项目采用 [MIT 许可证](LICENSE)。贡献即表示你同意将代码以相同许可证授权。

## 免责声明

- 本项目仅供个人学习与研究使用，不提供任何商业服务或保证
- 使用者应自行承担使用风险，开发者不对因使用本项目造成的任何损失负责
- 使用本项目时请遵守所使用 AI 服务的第三方条款和条件
- 所有数据存储在本地，开发者不会收集、上传或访问任何用户数据

## 许可证

MIT License。详见 [LICENSE](LICENSE) 文件。
