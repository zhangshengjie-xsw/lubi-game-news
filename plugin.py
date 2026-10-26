"""按 plugin_template 的 BasePlugin + LifecycleBindingRequest 方式装配。"""

from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.base.mount_point_types import LifecycleBindingRequest
from src.plugin_system.base.hook_contracts import before_reply_context

from .commands import GameNewsCommand


class GameNewsPlugin(BasePlugin):
    config_file_name = "config.toml"
    config_schema = {"news": {"count": 3, "max_age_hours": 48, "cache_minutes": 15, "include_summary": True}}
    component_display_titles = {"news": "游戏新闻台"}
    component_display_tables = {
        "news": {
            "新闻来源": {
                "title": "标题",
                "published": "发布时间",
                "source": "来源",
                "url": "原文链接",
                "summary": "RSS 摘要",
            }
        }
    }

    @staticmethod
    def validate_config(config):
        section = config.get("news", {})
        if type(section.get("include_summary", True)) is not bool:
            raise ValueError("news.include_summary 必须是布尔值")
        for key, low, high in (("count", 1, 3), ("max_age_hours", 1, 168), ("cache_minutes", 1, 60)):
            value = section.get(key, {"count": 3, "max_age_hours": 48, "cache_minutes": 15}[key])
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"news.{key} 必须是 {low}—{high} 之间的整数")

    def build_lifecycle_bindings(self):
        return (
            LifecycleBindingRequest(
                point_id=before_reply_context.BEFORE_REPLY_CONTEXT_DEFINITION.point_id,
                component=GameNewsCommand(),
            ),
        )
