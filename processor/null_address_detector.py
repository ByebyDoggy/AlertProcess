from typing import Literal
from database.models import ContractAddressDB
from processor.core import AlertProcessor, AlertProcessorConfig,ProcessedResult
from processor.core import AlertInput
from arkm import AsyncArkmClient, SyncArkmClient

NULL_ADDRESS = "0x0000000000000000000000000000000000000000"
# 检测规则，检查利用者是否是可信实体，若为可信实体直接通过，跳过后续检测(对于arkm实体，除了hacker其余实体均可信)

class VictimNULLAddressAlertProcessorConfig(AlertProcessorConfig):
    processor_name: str = "VictimNULLAddressAlertProcessor"

class VictimNULLAddressAlertProcessor(AlertProcessor):
    def __init__(self,config: VictimNULLAddressAlertProcessorConfig):
        super().__init__(config)
        self.arkm_client = AsyncArkmClient(
            cookie=config.arkm_cookie
        )
        self.arkm_sync_client = SyncArkmClient(
            cookie=config.arkm_cookie
        )
        self.config: VictimNULLAddressAlertProcessorConfig = config

    async def _process_alert(self, alert:AlertInput):
        # 优先尝试从本地数据库查找
        if alert.attacked_address == NULL_ADDRESS:
            return ProcessedResult(
                need_more_check=False,
                process_details=[{
                    "entity_type": "victim",
                    "reason": f"victim address is NULL_ADDRESS,it would "
                              f"be a suspicious mint.",
                }],
                score=500
            )


