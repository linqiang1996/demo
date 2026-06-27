import math
import unittest

from app.analytics import build_portfolio_nav, to_nav_frame


class PortfolioAnalyticsTests(unittest.TestCase):
    def test_cumulative_return_comes_from_portfolio_nav_curve(self) -> None:
        nav_df = to_nav_frame(
            [
                {"product_key": "alpha", "product_name": "Alpha", "nav_date": "2026-01-02", "nav_value": 1.0},
                {"product_key": "alpha", "product_name": "Alpha", "nav_date": "2026-01-03", "nav_value": 1.5},
                {"product_key": "alpha", "product_name": "Alpha", "nav_date": "2026-01-04", "nav_value": 1.5},
                {"product_key": "beta", "product_name": "Beta", "nav_date": "2026-01-04", "nav_value": 1.0},
            ]
        )
        allocations = {
            "alpha": {"amount": 100.0, "entry_nav": 1.0},
            "beta": {"amount": 100.0, "entry_nav": 1.0},
        }

        result = build_portfolio_nav(nav_df, allocations, risk_free_rate=0.0, annual_trading_days=252, weekly_periods=52)
        metrics = result["metrics"]

        self.assertTrue(math.isclose(metrics["latest_nav"], 1.5, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["since_invest_return"], 0.5, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["current_asset_scale"], 250.0, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["initial_investment_scale"], 200.0, rel_tol=1e-9))
        self.assertEqual(metrics["history_points"], 3)

        beta = next(item for item in result["positions"] if item["product_key"] == "beta")
        self.assertEqual(beta["first_invest_date"], "2026-01-04")
        self.assertTrue(math.isclose(beta["current_asset_scale"], 100.0, rel_tol=1e-9))

    def test_entry_nav_is_share_basis_not_inferred_entry_date(self) -> None:
        nav_df = to_nav_frame(
            [
                {"product_key": "gamma", "product_name": "Gamma", "nav_date": "2026-01-02", "nav_value": 1.0},
                {"product_key": "gamma", "product_name": "Gamma", "nav_date": "2026-01-03", "nav_value": 1.2},
                {"product_key": "gamma", "product_name": "Gamma", "nav_date": "2026-01-04", "nav_value": 1.4},
            ]
        )
        allocations = {"gamma": {"amount": 140.0, "entry_nav": 1.4}}

        result = build_portfolio_nav(nav_df, allocations, risk_free_rate=0.0, annual_trading_days=252, weekly_periods=52)
        metrics = result["metrics"]
        position = result["positions"][0]

        self.assertEqual(position["first_invest_date"], "2026-01-02")
        self.assertTrue(math.isclose(position["entry_nav"], 1.4, rel_tol=1e-9))
        self.assertTrue(math.isclose(position["since_invest_return"], 0.0, rel_tol=1e-9))
        self.assertEqual(metrics["base_date"], "2026-01-02")
        self.assertEqual(metrics["first_actual_date"], "2026-01-02")
        self.assertEqual(metrics["history_points"], 3)
        self.assertTrue(math.isclose(metrics["latest_nav"], 1.0, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["since_invest_return"], 0.0, rel_tol=1e-9))

    def test_manual_initial_portfolio_nav_scales_display_nav_only(self) -> None:
        nav_df = to_nav_frame(
            [
                {"product_key": "alpha", "product_name": "Alpha", "nav_date": "2026-01-02", "nav_value": 1.0},
                {"product_key": "alpha", "product_name": "Alpha", "nav_date": "2026-01-03", "nav_value": 1.2},
            ]
        )
        allocations = {"alpha": {"amount": 100.0, "entry_nav": 1.0}}

        result = build_portfolio_nav(
            nav_df,
            allocations,
            risk_free_rate=0.0,
            annual_trading_days=252,
            weekly_periods=52,
            initial_portfolio_nav=1.5,
        )
        metrics = result["metrics"]

        self.assertTrue(math.isclose(metrics["configured_initial_nav"], 1.5, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["computed_latest_nav"], 1.2, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["latest_nav"], 1.2, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["since_invest_return"], -0.2, rel_tol=1e-9))

    def test_manual_latest_nav_overrides_portfolio_display_nav(self) -> None:
        nav_df = to_nav_frame(
            [
                {"product_key": "alpha", "product_name": "Alpha", "nav_date": "2026-01-02", "nav_value": 1.0},
                {"product_key": "alpha", "product_name": "Alpha", "nav_date": "2026-01-03", "nav_value": 1.2},
            ]
        )
        allocations = {"alpha": {"amount": 100.0, "entry_nav": 1.0}}

        result = build_portfolio_nav(
            nav_df,
            allocations,
            risk_free_rate=0.0,
            annual_trading_days=252,
            weekly_periods=52,
            initial_portfolio_nav=1.0,
            latest_portfolio_nav=1.35,
        )
        metrics = result["metrics"]

        self.assertTrue(math.isclose(metrics["configured_latest_nav"], 1.35, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["computed_latest_nav"], 1.2, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["latest_nav"], 1.35, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["since_invest_return"], 0.35, rel_tol=1e-9))

    def test_manual_only_positions_are_added_to_scale_snapshot(self) -> None:
        result = build_portfolio_nav(
            to_nav_frame([]),
            {},
            risk_free_rate=0.0,
            annual_trading_days=252,
            weekly_periods=52,
            initial_portfolio_nav=1.0,
            manual_positions=[
                {
                    "product_key": "manual::1",
                    "product_name": "手动产品A",
                    "amount": 100.0,
                    "entry_nav": 1.0,
                    "latest_nav": 1.2,
                }
            ],
        )
        metrics = result["metrics"]
        position = result["positions"][0]

        self.assertEqual(metrics["manual_only_position_count"], 1)
        self.assertTrue(math.isclose(metrics["initial_investment_scale"], 100.0, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["current_asset_scale"], 120.0, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["computed_latest_nav"], 1.2, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["latest_nav"], 1.2, rel_tol=1e-9))
        self.assertTrue(math.isclose(metrics["since_invest_return"], 0.2, rel_tol=1e-9))
        self.assertEqual(position["product_name"], "手动产品A")
        self.assertTrue(position["is_manual_only"])


if __name__ == "__main__":
    unittest.main()
