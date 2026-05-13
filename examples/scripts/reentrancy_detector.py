"""
重入攻击检测脚本

检测特征：
1. 同一合约在调用栈中多次出现
2. 嵌套调用深度 > 3
3. 可疑的调用模式
"""

# 检测重入模式
reentrancy_patterns = ctx.detect_reentrancy()

if reentrancy_patterns:
    result = True
    score = 95
    labels = ["reentrancy_attack"]

    # 检查嵌套深度
    max_depth = max(max(p["depths"]) for p in reentrancy_patterns)

    if max_depth > 3:
        score = 100
        labels.append("deep_reentrancy")

    # 记录受影响的合约
    affected_contracts = list(set(p["contract"] for p in reentrancy_patterns))

    ctx["reentrancy_patterns"] = reentrancy_patterns
    ctx["affected_contracts"] = affected_contracts
    ctx["max_depth"] = max_depth
else:
    result = False
    score = 0
