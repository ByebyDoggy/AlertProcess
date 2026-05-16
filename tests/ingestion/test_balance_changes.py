from backend.ingestion.balance_changes import BalanceChangeCalculator

TOKEN = "0xToken"
ALICE = "0xAlice"
BOB = "0xBob"
CAROL = "0xCarol"


def test_calculator_computes_net_usd_loss_and_profit_from_transfers():
    calculator = BalanceChangeCalculator()
    transfers = [
        {"token": TOKEN, "from": ALICE, "to": BOB, "amount_raw": "150000000"},
        {"token": TOKEN, "from": BOB, "to": CAROL, "amount_raw": "25000000"},
    ]

    result = calculator.calculate(
        transfers=transfers,
        token_prices={TOKEN: 2.0},
        token_decimals={TOKEN: 2},
    )

    assert result.top_loss_address == ALICE.lower()
    assert result.top_loss_usd == 3_000_000.0
    assert result.top_profit_address == BOB.lower()
    assert result.top_profit_usd == 2_500_000.0
    assert result.changes_by_address[ALICE.lower()].net_usd == -3_000_000.0
    assert result.changes_by_address[BOB.lower()].net_usd == 2_500_000.0


def test_calculator_parses_hex_amounts_and_raw_transfer_value_keys():
    calculator = BalanceChangeCalculator()
    transfers = [
        {"token": TOKEN, "from": ALICE, "to": BOB, "value": hex(10 * 10**18)},
    ]

    result = calculator.calculate(
        transfers=transfers,
        token_prices={TOKEN: 1.5},
        token_decimals={TOKEN: 18},
    )

    assert result.top_loss_address == ALICE.lower()
    assert result.top_loss_usd == 15.0
    assert result.top_profit_address == BOB.lower()
    assert result.top_profit_usd == 15.0


def test_calculator_exports_detection_context_balance_changes():
    calculator = BalanceChangeCalculator()
    result = calculator.calculate(
        transfers=[{"token": TOKEN, "from": ALICE, "to": BOB, "amount_raw": "100"}],
        token_prices={TOKEN: 1.0},
        token_decimals={TOKEN: 0},
    )

    assert result.to_context_balance_changes() == [
        {
            "address": ALICE.lower(),
            "net_usd": -100.0,
            "loss_usd": 100.0,
            "profit_usd": 0.0,
            "net_by_token": {TOKEN.lower(): "-100"},
        },
        {
            "address": BOB.lower(),
            "net_usd": 100.0,
            "loss_usd": 0.0,
            "profit_usd": 100.0,
            "net_by_token": {TOKEN.lower(): "100"},
        },
    ]
