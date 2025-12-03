from typing import Literal
from database.models import ContractAddressDB
from processor.core import AlertProcessor, AlertProcessorConfig,ProcessedResult
from processor.core import AlertInput
from arkm import AsyncArkmClient, SyncArkmClient

ChainIDToARKMNetwork = {
    1: "ethereum",
    56: "bsc",
    137: "polygon",
}

# 检测规则，检查利用者是否是可信实体，若为可信实体直接通过，跳过后续检测(对于arkm实体，除了hacker其余实体均可信)

class VictimARKMLabelCheckAlertProcessorConfig(AlertProcessorConfig):
    ignored_entity_types: list[str] = ['hacker']
    processor_name: str = "VictimARKMLabelCheckAlertProcessor"
    arkm_cookie: str

class VictimARKMLabelCheckAlertProcessor(AlertProcessor):
    def __init__(self,config: VictimARKMLabelCheckAlertProcessorConfig):
        super().__init__(config)
        self.arkm_client = AsyncArkmClient(
            cookie=config.arkm_cookie
        )
        self.arkm_sync_client = SyncArkmClient(
            cookie=config.arkm_cookie
        )
        self.config: VictimARKMLabelCheckAlertProcessorConfig = config

    async def _process_alert(self, alert:AlertInput):
        # 优先尝试从本地数据库查找
        arkm_entity_type = None
        contract_entity =self.db.query(
            ContractAddressDB
        ).where(
            ContractAddressDB.contract_address == alert.exploiter_address
        ).first()
        if contract_entity:
            arkm_entity_type = contract_entity.entity_type
        else:
            response = self.arkm_sync_client.get(
                path=f"/intelligence/address_enriched/{alert.exploiter_address}/all?includeTags=true&includeEntityPredictions=true&includeClusters=true"
            )
            for arkm_chain, chain_data in response.items():
                if arkm_chain == ChainIDToARKMNetwork[alert.chain_id]:
                    arkm_entity = chain_data.get("arkhamEntity")
                    if arkm_entity:
                        arkm_entity_type = arkm_entity.get("type")

        if arkm_entity_type:
            # 若实体类型不在黑名单中，直接通过
            if arkm_entity_type in self.config.ignored_entity_types:
                return ProcessedResult(
                    need_more_check=False,
                    process_details=[{
                        "entity_type": arkm_entity_type,
                        "reason": f"entity type {arkm_entity_type} is in ignored entity list",
                    }]
                )
            else:
                # 若实体类型在黑名单中，返回-1
                return ProcessedResult(
                    need_more_check=True,
                    process_details=[{
                        "entity_type": arkm_entity_type,
                        "reason": f"exploiter is not a entity or"
                                  f" entity type {arkm_entity_type} is in ignored entity list"
                    }]
                )
        else:
            return ProcessedResult(
                need_more_check=True,
                process_details=[{
                    "entity_type": arkm_entity_type,
                    "reason": f"victim is not a entity, normal user or not tagged entity wallet",
                }],
                score=0
            )
