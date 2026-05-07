from __future__ import annotations

import unittest

from coinb.risk import RiskManager


def make_risk_manager() -> RiskManager:
    return RiskManager(
        starting_cash_krw=1_000_000,
        max_position_krw=100_000,
        position_size_pct=10.0,
        max_open_positions=3,
        min_order_krw=5_000,
        daily_loss_limit_pct=3.0,
        total_loss_limit_pct=10.0,
        max_consecutive_losses=3,
    )


class TestRiskManager(unittest.TestCase):
    def test_entry_allowed(self) -> None:
        risk = make_risk_manager()

        decision = risk.check_entry(
            market="KRW-BTC",
            cash_krw=1_000_000,
            equity_krw=1_000_000,
            open_position_count=0,
            already_has_position=False,
        )

        self.assertTrue(decision.ok)
        self.assertEqual(decision.reason, "entry_allowed")
        self.assertEqual(decision.amount_krw, 100_000)

    def test_already_has_position_blocked(self) -> None:
        risk = make_risk_manager()

        decision = risk.check_entry(
            market="KRW-BTC",
            cash_krw=1_000_000,
            equity_krw=1_000_000,
            open_position_count=1,
            already_has_position=True,
        )

        self.assertFalse(decision.ok)
        self.assertEqual(decision.reason, "already_has_position")

    def test_max_open_positions_blocked(self) -> None:
        risk = make_risk_manager()

        decision = risk.check_entry(
            market="KRW-BTC",
            cash_krw=1_000_000,
            equity_krw=1_000_000,
            open_position_count=3,
            already_has_position=False,
        )

        self.assertFalse(decision.ok)
        self.assertEqual(decision.reason, "max_open_positions_reached")

    def test_min_order_blocked(self) -> None:
        risk = RiskManager(
            starting_cash_krw=1_000_000,
            max_position_krw=4_000,
            position_size_pct=1.0,
            max_open_positions=3,
            min_order_krw=5_000,
            daily_loss_limit_pct=3.0,
            total_loss_limit_pct=10.0,
            max_consecutive_losses=3,
        )

        decision = risk.check_entry(
            market="KRW-BTC",
            cash_krw=1_000_000,
            equity_krw=1_000_000,
            open_position_count=0,
            already_has_position=False,
        )

        self.assertFalse(decision.ok)
        self.assertEqual(decision.reason, "amount_below_min_order")

    def test_insufficient_cash_blocked(self) -> None:
        risk = make_risk_manager()

        decision = risk.check_entry(
            market="KRW-BTC",
            cash_krw=1_000,
            equity_krw=1_000_000,
            open_position_count=0,
            already_has_position=False,
        )

        self.assertFalse(decision.ok)
        self.assertEqual(decision.reason, "insufficient_cash")

    def test_consecutive_losses_stop(self) -> None:
        risk = make_risk_manager()

        risk.record_trade_result(-1_000)
        risk.record_trade_result(-1_000)
        risk.record_trade_result(-1_000)

        decision = risk.check_entry(
            market="KRW-BTC",
            cash_krw=1_000_000,
            equity_krw=997_000,
            open_position_count=0,
            already_has_position=False,
        )

        self.assertFalse(decision.ok)
        self.assertEqual(decision.reason, "max_consecutive_losses")
        self.assertTrue(risk.is_stopped)

    def test_daily_loss_limit_stop(self) -> None:
        risk = make_risk_manager()

        risk.record_trade_result(-31_000)

        decision = risk.check_entry(
            market="KRW-BTC",
            cash_krw=1_000_000,
            equity_krw=969_000,
            open_position_count=0,
            already_has_position=False,
        )

        self.assertFalse(decision.ok)
        self.assertEqual(decision.reason, "risk_stopped:daily_loss_limit_reached")
        self.assertTrue(risk.is_stopped)

    def test_total_loss_limit_stop(self) -> None:
        risk = make_risk_manager()

        decision = risk.check_entry(
            market="KRW-BTC",
            cash_krw=900_000,
            equity_krw=899_000,
            open_position_count=0,
            already_has_position=False,
        )

        self.assertFalse(decision.ok)
        self.assertEqual(decision.reason, "total_loss_limit_reached")
        self.assertTrue(risk.is_stopped)


if __name__ == "__main__":
    unittest.main()