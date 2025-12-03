from web3 import Web3

from processor.core import AlertProcessor, AlertProcessorConfig, ProcessedResult
from processor.core import AlertInput

# 检测交易手续费 若超过100美金认为是异常转账
GasPriceThresholdInUSD = 100000000 # 100美金

ChainIDToNativeTokenPrice = {
    1: 2000, # ETH
    56: 700, # BNB
}

class GasPriceCheckConfig(AlertProcessorConfig):
    processor_name:str = "TransactionGasPriceCheckAlertProcessor"
    chain_id_to_provider_url: dict

class TransactionGasPriceCheckAlertProcessor(AlertProcessor):
    def __init__(self, config: GasPriceCheckConfig):
        super().__init__(config)
        self.config = config

    async def _process_alert(self, alert:AlertInput) -> ProcessedResult:
        web3 = Web3(Web3.HTTPProvider(self.config.chain_id_to_provider_url[alert.chain_id]))
        gas_price = web3.eth.gas_price
        gas_price_in_usd = gas_price / 10**18 * ChainIDToNativeTokenPrice[alert.chain_id]
        if gas_price_in_usd > GasPriceThresholdInUSD:
            return ProcessedResult(
                need_more_check=False,
                score=500,
                process_details=[{
                    "gas_price": gas_price,
                    "gas_price_in_usd": gas_price_in_usd,
                    "risk_reason": f"gas_price_in_usd({gas_price_in_usd}) > "
                                   f"GasPriceThresholdInUSD({GasPriceThresholdInUSD})"
                                   f"It is a suspicious high gas price, please check it.",
                }],
            )
        return ProcessedResult(
            need_more_check=False,
            score=0.0,
            process_details=[{
                "gas_price": gas_price,
            }],
        )
