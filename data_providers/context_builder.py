"""
Transaction Context Builder
Builds TransactionContext from AlertInput by fetching full tx data via web3
"""
from typing import Any
from models import AlertInput, TransactionContext
from web3 import Web3
from datetime import datetime


class TransactionContextBuilder:
    """
    Builds TransactionContext from AlertInput by fetching
    transaction details from the blockchain
    """
    
    def __init__(self, chain_id_to_provider_url: dict[int, str]):
        self.chain_id_to_provider_url = chain_id_to_provider_url
        self._web3_instances: dict[int, Web3] = {}
    
    def get_web3(self, chain_id: int) -> Web3 | None:
        """Get or create web3 instance for chain"""
        if chain_id not in self._web3_instances:
            provider_url = self.chain_id_to_provider_url.get(chain_id)
            if provider_url:
                try:
                    self._web3_instances[chain_id] = Web3(Web3.HTTPProvider(provider_url))
                except Exception:
                    return None
        return self._web3_instances.get(chain_id)
    
    async def build(self, alert: AlertInput) -> TransactionContext:
        """
        Build full TransactionContext from AlertInput
        
        Fetches transaction data from the chain and populates
        the TransactionContext with all available information.
        """
        web3 = self.get_web3(alert.chain_id)
        
        if not web3:
            # Return minimal context if web3 not available
            return TransactionContext(
                chain_id=alert.chain_id,
                tx_hash=alert.tx_hash,
                attacked_address=alert.attacked_address,
                exploiter_address=alert.exploiter_address
            )
        
        try:
            # Fetch transaction
            tx = web3.eth.get_transaction(alert.tx_hash)
            tx_dict = dict(tx)
            
            # Fetch receipt for gas_used and logs
            receipt = web3.eth.get_transaction_receipt(alert.tx_hash)
            receipt_dict = dict(receipt)
            
            # Fetch block for timestamp
            block = web3.eth.get_block(tx.blockNumber)
            
            # Build context
            context = TransactionContext(
                chain_id=alert.chain_id,
                tx_hash=alert.tx_hash,
                block_number=tx.blockNumber,
                from_address=tx_dict.get('from'),
                to_address=tx_dict.get('to'),
                value=tx_dict.get('value', 0),
                gas_price=tx_dict.get('gasPrice'),
                gas_limit=tx_dict.get('gas'),
                gas_used=receipt_dict.get('gasUsed'),
                timestamp=datetime.fromtimestamp(block.timestamp),
                input_data=tx_dict.get('input', ''),
                nonce=tx_dict.get('nonce'),
                r=tx_dict.get('r'),
                s=tx_dict.get('s'),
                v=tx_dict.get('v'),
                raw_tx=tx_dict,
                attacked_address=alert.attacked_address,
                exploiter_address=alert.exploiter_address
            )
            
            # Auto-fill attacked/exploiter if not provided
            if not context.attacked_address:
                context.attacked_address = context.to_address
            if not context.exploiter_address:
                context.exploiter_address = context.from_address
            
            return context
            
        except Exception as e:
            # Return minimal context on error
            return TransactionContext(
                chain_id=alert.chain_id,
                tx_hash=alert.tx_hash,
                attacked_address=alert.attacked_address,
                exploiter_address=alert.exploiter_address
            )
