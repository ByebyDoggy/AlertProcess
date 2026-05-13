"""
余额变化追踪脚本

追踪交易中的余额变化，识别异常资金流动。
"""

# 获取余额变化
balance_changes = ctx.get_balance_changes()

if not balance_changes:
    result = False
    score = 0
else:
    # 统计余额变化
    total_addresses = 0
    total_tokens = len(balance_changes)
    large_changes = []

    for token, addr_changes in balance_changes.items():
        total_addresses += len(addr_changes)

        for addr, change in addr_changes.items():
            # 记录大额变化（> 10万）
            if abs(change) > 100000:
                price = ctx.get_token_price(token)
                value_usd = abs(change) * price

                large_changes.append({
                    "address": addr,
                    "token": token,
                    "change": change,
                    "value_usd": value_usd,
                })

    # 判断是否有异常
    if large_changes:
        result = True
        score = 75
        labels = ["large_balance_change"]

        # 检查是否有超大额变化（> 100万 USD）
        max_value = max(c["value_usd"] for c in large_changes)
        if max_value > 1000000:
            score = 90
            labels.append("extremely_large_change")

        ctx["large_changes"] = large_changes
        ctx["total_addresses"] = total_addresses
        ctx["total_tokens"] = total_tokens
    elif total_addresses > 20:
        # 涉及大量地址也可能是异常
        result = True
        score = 65
        labels = ["multiple_addresses"]
        ctx["total_addresses"] = total_addresses
    else:
        result = False
        score = 10
