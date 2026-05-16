"""
动态函数签名分析器

支持多层分析：
1. Layer 1: 硬编码签名（高置信度 90%）
2. Layer 2: 4bytes 查询 + 关键词匹配（中置信度 70%）
3. Layer 3: 上下文特征（置信度调整 ±20%）
4. Layer 4: 可选 LLM 判断（语义理解 60-80%）
"""

import requests
from functools import lru_cache
from typing import Dict, List, Optional, Set
import logging

logger = logging.getLogger(__name__)


class FourBytesClient:
    """4bytes.directory API 客户端"""

    BASE_URL = "https://www.4byte.directory/api/v1/signatures/"

    def __init__(self, timeout: int = 2, cache_size: int = 1000):
        self.timeout = timeout
        self._cache: Dict[str, List[str]] = {}

    @lru_cache(maxsize=1000)
    def lookup_signature(self, selector: str) -> List[str]:
        """
        查询函数签名

        Args:
            selector: 函数选择器（如 "0x7c025200"）

        Returns:
            函数签名列表（如 ["withdrawERC20(address,address,uint256)"]）
        """
        # 检查本地缓存
        if selector in self._cache:
            return self._cache[selector]

        try:
            response = requests.get(
                f"{self.BASE_URL}?hex_signature={selector}",
                timeout=self.timeout
            )
            if response.status_code == 200:
                data = response.json()
                signatures = [item["text_signature"] for item in data.get("results", [])]
                self._cache[selector] = signatures
                return signatures
        except Exception as e:
            logger.warning(f"4bytes lookup failed for {selector}: {e}")
            return []

        return []


class FunctionNameAnalyzer:
    """函数名称关键词分析器"""

    # 提现相关关键词（高风险）
    WITHDRAWAL_KEYWORDS = [
        "withdraw",
        "claim",
        "redeem",
        "bridge",
        "unlock",
        "release",
        "rescue",
        "emergencywithdraw",
        "emergencywithdrawal",
    ]

    # 转账相关关键词（中风险）
    TRANSFER_KEYWORDS = [
        "transfer",
        "send",
        "swap",
        "exchange",
    ]

    # 排除关键词（正常操作）
    EXCLUDE_KEYWORDS = [
        "deposit",
        "stake",
        "lock",
        "mint",
        "approve",
    ]

    def analyze_function_name(self, func_sig: str) -> Dict:
        """
        分析函数名称

        Returns:
            {
                "is_suspicious": bool,
                "confidence": float,  # 0.0 - 1.0
                "matched_keywords": list[str],
                "risk_level": str,  # "high", "medium", "low"
            }
        """
        func_name = func_sig.split("(")[0].lower()

        # 检查排除关键词
        for keyword in self.EXCLUDE_KEYWORDS:
            if keyword in func_name:
                return {
                    "is_suspicious": False,
                    "confidence": 0.0,
                    "matched_keywords": [],
                    "risk_level": "low",
                    "reason": f"excluded_keyword:{keyword}"
                }

        # 检查提现关键词
        matched_withdrawal = [kw for kw in self.WITHDRAWAL_KEYWORDS if kw in func_name]
        if matched_withdrawal:
            return {
                "is_suspicious": True,
                "confidence": 0.70,
                "matched_keywords": matched_withdrawal,
                "risk_level": "high",
                "reason": "withdrawal_keyword_matched"
            }

        # 检查转账关键词
        matched_transfer = [kw for kw in self.TRANSFER_KEYWORDS if kw in func_name]
        if matched_transfer:
            return {
                "is_suspicious": True,
                "confidence": 0.50,
                "matched_keywords": matched_transfer,
                "risk_level": "medium",
                "reason": "transfer_keyword_matched"
            }

        return {
            "is_suspicious": False,
            "confidence": 0.0,
            "matched_keywords": [],
            "risk_level": "low",
            "reason": "no_keyword_matched"
        }


class ContextFeatureAnalyzer:
    """上下文特征分析器"""

    # 已知跨链桥合约
    KNOWN_BRIDGE_CONTRACTS = {
        "0x1a2a1c938ce3ec39b6d47113c7955baa9dd454f2",  # Ronin Bridge
        "0x2796317b0ff8538f253012862c06787adfb8ceb6",  # Poly Network
        "0x3ee18b2214aff97000d974cf647e7c347e8fa585",  # Wormhole
        "0x98f3c9e6e3face36baad05fe09d375ef1464288b",  # Multichain
        "0x88dcdc47d2f83a99cf0000fdf667a468bb958a78",  # Nomad Bridge
    }

    # 已知安全合约（白名单）
    KNOWN_SAFE_CONTRACTS = {
        "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",  # Uniswap V2 Router
        "0xe592427a0aece92de3edee1f18e0157c05861564",  # Uniswap V3 Router
        "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9",  # Aave V2 Pool
        "0x3d9819210a31b4961b30ef54be2aed79b9c9cd3b",  # Compound Comptroller
    }

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.large_transfer_threshold = self.config.get("large_transfer_threshold", 50000)
        self.complex_call_depth = self.config.get("complex_call_depth", 3)
        self.multi_token_threshold = self.config.get("multi_token_threshold", 2)

    def analyze_context(
        self,
        contract_address: Optional[str] = None,
        value_transferred: float = 0.0,
        call_depth: int = 0,
        token_count: int = 0,
        has_delegatecall_unknown: bool = False
    ) -> Dict:
        """
        分析上下文特征

        Returns:
            {
                "confidence_adjustment": float,  # -0.2 to +0.2
                "features": dict,
                "feature_count": int
            }
        """
        adjustment = 0.0
        features = {}

        # 特征 1: 合约类型
        if contract_address:
            contract_lower = contract_address.lower()
            if contract_lower in self.KNOWN_BRIDGE_CONTRACTS:
                adjustment += 0.20
                features["is_known_bridge"] = True
            elif contract_lower in self.KNOWN_SAFE_CONTRACTS:
                adjustment -= 0.20
                features["is_known_safe"] = True

        # 特征 2: 资金流向
        if value_transferred > self.large_transfer_threshold:
            adjustment += 0.15
            features["large_transfer"] = True

        # 特征 3: 调用复杂度
        if call_depth > self.complex_call_depth:
            adjustment += 0.10
            features["complex_call"] = True

        # 特征 4: 多代币转账
        if token_count > self.multi_token_threshold:
            adjustment += 0.10
            features["multi_token"] = True

        # 特征 5: delegatecall 到未知地址
        if has_delegatecall_unknown:
            adjustment += 0.15
            features["delegatecall_unknown"] = True

        # 计算特征数量（排除负面特征）
        feature_count = sum([
            features.get("is_known_bridge", False),
            features.get("large_transfer", False),
            features.get("complex_call", False),
            features.get("multi_token", False),
            features.get("delegatecall_unknown", False),
        ])

        return {
            "confidence_adjustment": max(-0.2, min(0.2, adjustment)),
            "features": features,
            "feature_count": feature_count
        }


class SignatureAnalyzer:
    """
    动态函数签名分析器

    支持多层分析：
    - Layer 1: 硬编码签名（高置信度）
    - Layer 2: 4bytes 查询 + 关键词匹配（中置信度）
    - Layer 3: 上下文特征（置信度调整）
    """

    # Layer 1: 高置信度硬编码签名
    HIGH_CONFIDENCE_SIGNATURES = {
        "0x7c025200": ("withdrawERC20(address,address,uint256)", 0.90),
        "0x2e1a7d4d": ("withdraw(uint256)", 0.90),
        "0x00f714ce": ("withdraw(uint256,address)", 0.90),
        "0x51cff8d9": ("withdraw(address)", 0.90),
        "0xf3fef3a3": ("withdraw(address,uint256)", 0.90),
        "0x8e19899e": ("withdrawETH(uint256)", 0.90),
        "0x3ccfd60b": ("withdraw()", 0.90),
        "0x69328dec": ("withdrawTo(address,uint256)", 0.90),
        "0x461bcd22": ("claim()", 0.90),
        "0x4e71d92d": ("claim(address)", 0.90),
    }

    # Layer 1: 中置信度硬编码签名
    MEDIUM_CONFIDENCE_SIGNATURES = {
        "0xac9650d8": ("multicall(bytes[])", 0.70),
        "0x7de4edef": ("execute(address,bytes)", 0.70),
        "0x1cff79cd": ("execute(address,bytes)", 0.70),
        "0xb61d27f6": ("execute(address,uint256,bytes)", 0.70),
    }

    def __init__(
        self,
        enable_4bytes: bool = True,
        enable_llm: bool = False,
        config: Optional[Dict] = None
    ):
        self.enable_4bytes = enable_4bytes
        self.enable_llm = enable_llm
        self.config = config or {}

        # 初始化子模块
        self.fourbytes_client = FourBytesClient() if enable_4bytes else None
        self.function_analyzer = FunctionNameAnalyzer()
        self.context_analyzer = ContextFeatureAnalyzer(config)

        # 配置
        self.min_context_features = self.config.get("min_context_features", 2)
        self.dynamic_threshold_multiplier = self.config.get("dynamic_threshold_multiplier", 1.0)

    def check_hardcoded(self, selector: str) -> Dict:
        """
        Layer 1: 检查硬编码签名

        Returns:
            {
                "matched": bool,
                "function_name": str,
                "confidence": float,
                "layer": str
            }
        """
        selector_lower = selector.lower()

        # 检查高置信度签名
        if selector_lower in self.HIGH_CONFIDENCE_SIGNATURES:
            func_name, confidence = self.HIGH_CONFIDENCE_SIGNATURES[selector_lower]
            return {
                "matched": True,
                "function_name": func_name,
                "confidence": confidence,
                "layer": "layer1_high"
            }

        # 检查中置信度签名
        if selector_lower in self.MEDIUM_CONFIDENCE_SIGNATURES:
            func_name, confidence = self.MEDIUM_CONFIDENCE_SIGNATURES[selector_lower]
            return {
                "matched": True,
                "function_name": func_name,
                "confidence": confidence,
                "layer": "layer1_medium"
            }

        return {
            "matched": False,
            "function_name": None,
            "confidence": 0.0,
            "layer": "layer1"
        }

    def check_4bytes_keywords(self, selector: str) -> Dict:
        """
        Layer 2: 4bytes 查询 + 关键词匹配

        Returns:
            {
                "is_suspicious": bool,
                "confidence": float,
                "matched_keywords": list[str],
                "function_signatures": list[str],
                "layer": str
            }
        """
        if not self.enable_4bytes or not self.fourbytes_client:
            return {
                "is_suspicious": False,
                "confidence": 0.0,
                "matched_keywords": [],
                "function_signatures": [],
                "layer": "layer2"
            }

        # 查询 4bytes
        signatures = self.fourbytes_client.lookup_signature(selector)

        if not signatures:
            return {
                "is_suspicious": False,
                "confidence": 0.0,
                "matched_keywords": [],
                "function_signatures": [],
                "layer": "layer2"
            }

        # 对每个签名进行关键词匹配
        best_result = {
            "is_suspicious": False,
            "confidence": 0.0,
            "matched_keywords": [],
            "risk_level": "low"
        }

        for sig in signatures:
            result = self.function_analyzer.analyze_function_name(sig)
            if result["confidence"] > best_result["confidence"]:
                best_result = result

        return {
            "is_suspicious": best_result["is_suspicious"],
            "confidence": best_result["confidence"],
            "matched_keywords": best_result["matched_keywords"],
            "risk_level": best_result["risk_level"],
            "function_signatures": signatures,
            "layer": "layer2"
        }

    def analyze(
        self,
        selector: str,
        context: Optional[Dict] = None
    ) -> Dict:
        """
        完整分析函数签名

        Args:
            selector: 函数选择器（如 "0x7c025200"）
            context: 上下文信息
                - contract_address: 合约地址
                - value_transferred: 转账金额（USD）
                - call_depth: 调用深度
                - token_count: 代币数量
                - has_delegatecall_unknown: 是否有 delegatecall 到未知地址

        Returns:
            {
                "is_suspicious": bool,
                "confidence": float,
                "score": float,
                "matched_patterns": list[str],
                "analysis_layers": dict,
                "requires_additional_features": bool
            }
        """
        context = context or {}
        result = {
            "is_suspicious": False,
            "confidence": 0.0,
            "score": 0.0,
            "matched_patterns": [],
            "analysis_layers": {},
            "requires_additional_features": False
        }

        # Layer 1: 硬编码签名
        layer1 = self.check_hardcoded(selector)
        result["analysis_layers"]["layer1"] = layer1

        if layer1["matched"]:
            result["is_suspicious"] = True
            result["confidence"] = layer1["confidence"]
            result["score"] = 50.0 * layer1["confidence"]
            result["matched_patterns"].append(f"hardcoded:{layer1['function_name']}")

            # 硬编码签名不需要额外特征
            result["requires_additional_features"] = False

            # 继续分析上下文以进一步调整置信度
        else:
            # Layer 2: 4bytes 查询 + 关键词匹配
            layer2 = self.check_4bytes_keywords(selector)
            result["analysis_layers"]["layer2"] = layer2

            if layer2["is_suspicious"]:
                result["is_suspicious"] = True
                result["confidence"] = layer2["confidence"]
                result["score"] = 50.0 * layer2["confidence"]
                result["matched_patterns"].extend([
                    f"keyword:{kw}" for kw in layer2["matched_keywords"]
                ])

                # 动态识别需要额外特征验证
                result["requires_additional_features"] = True

        # Layer 3: 上下文特征
        layer3 = self.context_analyzer.analyze_context(
            contract_address=context.get("contract_address"),
            value_transferred=context.get("value_transferred", 0.0),
            call_depth=context.get("call_depth", 0),
            token_count=context.get("token_count", 0),
            has_delegatecall_unknown=context.get("has_delegatecall_unknown", False)
        )
        result["analysis_layers"]["layer3"] = layer3

        # 应用上下文调整
        result["confidence"] += layer3["confidence_adjustment"]
        result["score"] += layer3["confidence_adjustment"] * 50.0

        # 如果是动态识别且特征不足，降低置信度
        if result["requires_additional_features"]:
            if layer3["feature_count"] < self.min_context_features:
                result["confidence"] *= 0.5
                result["score"] *= 0.5
                result["matched_patterns"].append("insufficient_context_features")

        # 白名单检查
        if layer3["features"].get("is_known_safe"):
            result["is_suspicious"] = False
            result["confidence"] = 0.0
            result["score"] = 0.0
            result["matched_patterns"].append("whitelisted_contract")

        # 确保置信度和分数在合理范围内
        result["confidence"] = max(0.0, min(1.0, result["confidence"]))
        result["score"] = max(0.0, min(100.0, result["score"]))

        return result

    def get_effective_threshold(self, analysis_result: Dict, base_threshold: float = 65.0) -> float:
        """
        根据分析结果获取有效阈值

        硬编码签名使用基础阈值，动态识别使用更高阈值
        """
        if analysis_result["analysis_layers"]["layer1"]["matched"]:
            # 硬编码签名，使用基础阈值
            return base_threshold
        else:
            # 动态识别，使用更高阈值
            return base_threshold * self.dynamic_threshold_multiplier
