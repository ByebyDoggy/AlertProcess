"""动作节点模块"""
from nodes.actions.base import BaseAction
from nodes.actions.set_severity import SetSeverityAction
from nodes.actions.add_tag import AddTagAction
from nodes.actions.notify_webhook import NotifyWebhookAction
from nodes.actions.notify_telegram import NotifyTelegramAction
from nodes.actions.update_database import UpdateDatabaseAction

__all__ = [
    "BaseAction",
    "SetSeverityAction",
    "AddTagAction",
    "NotifyWebhookAction",
    "NotifyTelegramAction",
    "UpdateDatabaseAction",
]
