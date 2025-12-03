from processor.core import AlertProcessor, ProcessedResult, AlertProcessorConfig
from processor.core import AlertInput


class ChainedProcessorConfig(AlertProcessorConfig):
    model_config = {
        "arbitrary_types_allowed": True  # 添加这一行允许Pydantic使用任意类型
    }
    processor_name: str = "ChainedProcessor"
    processors: list[AlertProcessor] = []

class ChainedAlertProcessor(AlertProcessor):
    async def _process_alert(self, alert: AlertInput) -> ProcessedResult:
        details_result_list = []
        score = 0.0
        for processor in self.processors:
            try:
                result = await processor._process_alert(alert)
                score += result.score
            except:
                import traceback
                traceback.print_exc()
                raise
            details_result_list.extend(result.process_details)
            if not result.need_more_check:
                return ProcessedResult(need_more_check=False, score=score, process_details=details_result_list)
        return ProcessedResult(need_more_check=False, score=score, process_details=details_result_list)

    def __init__(self, config: ChainedProcessorConfig):
        super().__init__(config)
        self.processors = config.processors