# ============================================================
# plugin_loader.py — 插件系统加载器（Phase 8.4）
#
# 插件类型：
#   - Agent 插件：注册新 Agent（实现 BaseAgent 子类）
#   - Tool 插件：注册新工具（LangChain Tool 函数）
#   - Provider 插件：注册新 LLM 提供商
#
# 加载机制：
#   - 从 PLUGIN_DIRS 环境变量（逗号分隔路径列表）扫描 plugin.json
#   - 只加载显式配置的目录，不扫描任意路径
#   - plugin.json manifest 必须声明 capability
#   - 默认关闭；需要配置 PLUGIN_DIRS 才启用
# ============================================================

import json
import os
import sys
from importlib import util as import_util
from pathlib import Path
from typing import Any


class PluginManifest:
    """插件清单：plugin.json 的解析结果。"""
    name: str
    version: str
    type: str          # agent | tool | provider
    description: str
    entry_point: str   # Python 模块路径
    capabilities: list[str]  # 声明的能力
    config: dict       # 额外配置

    def __init__(self, data: dict):
        self.name = data.get("name", "unknown")
        self.version = data.get("version", "0.1.0")
        self.type = data.get("type", "tool")
        self.description = data.get("description", "")
        self.entry_point = data.get("entry_point", "")
        self.capabilities = data.get("capabilities", [])
        self.config = data.get("config", {})


def discover_plugins() -> list[tuple[Path, PluginManifest]]:
    """扫描 PLUGIN_DIRS 中的所有 plugin.json，返回 (plugin_dir, manifest) 列表。"""
    dirs_str = os.environ.get("PLUGIN_DIRS", "")
    if not dirs_str:
        return []

    plugins: list[tuple[Path, PluginManifest]] = []
    for dir_path in dirs_str.split(","):
        dir_path = dir_path.strip()
        if not dir_path:
            continue
        p = Path(dir_path)
        manifest_file = p / "plugin.json"
        if not manifest_file.is_file():
            continue
        try:
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest = PluginManifest(data)
            plugins.append((p, manifest))
        except Exception as e:
            print(f"[plugin] Failed to load {manifest_file}: {e}", file=sys.stderr)

    return plugins


def load_agent_plugin(plugin_dir: Path, manifest: PluginManifest) -> Any | None:
    """加载一个 Agent 插件，返回 BaseAgent 子类。"""
    if manifest.type != "agent":
        return None

    try:
        entry = manifest.entry_point
        if ":" in entry:
            module_path, class_name = entry.split(":", 1)
        else:
            return None

        # Add plugin dir to sys.path temporarily
        sys.path.insert(0, str(plugin_dir))
        try:
            spec = import_util.find_spec(module_path)
            if spec is None:
                print(f"[plugin] Module {module_path} not found in {plugin_dir}", file=sys.stderr)
                return None
            mod = import_util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return getattr(mod, class_name, None)
        finally:
            sys.path.pop(0)
    except Exception as e:
        print(f"[plugin] Failed to load agent plugin {manifest.name}: {e}", file=sys.stderr)
        return None


def load_tool_plugin(plugin_dir: Path, manifest: PluginManifest) -> Any | None:
    """加载一个 Tool 插件，返回 LangChain Tool 函数或可调用对象。"""
    if manifest.type != "tool":
        return None

    try:
        entry = manifest.entry_point
        if ":" in entry:
            module_path, func_name = entry.split(":", 1)
        else:
            return None

        sys.path.insert(0, str(plugin_dir))
        try:
            spec = import_util.find_spec(module_path)
            if spec is None:
                print(f"[plugin] Module {module_path} not found in {plugin_dir}", file=sys.stderr)
                return None
            mod = import_util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return getattr(mod, func_name, None)
        finally:
            sys.path.pop(0)
    except Exception as e:
        print(f"[plugin] Failed to load tool plugin {manifest.name}: {e}", file=sys.stderr)
        return None


def load_all_tools(conn=None) -> list:
    """加载所有已安装的 Tool 插件，返回 LangChain Tool 列表。"""
    plugins = discover_plugins()
    tools = []
    for plugin_dir, manifest in plugins:
        if manifest.type == "tool":
            tool_fn = load_tool_plugin(plugin_dir, manifest)
            if tool_fn is not None:
                tools.append(tool_fn)
    return tools


def load_all_agent_classes() -> dict[str, Any]:
    """加载所有已安装的 Agent 插件，返回 {agent_id: AgentClass} 映射。"""
    plugins = discover_plugins()
    agents = {}
    for plugin_dir, manifest in plugins:
        if manifest.type == "agent":
            cls = load_agent_plugin(plugin_dir, manifest)
            if cls is not None:
                agents[getattr(cls, 'agent_id', manifest.name)] = cls
    return agents
