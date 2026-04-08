from src.risk_manager import RiskManager


def test_position_size_basic():
    units = RiskManager.calculate_position_size(
        balance=10_000,
        risk_per_trade=0.01,
        entry_price=1.1000,
        stop_loss=1.0950,
        instrument="EUR_USD",
    )
    # Riesgo 100 USD / 0.005 stop = 20.000 unidades
    assert units == 20_000


def test_position_size_zero_distance():
    units = RiskManager.calculate_position_size(
        balance=10_000,
        risk_per_trade=0.01,
        entry_price=1.1000,
        stop_loss=1.1000,
        instrument="EUR_USD",
    )
    assert units == 0


def test_daily_halt():
    rm = RiskManager(max_daily_loss=0.05)
    rm.update_day(10_000)
    rm.register_pnl(9_400)  # -6%
    assert rm.is_halted()
