"""
ARKM 实体标签 Provider

通过 ARKM Intelligence API 获取地址的实体标签信息。
注入字段: entity_type, entity_id, entity_name, entity_confidence
"""

from __future__ import annotations

import logging
from typing import Any

from nodes.context.provider import ContextProvider

logger = logging.getLogger(__name__)


class ARKMLabelProvider(ContextProvider):
    """
    ARKM 实体标签提供者。

    注入字段:
      - entity_type: str       — 实体类型 (hacker, exchange, defi_protocol, etc.)
      - entity_id: str         — 实体 ID
      - entity_name: str       — 实体名称
      - entity_confidence: str — 置信度

    API 调用:
      - ARKM Intelligence API 查询地址标签
    """

    name = "arkm_label"
    description = "通过 ARKM Intelligence API 获取地址实体标签"
    provides = ["entity_type", "entity_id", "entity_name", "entity_confidence"]

    def __init__(self, cookie: str | None = None):
        self._cookie = cookie

    @property
    def cookie(self) -> str | None:
        """延迟获取 cookie（从全局配置）"""
        if self._cookie is None:
            try:
                from config.model import settings
                self._cookie = settings.arkm_cookie
            except Exception:
                pass
        return self._cookie

    async def fetch(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        获取地址实体标签信息。

        策略:
          1. 如果 context 中已有 entity_type，跳过
          2. 从 context 提取地址
          3. 调用 ARKM API 获取标签
        """
        # 1. 检查已有数据
        if context.get("entity_type"):
            return {}

        # 2. 提取地址
        addresses = self.extract_addresses(context)
        if not addresses:
            return {}

        # 3. 优先查询 exploiter_address
        target_addr = (
            context.get("exploiter_address", "").lower()
            or addresses[0]
        )

        # 4. 尝试从 ARKM API 获取
        if not self.cookie:
            logger.debug("[ARKMLabel] No cookie configured, skipping")
            return {}

        return await self._fetch_from_arkm(target_addr)

    async def _fetch_from_arkm(self, address: str) -> dict[str, Any]:
        """调用 ARKM Intelligence API 获取实体标签"""
        import httpx

        url = f"https://intelligence.arkm.io/api/v1/entity/{address}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url,
                    headers={
                        "accept": "application/json",
                        "cookie": self.cookie,
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
                    "entity_queried": address,
                }

            return {}

        except httpx.HTTPStatusError as e:
            logger.warning(
                f"[ARKMLabel] API error for {address}: "
                f"{e.response.status_code}"
            )
            return {"_arkm_label_error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            logger.error(f"[ARKMLabel] Unexpected error: {e}", exc_info=True)
            return {"_arkm_label_error": str(e)}
