"""
Flash Loan 检测脚本

检测特征：
1. 大额借贷（> 100万）
2. 同一交易内有多次 Swap
3. 高 ROI（> 5%）
"""

# 获取转账和 Swap 事件
transfers = ctx.get_transfers()
swaps = ctx.get_swaps()

# 检查是否有大额借贷
large_borrows = [t for t in transfers if t.get("amount", 0) > 1000000]

if large_borrows and len(swaps) >= 2:
    # 计算资金流入流出
    from_addr = ctx.tx_context.from_address.lower()

    total_in = sum(
        t.get("amount", 0)
        for t in transfers
        if t.get("to_address", "").lower() == from_addr
    )

    total_out = sum(
        t.get("amount", 0)
        for t in transfers
        if t.get("from_address", "").lower() == from_addr
    )

    # 计算 ROI
    roi = ctx.calculate_roi(total_in, total_out)

    if roi > 5:
        result = True
        score = 85
        labels = ["flash_loan", "high_roi"]
        ctx["flash_loan_roi"] = roi
        ctx["borrow_amount"] = max(t.get("amount", 0) for t in large_borrows)
    else:
        result = False
        score = 30
else:
    result = False
    score = 0
