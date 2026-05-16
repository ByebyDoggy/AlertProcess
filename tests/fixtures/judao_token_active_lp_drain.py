from __future__ import annotations

ATTACK_TX_HASH = "0x956e38b8ddb40ba080c8042c685ae52ee5c1b096f1d7f0c4a6c59be3eb4265bd"
SENDER = "0x5384b34c74024d6563b323351a4bbfa18432161b"
ENTRY_CONTRACT = "0x3b9bc53af5012b12b6886a665bb22382211ae432"
EXECUTOR_CONTRACT = "0x530904b5b5ec86cca0528a682614f57f87e7f079"
JUDAO = "0xf55dff7898930a2d28cdbc39d615b1624ac86888"
JUDAO_LP = "0x5d7b61e91cb59e90f7fae8d0fe2e73976161592f"
MOOLAH_PROXY = "0x8f73b65b4caaf64fba2af91cc5d4a2a1318e5d8c"
PANCAKE_ROUTER = "0x10ed43c718714eb63d5aa57b78b54704e256024e"
USDT = "0x55d398326f99059ff775485246999027b3197955"
WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
NATIVE_BNB = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
DEAD = "0x000000000000000000000000000000000000dead"
FEE = "0x0000000000000000000000000000000000000fee"
REWARD_A = "0xe7b95eaada89a0b2cce3086d5d4d1537d087a6e1"
REWARD_B = "0xccdd127594f24bf3a6ec08e5ea793203a8941540"
REWARD_C = "0x82ea37296171b3f06702b0a6e0671172f79910ba"
ERC1967_PROXY = "0x8599068597fd27d87514cb90c42300c03a474084"

FLASH_LOAN_RAW = 2_295_723_159_642_210_185_991_283
LP_TO_EXECUTOR_JUDAO_RAW = 5_473_557_853_503_254_662_548_079
LP_TO_JUDAO_RAW = 3_019_432_906_656_452_109_766_422
LP_TO_DEAD_JUDAO_RAW = 3_019_432_906_656_452_109_766_424
JUDAO_TO_LP_RAW = 389_206_461_086_932_694_355_629
EXECUTOR_TO_LP_JUDAO_RAW = 5_198_393_287_782_908_758_112_995
LP_TO_EXECUTOR_USDT_RAW = 2_523_596_497_552_140_965_784_945
EXECUTOR_TO_SENDER_USDT_RAW = 205_259_490_762_457_026_328_485
SENDER_BNB_RAW = 36_000_000_000_000_000_000

JUDAO_PRICE = 0.286
USDT_PRICE = 1.0
BNB_PRICE = 626.77


def _transfer(token: str, from_addr: str, to_addr: str, amount_raw: int) -> dict:
    return {
        "token": token,
        "from": from_addr,
        "to": to_addr,
        "amount_raw": str(amount_raw),
    }


def _call(caller: str, callee: str, selector: str, operation: str = "CALL") -> dict:
    return {
        "caller": caller,
        "callee": callee,
        "selector": selector,
        "operation": operation,
    }


def build_judao_context() -> dict:
    return {
        "chain_id": 56,
        "tx_hash": ATTACK_TX_HASH,
        "from_address": SENDER,
        "to_address": ENTRY_CONTRACT,
        "value": 0,
        "transfers": [
            _transfer(USDT, MOOLAH_PROXY, EXECUTOR_CONTRACT, FLASH_LOAN_RAW),
            _transfer(USDT, EXECUTOR_CONTRACT, JUDAO_LP, FLASH_LOAN_RAW),
            _transfer(JUDAO, JUDAO_LP, EXECUTOR_CONTRACT, LP_TO_EXECUTOR_JUDAO_RAW),
            _transfer(JUDAO, JUDAO_LP, JUDAO, LP_TO_JUDAO_RAW),
            _transfer(JUDAO, JUDAO_LP, DEAD, LP_TO_DEAD_JUDAO_RAW),
            _transfer(JUDAO, JUDAO, JUDAO_LP, JUDAO_TO_LP_RAW),
            _transfer(JUDAO, EXECUTOR_CONTRACT, JUDAO_LP, EXECUTOR_TO_LP_JUDAO_RAW),
            _transfer(USDT, JUDAO_LP, EXECUTOR_CONTRACT, LP_TO_EXECUTOR_USDT_RAW),
            _transfer(USDT, EXECUTOR_CONTRACT, MOOLAH_PROXY, FLASH_LOAN_RAW),
            _transfer(USDT, EXECUTOR_CONTRACT, SENDER, EXECUTOR_TO_SENDER_USDT_RAW),
            _transfer(NATIVE_BNB, PANCAKE_ROUTER, SENDER, SENDER_BNB_RAW),
            _transfer(USDT, JUDAO, REWARD_A, 10_106_292_909_056_116_654_102),
            _transfer(USDT, JUDAO, REWARD_B, 44_864_746_539_606_315_267_924),
            _transfer(USDT, JUDAO, REWARD_C, 54_971_039_448_662_431_922_027),
            _transfer(USDT, JUDAO, ERC1967_PROXY, 126_390_017_945_602_680_958_641),
        ],
        "trace_calls": [
            _call(SENDER, ENTRY_CONTRACT, "", "CREATE"),
            _call(ENTRY_CONTRACT, EXECUTOR_CONTRACT, "", "CREATE"),
            _call(EXECUTOR_CONTRACT, JUDAO, "0x0dfe1681", "STATICCALL"),
            _call(EXECUTOR_CONTRACT, MOOLAH_PROXY, "0xe0232b42"),
            _call(EXECUTOR_CONTRACT, PANCAKE_ROUTER, "0x38ed1739"),
            _call(PANCAKE_ROUTER, JUDAO_LP, "0x0902f1ac", "STATICCALL"),
            _call(PANCAKE_ROUTER, JUDAO_LP, "0x022c0d9f"),
            _call(JUDAO, PANCAKE_ROUTER, "0x38ed1739"),
            _call(JUDAO, JUDAO_LP, "0x0902f1ac", "STATICCALL"),
            _call(JUDAO, USDT, "0xa9059cbb"),
            _call(JUDAO, JUDAO_LP, "0x022c0d9f"),
            _call(EXECUTOR_CONTRACT, PANCAKE_ROUTER, "0x18cbafe5"),
            _call(PANCAKE_ROUTER, JUDAO_LP, "0x0902f1ac", "STATICCALL"),
            _call(PANCAKE_ROUTER, JUDAO_LP, "0x022c0d9f"),
        ],
        "top_profit_address": JUDAO,
        "top_loss_address": JUDAO_LP,
        "token_prices": {
            JUDAO: JUDAO_PRICE,
            USDT: USDT_PRICE,
            WBNB: BNB_PRICE,
            NATIVE_BNB: BNB_PRICE,
        },
        "token_decimals": {
            JUDAO: 18,
            USDT: 18,
            WBNB: 18,
            NATIVE_BNB: 18,
        },
        "address_labels": {
            JUDAO_LP: "PancakeSwap JUDAO-USDT Cake-LP Pair",
            PANCAKE_ROUTER: "PancakeSwap Router v2",
            MOOLAH_PROXY: "ListaDAO Moolah Proxy",
            JUDAO: "JUDAO Token",
        },
        "stablecoins": [USDT],
        "wrapped_native_tokens": [WBNB, NATIVE_BNB],
        "flash_loan_present": True,
        "temporary_contract_count": 2,
    }


def build_normal_fee_token_context() -> dict:
    fee_token = "0x1111111111111111111111111111111111111111"
    lp = "0x2222222222222222222222222222222222222222"
    user = "0x3333333333333333333333333333333333333333"
    router = PANCAKE_ROUTER

    return {
        "chain_id": 56,
        "tx_hash": "0xnormalfeetokenswap",
        "from_address": user,
        "to_address": router,
        "value": 0,
        "transfers": [
            _transfer(USDT, user, lp, 1_000_000_000_000_000_000_000),
            _transfer(fee_token, lp, user, 900_000_000_000_000_000_000),
            _transfer(fee_token, lp, fee_token, 20_000_000_000_000_000_000),
            _transfer(fee_token, fee_token, lp, 10_000_000_000_000_000_000),
        ],
        "trace_calls": [
            _call(router, lp, "0x0902f1ac", "STATICCALL"),
            _call(router, lp, "0x022c0d9f"),
        ],
        "top_profit_address": user,
        "top_loss_address": lp,
        "token_prices": {fee_token: 0.01, USDT: USDT_PRICE},
        "token_decimals": {fee_token: 18, USDT: 18},
        "address_labels": {lp: "PancakeSwap fee-token pair"},
        "stablecoins": [USDT],
        "wrapped_native_tokens": [WBNB, NATIVE_BNB],
        "flash_loan_present": False,
        "temporary_contract_count": 0,
    }
