#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local AI Agent Bridge - 轻量级 AI 桥接服务器

一款极简的本地 AI 桥接服务器，通过 HTTP API 接收用户请求，
包装为预设的 prompt 模板，存储到本地文件供 AI 工具读取，
并将 AI 的响应返回给用户。支持多用户数据隔离、会话记录、
自动配置初始化等功能。零外部依赖，仅需 Python 3.8+。

Author: Local AI Agent Bridge Contributors
License: MIT
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import stat
import sys
import time
import traceback
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs

# ─── 日志配置 ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BridgeServer")

# ─── 默认配置 ───────────────────────────────────────────────
DEFAULT_CONFIG: Dict[str, Any] = {
    "port": 5000,
    "cache_folder": "./cache",
    "endpoint": "/bridge/messages",
    "wrapper_template": (
        "你现在是一个高级AI执行器，请严格按照以下用户指令执行任务。\n\n"
        "### 用户指令\n{user_message}\n\n"
        "### 执行要求\n"
        "1. 根据用户指令，完整、准确地完成所需的工作。\n"
        "2. 只输出最终结果，不要输出任何解释、问候或额外文字。\n"
        "3. 如果用户指令要求输出代码，只输出纯代码，不要用 markdown 代码块包裹，除非明确要求。\n"
        "4. 如果无法完成，输出\"ERROR: 无法完成\"并说明原因，但仍然不要输出其它内容。\n\n"
        "现在请开始执行。"
    ),
    "multi_user": False,
    "user_data_folder": "./user_data",
    "save_sessions": False,
    "session_folder": "./sessions",
    "clear_cache_on_start": True,
}

CONFIG_FALLBACKS: Dict[str, Any] = {
    "port": 5000,
    "cache_folder": "./cache",
    "endpoint": "/bridge/messages",
    "wrapper_template": DEFAULT_CONFIG["wrapper_template"],
    "multi_user": False,
    "user_data_folder": "./user_data",
    "save_sessions": False,
    "session_folder": "./sessions",
    "clear_cache_on_start": True,
}

RUN_SH_CONTENT = """#!/bin/bash
cd "$(dirname "$0")"
python3 bridge_server.py
"""

RUN_BAT_CONTENT = """@echo off
cd /d "%~dp0"
python bridge_server.py
pause
"""


# ─── 工具函数 ───────────────────────────────────────────────

def get_base_dir() -> Path:
    """获取脚本所在目录作为项目根目录。

    Returns:
        Path: 项目根目录的绝对路径。
    """
    return Path(__file__).resolve().parent


def ensure_dir(path: Path) -> None:
    """确保目录存在，不存在则创建。

    Args:
        path: 目标目录路径。
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error("创建目录失败 %s: %s", path, e)


def clear_directory(path: Path) -> None:
    """清空目录内容（保留目录自身）。

    Args:
        path: 目标目录路径。
    """
    if not path.exists():
        return
    try:
        for item in path.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except OSError as e:
                logger.warning("清理失败 %s: %s", item, e)
        logger.info("已清空目录: %s", path)
    except OSError as e:
        logger.error("遍历目录失败 %s: %s", path, e)


# ─── 配置管理 ───────────────────────────────────────────────

def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """加载配置文件，缺失项使用安全默认值并打印警告。

    首次运行时若 config.json 不存在，自动创建并写入默认值。

    Args:
        config_path: 配置文件路径，默认为项目根目录下的 config.json。

    Returns:
        配置字典，所有键均已被填充。
    """
    if config_path is None:
        config_path = get_base_dir() / "config.json"

    config: Dict[str, Any] = {}

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                config.update(loaded)
            logger.info("已加载配置文件: %s", config_path)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("配置文件读取失败 (%s)，将使用默认值", e)
    else:
        logger.info("配置文件不存在，正在创建默认配置...")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
            logger.info("默认配置已写入: %s", config_path)
            return dict(DEFAULT_CONFIG)
        except OSError as e:
            logger.error("无法创建配置文件 (%s)，使用内存默认值", e)
            return dict(DEFAULT_CONFIG)

    # 容错：缺失项用安全默认值
    for key, fallback in CONFIG_FALLBACKS.items():
        if key not in config:
            logger.warning("配置缺失 '%s'，使用默认值: %s", key, fallback)
            config[key] = fallback

    return config


# ─── 启动脚本生成 ───────────────────────────────────────────

def generate_run_scripts(base_dir: Path) -> None:
    """首次运行时检测并自动生成 run.sh 和 run.bat。

    对 run.sh 在 POSIX 系统上自动执行 chmod +x。

    Args:
        base_dir: 项目根目录。
    """
    run_sh = base_dir / "run.sh"
    run_bat = base_dir / "run.bat"

    if not run_sh.exists():
        try:
            with open(run_sh, "w", encoding="utf-8", newline="\n") as f:
                f.write(RUN_SH_CONTENT)
            logger.info("已生成 run.sh")
            if platform.system() != "Windows":
                try:
                    os.chmod(run_sh, os.stat(run_sh).st_mode | stat.S_IEXEC)
                except OSError:
                    pass
        except OSError as e:
            logger.error("生成 run.sh 失败: %s", e)

    if not run_bat.exists():
        try:
            with open(run_bat, "w", encoding="utf-8", newline="\r\n") as f:
                f.write(RUN_BAT_CONTENT)
            logger.info("已生成 run.bat")
        except OSError as e:
            logger.error("生成 run.bat 失败: %s", e)


# ─── 用户识别 ───────────────────────────────────────────────

def resolve_user_id(
    config: Dict[str, Any],
    headers: Dict[str, str],
    query_params: Dict[str, str],
) -> str:
    """根据配置和请求解析当前用户 ID。

    多用户模式下通过 X-User-ID 请求头或 user URL 参数识别，
    未提供时默认 "default"。单用户模式始终返回 "default"。

    注意：此模式无鉴权，仅适合本地信任环境。

    Args:
        config: 应用配置。
        headers: 请求头字典（键为小写）。
        query_params: URL 查询参数字典。

    Returns:
        用户 ID 字符串。
    """
    if not config.get("multi_user", False):
        return "default"

    user_id = headers.get("x-user-id", "").strip()
    if not user_id:
        user_id = query_params.get("user", "default").strip()
    if not user_id:
        user_id = "default"

    # 安全检查：防止路径遍历
    if ".." in user_id or "/" in user_id or "\\" in user_id:
        logger.warning("检测到非法用户 ID，回退为 default")
        user_id = "default"

    return user_id


# ─── 会话记录 ───────────────────────────────────────────────

def save_session_record(
    config: Dict[str, Any],
    user_id: str,
    request_body: Dict[str, Any],
    response_body: Dict[str, Any],
) -> None:
    """将一次完整交互保存为 JSON 会话文件。

    Args:
        config: 应用配置。
        user_id: 用户 ID。
        request_body: 原始请求体。
        response_body: 响应体。
    """
    if not config.get("save_sessions", False):
        return

    session_dir = get_base_dir() / config.get("session_folder", "./sessions") / user_id
    ensure_dir(session_dir)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    session_file = session_dir / f"{timestamp}.json"

    record: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "request": request_body,
        "response": response_body,
    }

    try:
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        logger.info("会话已保存 (user=%s)", user_id)
    except OSError as e:
        logger.error("保存会话失败: %s", e)


# ─── HTTP 请求处理器 ────────────────────────────────────────

class BridgeHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器，处理 AI 桥接请求。

    支持 GET（状态查询）、POST（消息桥接）和 OPTIONS（CORS）。
    日志中仅记录请求元数据，不记录完整用户输入内容。
    """

    config: Dict[str, Any] = {}

    def log_message(self, format: str, *args: Any) -> None:
        """重写日志方法，脱敏处理——不输出完整用户输入。"""
        logger.info(
            "%s - %s [%s] - body_len=%s",
            self.client_address[0],
            self.command,
            self.path,
            getattr(self, "_body_len", "N/A"),
        )

    def _send_json(self, status: int, data: Dict[str, Any]) -> None:
        """发送 JSON 响应。

        Args:
            status: HTTP 状态码。
            data: 响应数据字典。
        """
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        """读取请求体。

        Returns:
            原始请求体字节。
        """
        content_len = int(self.headers.get("Content-Length", 0))
        self._body_len = content_len  # type: ignore[attr-defined]
        if content_len > 0:
            return self.rfile.read(content_len)
        return b""

    def do_OPTIONS(self) -> None:
        """处理 CORS 预检请求。"""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-User-ID")
        self.end_headers()

    def do_GET(self) -> None:
        """处理 GET 请求，返回服务器状态。"""
        parsed = urlparse(self.path)
        if parsed.path in ("/health", "/"):
            self._send_json(200, {
                "status": "running",
                "service": "Local AI Agent Bridge",
                "multi_user": self.config.get("multi_user", False),
                "save_sessions": self.config.get("save_sessions", False),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        """处理 POST 请求，执行 AI 消息桥接。

        流程：接收消息 → 包装模板 → 写入 request.txt →
        轮询等待 response.txt → 返回 AI 响应。
        """
        parsed = urlparse(self.path)
        endpoint: str = self.config.get("endpoint", "/bridge/messages")

        if parsed.path != endpoint:
            self._send_json(404, {"error": f"Not found. Use {endpoint}"})
            return

        # 解析查询参数
        query_params: Dict[str, str] = {}
        for k, v in parse_qs(parsed.query).items():
            query_params[k] = v[0] if v else ""

        # 收集请求头（小写）
        headers_lower: Dict[str, str] = {}
        for k, v in self.headers.items():
            headers_lower[k.lower()] = v

        user_id = resolve_user_id(self.config, headers_lower, query_params)

        # 读取请求体
        try:
            raw_body = self._read_body()
            try:
                body_json: Dict[str, Any] = json.loads(raw_body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                body_json = {"raw": raw_body.decode("utf-8", errors="replace")}
        except Exception as e:
            logger.error("读取请求体失败: %s", e)
            self._send_json(400, {"error": "Bad request body"})
            return

        # 提取用户消息
        user_message = body_json.get("message", body_json.get("text", ""))
        if not user_message and isinstance(body_json.get("raw"), str):
            user_message = body_json["raw"]

        logger.info(
            "收到请求 - user=%s, msg_len=%d, ip=%s",
            user_id, len(str(user_message)), self.client_address[0],
        )

        # 包装模板
        template: str = self.config.get("wrapper_template", DEFAULT_CONFIG["wrapper_template"])
        wrapped = template.replace("{user_message}", str(user_message))

        # 用户目录
        user_data = self.config.get("user_data_folder", "./user_data")
        user_dir = get_base_dir() / user_data / user_id
        ensure_dir(user_dir)

        request_file = user_dir / "request.txt"
        response_file = user_dir / "response.txt"

        # 写入 request.txt
        try:
            with open(request_file, "w", encoding="utf-8") as f:
                f.write(wrapped)
            logger.info("已写入 request.txt (user=%s, len=%d)", user_id, len(wrapped))
        except OSError as e:
            logger.error("写入 request.txt 失败: %s", e)
            self._send_json(500, {"error": "Failed to write request file"})
            return

        # 清空旧响应
        if response_file.exists():
            try:
                with open(response_file, "w", encoding="utf-8") as f:
                    f.write("")
            except OSError:
                pass

        # 轮询等待响应（最长 300 秒）
        timeout = 300.0
        poll_interval = 0.5
        elapsed = 0.0
        response_text = ""

        while elapsed < timeout:
            try:
                if response_file.exists():
                    with open(response_file, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if content:
                        response_text = content
                        break
            except OSError as e:
                logger.error("读取 response.txt 失败: %s", e)

            time.sleep(poll_interval)
            elapsed += poll_interval

        if not response_text:
            logger.warning("等待 AI 响应超时 (user=%s, elapsed=%.1fs)", user_id, elapsed)
            self._send_json(408, {
                "error": "Timeout waiting for AI response",
                "hint": "请确保 AI 工具已将响应写入 response.txt",
            })
            return

        response_data: Dict[str, Any] = {
            "response": response_text,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # 保存会话
        save_session_record(self.config, user_id, body_json, response_data)

        logger.info("响应就绪 - user=%s, resp_len=%d", user_id, len(response_text))
        self._send_json(200, response_data)


# ─── 服务器启动 ─────────────────────────────────────────────

def run_server() -> None:
    """启动 AI 桥接服务器，执行完整初始化流程。

    1. 加载/创建配置
    2. 生成启动脚本
    3. 清理/创建缓存与数据目录
    4. 启动 HTTP 服务器
    """
    base_dir = get_base_dir()
    config = load_config()

    logger.info("=" * 50)
    logger.info("Local AI Agent Bridge 启动中...")
    logger.info("项目目录: %s", base_dir)
    logger.info("监听端口: %s", config["port"])
    logger.info("API 端点: %s", config["endpoint"])
    logger.info("多用户模式: %s", "开启" if config.get("multi_user") else "关闭")
    logger.info("会话记录: %s", "开启" if config.get("save_sessions") else "关闭")
    logger.info("=" * 50)

    # 生成启动脚本
    generate_run_scripts(base_dir)

    # 缓存目录
    cache_dir = base_dir / str(config.get("cache_folder", "./cache"))
    if config.get("clear_cache_on_start", True):
        clear_directory(cache_dir)
    ensure_dir(cache_dir)

    # 用户数据目录
    user_data_dir = base_dir / str(config.get("user_data_folder", "./user_data"))
    ensure_dir(user_data_dir)

    # 会话目录
    if config.get("save_sessions", False):
        session_dir = base_dir / str(config.get("session_folder", "./sessions"))
        ensure_dir(session_dir)

    # 注入配置到 Handler
    BridgeHandler.config = config

    # 启动服务器
    port: int = int(config.get("port", 5000))
    server = HTTPServer(("0.0.0.0", port), BridgeHandler)

    logger.info("服务器已启动: http://localhost:%d%s", port, config["endpoint"])
    logger.info("健康检查: http://localhost:%d/health", port)
    logger.info("按 Ctrl+C 停止服务器")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务器正在关闭...")
        server.shutdown()
        logger.info("服务器已停止")


if __name__ == "__main__":
    try:
        run_server()
    except Exception as e:
        logger.critical("服务器异常退出: %s\n%s", e, traceback.format_exc())
        sys.exit(1)
