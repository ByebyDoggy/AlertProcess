"""
资金流向分析脚本

分析交易中的资金流向，识别主要受益者和异常资金流动。
"""

# 获取余额变化
balance_changes = ctx.get_balance_changes()

if not balance_changes:
    result = False
    score = 0
else:
    # 找出余额增加最多的地址
    max_gain = 0
    max_gain_address = None
    max_gain_token = None

    for token, addr_changes in balance_changes.items():
        for addr, change in addr_changes.items():
            if change > max_gain:
                max_gain = change
                max_gain_address = addr
                max_gain_token = token

    # 找出余额减少最多的地址
    max_loss = 0
    max_loss_address = None

    for token, addr_changes in balance_changes.items():
        for addr, change in addr_changes.items():
            if change < -max_loss:
                max_loss = -change
                max_loss_address = addr

    # 判断是否有异常资金流动
    if max_gain > 100000:
        result = True
        score = 80
        labels = ["large_fund_flow"]

        # 获取代币价格计算 USD 价值
        if max_gain_token:
            price = ctx.get_token_price(max_gain_token)
            value_usd = max_gain * price

            if value_usd > 1000000:
                score = 90
                labels.append("high_value_transfer")

        ctx["beneficiary"] = max_gain_address
        ctx["gain_amount"] = max_gain
        ctx["victim"] = max_loss_address
        ctx["loss_amount"] = max_loss
    else:
        result = False
        score = 10
