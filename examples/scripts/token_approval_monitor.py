"""
Token 授权监控脚本

监控 Token 授权事件，识别高风险授权。
"""

# 获取 Approval 事件
approvals = ctx.get_approvals()

if not approvals:
    result = False
    score = 0
else:
    # 检查无限授权
    unlimited_approvals = []
    high_value_approvals = []

    for approval in approvals:
        amount = approval.get("amount", 0)
        token = approval.get("token_address", "")
        spender = approval.get("spender", "")

        # 检查是否为无限授权（通常是 2^256-1）
        if amount > 2**255:
            unlimited_approvals.append(approval)

        # 检查高价值授权
        price = ctx.get_token_price(token)
        value_usd = amount * price

        if value_usd > 100000:
            high_value_approvals.append({
                "token": token,
                "spender": spender,
                "amount": amount,
                "value_usd": value_usd,
            })

    # 判断风险
    if unlimited_approvals or high_value_approvals:
        result = True
        score = 70
        labels = ["token_approval"]

        if unlimited_approvals:
            score = 85
            labels.append("unlimited_approval")

        if high_value_approvals:
            max_value = max(a["value_usd"] for a in high_value_approvals)
            if max_value > 1000000:
                score = 90
                labels.append("high_value_approval")

        ctx["unlimited_approvals"] = len(unlimited_approvals)
        ctx["high_value_approvals"] = high_value_approvals
    else:
        result = False
        score = 20
