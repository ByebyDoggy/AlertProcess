"""
价格操纵检测脚本

检测特征：
1. 单笔 Swap 价格影响 > 10%
2. 连续多笔 Swap 累计影响 > 20%
3. 异常价格波动
"""

swaps = ctx.get_swaps()

if not swaps:
    result = False
    score = 0
else:
    max_impact = 0
    total_impact = 0

    for swap in swaps:
        # 从 extra 获取储备量（如果可用）
        reserve_in = swap.get("reserve_in", 0)
        reserve_out = swap.get("reserve_out", 0)
        amount_in = swap.get("amount_in", 0)

        if reserve_in > 0 and reserve_out > 0 and amount_in > 0:
            impact = ctx.calculate_price_impact(
                reserve_in,
                reserve_out,
                amount_in
            )

            max_impact = max(max_impact, abs(impact))
            total_impact += abs(impact)

    # 判断是否为价格操纵
    if max_impact > 10 or total_impact > 20:
        result = True
        score = 90
        labels = ["price_manipulation", "high_impact"]
        ctx["max_price_impact"] = max_impact
        ctx["total_price_impact"] = total_impact
    else:
        result = False
        score = 20
