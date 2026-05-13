"""
Swap 分析脚本

分析交易中的 Swap 事件，识别异常交易模式。
"""

# 获取 Swap 事件
swaps = ctx.get_swaps()

if not swaps:
    result = False
    score = 0
else:
    # 分析 Swap 模式
    total_swaps = len(swaps)
    unique_tokens = set()
    total_volume = 0

    for swap in swaps:
        token_in = swap.get("token_in", "")
        token_out = swap.get("token_out", "")
        amount_in = swap.get("amount_in", 0)

        unique_tokens.add(token_in)
        unique_tokens.add(token_out)

        # 计算交易量（USD）
        price = ctx.get_token_price(token_in)
        total_volume += amount_in * price

    # 检查是否有异常模式
    suspicious = False

    # 模式 1: 大量 Swap（> 10 次）
    if total_swaps > 10:
        suspicious = True
        labels = ["multiple_swaps"]
        score = 70

    # 模式 2: 涉及多种代币（> 5 种）
    if len(unique_tokens) > 5:
        suspicious = True
        labels = ["multiple_tokens"]
        score = 75

    # 模式 3: 高交易量（> 100万 USD）
    if total_volume > 1000000:
        suspicious = True
        labels = ["high_volume_swap"]
        score = 80

    if suspicious:
        result = True
        ctx["total_swaps"] = total_swaps
        ctx["unique_tokens"] = len(unique_tokens)
        ctx["total_volume_usd"] = total_volume
    else:
        result = False
        score = 10
