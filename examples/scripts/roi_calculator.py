"""
ROI 计算脚本

计算交易的投资回报率（ROI），用于识别高收益攻击。
"""

# 获取转账记录
transfers = ctx.get_transfers()

if not transfers:
    result = False
    score = 0
else:
    from_addr = ctx.tx_context.from_address.lower()

    # 计算流入（收到的代币）
    inflow = 0
    for t in transfers:
        if t.get("to_address", "").lower() == from_addr:
            amount = t.get("amount", 0)
            token = t.get("token_address", "")
            price = ctx.get_token_price(token)
            inflow += amount * price

    # 计算流出（发送的代币）
    outflow = 0
    for t in transfers:
        if t.get("from_address", "").lower() == from_addr:
            amount = t.get("amount", 0)
            token = t.get("token_address", "")
            price = ctx.get_token_price(token)
            outflow += amount * price

    # 计算 ROI
    if outflow > 0:
        roi = ctx.calculate_roi(inflow, outflow)
        profit = inflow - outflow

        if roi > 10:
            result = True
            score = 85
            labels = ["high_roi"]

            if roi > 50:
                score = 95
                labels.append("extremely_high_roi")

            ctx["roi"] = roi
            ctx["profit_usd"] = profit
            ctx["inflow_usd"] = inflow
            ctx["outflow_usd"] = outflow
        else:
            result = False
            score = 20
    else:
        result = False
        score = 0
