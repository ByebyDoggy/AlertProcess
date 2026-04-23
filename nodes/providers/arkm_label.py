"""
ARKM 实体标签 Provider 节点

通过 ARKM Intelligence API 获取地址的实体标签信息。
注入字段到 extra: entity_type, entity_id, entity_name, entity_confidence
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

from nodes.base import NodeRegistry
from nodes.providers.base import BaseContextProviderNode
from nodes.models import TransactionContext

logger = logging.getLogger(__name__)


class ARKMLabelProviderNode(BaseContextProviderNode):
    """
    ARKM 实体标签 Provider 节点。

    通过 ARKM Intelligence API 获取地址实体标签。
    注入字段到 extra:
      - entity_type: 实体类型 (hacker, exchange, defi_protocol, etc.)
      - entity_id: 实体 ID
      - entity_name: 实体名称
      - entity_confidence: 置信度
    """

    name: str = "arkm_label_provider"
    label: str = "ARKM 标签查询"
    description: str = "通过 ARKM Intelligence API 获取地址实体标签，注入 entity_type、entity_name 等字段"
    icon: str = "\U0001f50d"
    color: str = "#7c3aed"

    provides = ["entity_type", "entity_id", "entity_name", "entity_confidence"]

    async def fetch(self, tx_context: TransactionContext) -> dict[str, Any]:
        """
        获取地址实体标签信息。

        策略:
          1. 从 tx_context 提取目标地址
          2. 调用 ARKM API 获取标签
          3. 返回 extra 字段字典
        """
        # 提取地址
        from_addr = tx_context.from_address or ""
        to_addr = tx_context.to_address or ""
        exploiter = tx_context.extra.get("exploiter_address", "") if tx_context.extra else ""

        if exploiter and isinstance(exploiter, str) and exploiter.startswith("0x"):
            target_addr = exploiter.lower()
        elif from_addr and from_addr.startswith("0x"):
            target_addr = from_addr.lower()
        elif to_addr and to_addr.startswith("0x"):
            target_addr = to_addr.lower()
        else:
            return {}

        # 获取 cookie
        cookie = self._get_cookie()
        if not cookie:
            logger.debug("[ARKMLabelProviderNode] No cookie configured, skipping")
            return {}

        return await self._fetch_from_arkm(target_addr, cookie)

    def _get_cookie(self) -> str | None:
        """从配置获取 cookie"""
        try:
            from config.model import settings
            return settings.arkm_cookie
        except Exception:
            return None

    async def _fetch_from_arkm(self, address: str, cookie: str) -> dict[str, Any]:
        """调用 ARKM Intelligence API 获取实体标签"""
        import httpx

        url = f"https://intelligence.arkm.io/api/v1/entity/{address}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url,
                    headers={
                        "accept": "application/json",
                        "cookie": cookie,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            # 解析标签
            entity_type = data.get("entityType") or data.get("type", "")
            entity_id = data.get("entityId") or data.get("id", "")
            entity_name = data.get("entityName") or data.get("name", "")
            confidence = data.get("confidence", "unknown")

            if entity_type:
                return {
                    "entity_type": entity_type,
                    "entity_id": str(entity_id),
                    "entity_name": entity_name,
                    "entity_confidence": confidence,
                }

            return {}

        except httpx.HTTPStatusError as e:
            logger.warning(f"[ARKMLabelProviderNode] API error for {address}: {e.response.status_code}")
            return {"_arkm_label_error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            logger.error(f"[ARKMLabelProviderNode] Unexpected error: {e}", exc_info=True)
            return {"_arkm_label_error": str(e)}


NodeRegistry.register(ARKMLabelProviderNode)
