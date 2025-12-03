from typing import Any
from database import SessionLocal
from pydantic import BaseModel
from logging import getLogger
class ProcessedResult(BaseModel):
    need_more_check: bool = True
    score: float = 0.0
    process_details: list[dict[str, Any]] = []


class AlertInput(BaseModel):
    chain_id: int
    attacked_address: str
    exploiter_address: str
    tx_hash: str



logger = getLogger(__name__)



class AlertProcessorConfig(BaseModel):
    processor_name:str

class AlertProcessor:
    def __init__(self, config: AlertProcessorConfig):
        self.db = SessionLocal()
        self.config = config

    def on_error(self, error: Exception):
        logger.error(f"Error in {self.config.processor_name}: {error}")
        return ProcessedResult(
            need_more_check=False,
            score=1000,
            process_details=[{
                "reason": f"error in {self.config.processor_name}: {error}",
            }],
        )

    async def _process_alert(self, alert:AlertInput) -> ProcessedResult:
        raise NotImplementedError( "Subclasses must implement _process_alert method")

    async def process_alert(self, alert:AlertInput) -> ProcessedResult:
        try:
            result = await self._process_alert(alert)
            result.process_details[0]['processor_name'] = self.config.processor_name
            logger.info(f"Alert processed by {self.config.processor_name}: {result}")
            return result
        except Exception as e:
            return self.on_error(e)
