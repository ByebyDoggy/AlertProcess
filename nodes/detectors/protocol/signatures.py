"""
函数签名注册表 — 统一维护协议攻击相关的已知函数选择器。

按攻击类型分组，供各协议攻击检测器引用。

函数选择器 = keccak256(signature)[:4]，如:
  keccak256("flash(uint256,uint256,uint256,address)") = 0x0906f8c8...
  选择器 = 0x0906f8c8
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# 闪电贷相关函数签名
# ---------------------------------------------------------------------------

FLASH_LOAN_SIGNATURES: dict[str, str] = {
    # Aave V2/V3
    "0x0906f8c8": "flash(address,uint256,uint256,uint256,address)",
    "0x5c7d2920": "flashLoan(address,address,uint256,uint256)",
    # dYdX
    "0xab9c4b5d": "initiateFlashLoan(address,address,uint256,bytes)",
    # Uniswap V2/V3
    "0x016602d8": "flashswap(uint256,uint256,address,bytes)",
    "0xa5c680e2": "flash(address,uint256,uint256,bytes)",
    # Balancer
    "0x0e2c3b4e": "flash(address,uint256,uint256)",
    # MakerDAO
    "0x2a2d80d1": "flash(address,uint256,bytes)",
}

# 闪电贷回调函数（攻击者合约中被协议调用的回调）
FLASH_LOAN_CALLBACK_SIGNATURES: dict[str, str] = {
    "0xaf0526a4": "executeOperation(address,uint256,uint256,address,bytes)",
    "0x23e4f85a": "callFunction(address,bytes32,bytes)",
    "0xd0948a6d": "uniswapV2Call(address,uint256,uint256,bytes)",
    "0x3f97f6c9": "uniswapV3FlashCallback(uint256,uint256,bytes)",
    "0x3af9e3a3": "balancerFlashLoan(address,uint256,uint256,bytes)",
}

FLASH_LOAN_EXPLOIT_SIGNATURES: dict[str, str] = {
    "0x38ed1739": "swapExactTokensForTokens(uint256,uint256,address[],address,uint256)",
    "0x8803dbee": "swapTokensForExactTokens(uint256,uint256,address[],address,uint256)",
    "0xe449022e": "swapExactTokensForTokensSupportingFeeOnTransferTokens(uint256,uint256,address[],address,uint256)",
    "0x7ff36ab5": "swapExactETHForTokens(uint256,address[],address,uint256)",
    "0x18cbafe5": "swapExactTokensForETH(uint256,uint256,address[],address,uint256)",
    "0xdb006a75": "borrow(uint256)",
    "0x852a12e3": "borrow(address,uint256)",
    "0xc5c2b2fd": "borrow(address,uint256,uint256,uint16,address)",
    "0x96cd4ddb": "liquidationCall(address,address,address,uint256,bool)",
    "0xc5ebeaec": "liquidate(address,uint256)",
    "0xa9059cbb": "transfer(address,uint256)",
}

# 闪电贷完整调用序列（borrow → callback → exploit）
FLASH_LOAN_ATTACK_SEQUENCE: list[str] = [
    "0x0906f8c8",  # flash()
    "0xaf0526a4",  # executeOperation() (回调)
]


# ---------------------------------------------------------------------------
# 预言机操纵相关函数签名
# ---------------------------------------------------------------------------

ORACLE_PRICE_UPDATE_SIGNATURES: dict[str, str] = {
    # Chainlink
    "0xf2ee5f6b": "latestRoundData()",
    "0x50d25bcd": "latestAnswer()",
    "0x7243e50a": "getRoundData(uint80)",
    # Uniswap TWAP
    "0x885e7c1f": "observe(uint32[])",
    "0x1698ee42": "consult(address,uint256)",
    # Band Protocol
    "0x4e4bf4a1": "getReferenceData(string)",
}

ORACLE_MANIPULATION_SIGNATURES: dict[str, str] = {
    # 大额单笔交易操纵流动性池价格
    "0x38ed1739": "swapExactTokensForTokens(uint256,uint256,address[],address,uint256)",
    "0x8803dbee": "swapTokensForExactTokens(uint256,uint256,address[],address,uint256)",
    "0xe449022e": "swapExactTokensForTokensSupportingFeeOnTransferTokens(uint256,uint256,address[],address,uint256)",
    "0x7ff36ab5": "swapExactETHForTokens(uint256,address[],address,uint256)",
    "0x18cbafe5": "swapExactTokensForETH(uint256,uint256,address[],address,uint256)",
    # 添加/移除流动性影响价格
    "0xe8e33700": "addLiquidity(address,address,uint256,uint256,uint256,uint256,address,uint256)",
    "0xf305d719": "addLiquidityETH(address,uint256,uint256,uint256,uint256,uint256)",
    "0x2e1a7d4d": "withdraw(uint256)",
    # 单区块内多次价格查询
    "0x885e7c1f": "observe(uint32[])",
}

ORACLE_EXPLOIT_SIGNATURES: dict[str, str] = {
    "0xc5ebeaec": "liquidate(address,uint256)",
    "0x96cd4ddb": "liquidationCall(address,address,address,uint256,bool)",
    "0xa9059cbb": "transfer(address,uint256)",
    "0x40c10f19": "mint(address,uint256)",
    "0xdb006a75": "borrow(uint256)",
    "0x852a12e3": "borrow(address,uint256)",
    "0xc5c2b2fd": "borrow(address,uint256,uint256,uint16,address)",
    "0x69328dec": "redeem(uint256)",
    "0xdb006a75": "borrow(uint256)",
}

# 预言机操纵典型序列: 大额 swap → 价格查询 → 利用价格
ORACLE_MANIPULATION_SEQUENCE: list[str] = [
    "0x38ed1739",  # swapExactTokensForTokens (操纵价格)
    "0xf2ee5f6b",  # latestRoundData (价格查询/依赖)
]


# ---------------------------------------------------------------------------
# 重入相关函数签名
# ---------------------------------------------------------------------------

REENTRANCY_DRAIN_SIGNATURES: dict[str, str] = {
    "0x3ccfd60b": "withdraw()",
    "0x2e1a7d4d": "withdraw(uint256)",
    "0xf3fef3a3": "withdraw(uint256,address,address)",
    "0xba087652": "redeem(uint256,address,address)",
    "0x69328dec": "redeem(uint256)",
    "0x51cff8d9": "claim(address)",
    "0x4e71d92d": "claimRewards()",
}


# ---------------------------------------------------------------------------
# 访问控制攻击相关函数签名
# ---------------------------------------------------------------------------

ACCESS_CONTROL_SIGNATURES: dict[str, str] = {
    # 所有权相关
    "0x715018a6": "renounceOwnership()",
    "0xf2fde38b": "transferOwnership(address)",
    "0x36568abe": "renounceRole(bytes32,address)",
    "0x2f2ff15d": "grantRole(bytes32,address)",
    # 权限提升
    "0x5c975abb": "setPaused(bool)",
    "0xcaf6c439": "setGovernor(address)",
    "0x3f4ba83a": "setAuthority(address)",
    # 初始化漏洞
    "0x8129fc1c": "initialize()",
    "0xc4d66de8": "initialize(address)",
    "0x485cc955": "initialize(address,address)",
}

# 代理升级相关
PROXY_UPGRADE_SIGNATURES: dict[str, str] = {
    "0x3659cfe6": "upgradeTo(address)",
    "0x4f1ef286": "upgradeToAndCall(address,bytes)",
    "0x5c60da1b": "implementation()",
    "0xf851a440": "admin()",
    "0x8f283970": "changeAdmin(address)",
}


# ---------------------------------------------------------------------------
# 治理攻击相关函数签名
# ---------------------------------------------------------------------------

GOVERNANCE_SIGNATURES: dict[str, str] = {
    # 投票相关
    "0x56781388": "vote(uint256,bool,bool)",
    "0x6fc1b0d7": "castVote(uint256,bool)",
    "0x10ddb22d": "castVoteWithReason(uint256,bool,string)",
    # 提案相关
    "0x7d5b6b4c": "propose(address[],uint256[],bytes[],string)",
    "0xfe0d94c1": "execute(uint256)",
    "0x432a9a68": "queue(uint256)",
    "0x78e97925": "state(uint256)",
    # 时间锁
    "0x1f3c1e5b": "scheduleBatch(address[],uint256[],bytes[],bytes32,bytes32,uint256)",
    "0x01a467be": "executeBatch(address[],uint256[],bytes[],bytes32,bytes32)",
}


# ---------------------------------------------------------------------------
# 通用辅助：按选择器查询签名
# ---------------------------------------------------------------------------

# 全量合并表（供全局查询）
ALL_SIGNATURES: dict[str, str] = {}
ALL_SIGNATURES.update(FLASH_LOAN_SIGNATURES)
ALL_SIGNATURES.update(FLASH_LOAN_CALLBACK_SIGNATURES)
ALL_SIGNATURES.update(FLASH_LOAN_EXPLOIT_SIGNATURES)
ALL_SIGNATURES.update(ORACLE_PRICE_UPDATE_SIGNATURES)
ALL_SIGNATURES.update(ORACLE_MANIPULATION_SIGNATURES)
ALL_SIGNATURES.update(REENTRANCY_DRAIN_SIGNATURES)
ALL_SIGNATURES.update(ACCESS_CONTROL_SIGNATURES)
ALL_SIGNATURES.update(PROXY_UPGRADE_SIGNATURES)
ALL_SIGNATURES.update(GOVERNANCE_SIGNATURES)


def lookup_signature(selector: str) -> str | None:
    """
    根据函数选择器查找函数签名。

    Args:
        selector: 函数选择器（如 "0x0906f8c8"）

    Returns:
        函数签名字符串，未找到返回 None
    """
    return ALL_SIGNATURES.get(selector.lower())


def lookup_signatures_batch(selectors: list[str]) -> dict[str, str]:
    """
    批量查找函数签名。

    Args:
        selectors: 函数选择器列表

    Returns:
        {selector: signature} 映射（仅包含找到的）
    """
    result = {}
    for s in selectors:
        sig = lookup_signature(s)
        if sig:
            result[s.lower()] = sig
    return result
