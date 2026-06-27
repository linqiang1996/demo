from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass
class ProductSnapshot:
    product_key: str
    product_name: str
    first_invest_date: str | None
    latest_date: str | None
    latest_nav: float | None
    daily_return: float | None
    weekly_return: float | None
    since_invest_return: float | None


def _empty_portfolio_result() -> dict:
    return {
        "series": [],
        "annual_returns": [],
        "product_series": {},
        "product_names": {},
        "positions": [],
        "metrics": {
            "configured_initial_nav": None,
            "configured_latest_nav": None,
            "computed_latest_nav": None,
            "latest_nav": None,
            "weekly_return": None,
            "weekly_anchor_date": None,
            "ytd_return": None,
            "since_invest_return": None,
            "daily_max_drawdown": None,
            "weekly_max_drawdown": None,
            "sharpe_ratio": None,
            "calmar_ratio": None,
            "current_asset_scale": None,
            "initial_investment_scale": None,
            "history_points": 0,
            "history_days": 0,
            "stale_position_count": 0,
            "recent_entry_position_count": 0,
        },
        "warnings": [],
    }


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _normalize_portfolio_config(config: dict[str, Any]) -> dict[str, dict[str, float | None]]:
    normalized: dict[str, dict[str, float | None]] = {}
    for product_key, raw_value in (config or {}).items():
        if str(product_key).startswith("__"):
            continue
        amount = None
        entry_nav = None
        if isinstance(raw_value, dict):
            amount = _positive_float(raw_value.get("amount"))
            entry_nav = _positive_float(raw_value.get("entry_nav"))
        else:
            amount = _positive_float(raw_value)
        if amount is None:
            continue
        normalized[str(product_key)] = {
            "amount": amount,
            "entry_nav": entry_nav,
        }
    return normalized


def to_nav_frame(rows: Iterable[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["product_key", "product_name", "nav_date", "nav_value"])
    df["nav_date"] = pd.to_datetime(df["nav_date"])
    df["nav_value"] = pd.to_numeric(df["nav_value"], errors="coerce")
    return df.sort_values(["product_key", "nav_date"]).reset_index(drop=True)


def compute_product_snapshots(nav_df: pd.DataFrame) -> list[ProductSnapshot]:
    if nav_df.empty:
        return []

    snapshots: list[ProductSnapshot] = []
    for product_key, group in nav_df.groupby("product_key"):
        group = group.sort_values("nav_date").dropna(subset=["nav_value"])
        if group.empty:
            continue
        product_name = str(group.iloc[-1]["product_name"])
        latest = group.iloc[-1]
        first = group.iloc[0]
        daily_return = None
        if len(group) >= 2 and group.iloc[-2]["nav_value"] not in (None, 0):
            daily_return = latest["nav_value"] / group.iloc[-2]["nav_value"] - 1
        weekly_return = None
        if len(group) >= 2:
            week_anchor = group[group["nav_date"] <= latest["nav_date"] - pd.Timedelta(days=7)]
            if not week_anchor.empty and week_anchor.iloc[-1]["nav_value"] not in (None, 0):
                weekly_return = latest["nav_value"] / week_anchor.iloc[-1]["nav_value"] - 1
        total_return = None
        if first["nav_value"] not in (None, 0):
            total_return = latest["nav_value"] / first["nav_value"] - 1
        snapshots.append(
            ProductSnapshot(
                product_key=str(product_key),
                product_name=product_name,
                first_invest_date=first["nav_date"].strftime("%Y-%m-%d"),
                latest_date=latest["nav_date"].strftime("%Y-%m-%d"),
                latest_nav=float(latest["nav_value"]),
                daily_return=float(daily_return) if daily_return is not None else None,
                weekly_return=float(weekly_return) if weekly_return is not None else None,
                since_invest_return=float(total_return) if total_return is not None else None,
            )
        )
    return sorted(snapshots, key=lambda item: item.product_name)


def max_drawdown(nav_series: pd.Series) -> float:
    cumulative_max = nav_series.cummax()
    drawdown = nav_series / cumulative_max - 1
    return float(drawdown.min()) if not drawdown.empty else 0.0


def sharpe_ratio(return_series: pd.Series, risk_free_rate: float, periods_per_year: int) -> float | None:
    clean = return_series.dropna()
    if len(clean) < 2:
        return 0.0
    excess = clean - risk_free_rate / periods_per_year
    volatility = excess.std(ddof=0)
    if volatility == 0 or np.isnan(volatility):
        return 0.0
    return float(excess.mean() / volatility * np.sqrt(periods_per_year))


def calmar_ratio(nav_series: pd.Series, periods_per_year: int) -> float | None:
    if len(nav_series) < 2:
        return 0.0
    total_periods = len(nav_series) - 1
    if total_periods <= 0:
        return 0.0
    total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    annualized = (1 + total_return) ** (periods_per_year / total_periods) - 1 if total_return > -1 else None
    mdd = abs(max_drawdown(nav_series))
    if annualized is None or mdd == 0:
        return 0.0
    return float(annualized / mdd)


def _with_inception_base(nav_series: pd.Series) -> pd.Series:
    if nav_series.empty:
        return nav_series
    first_value = float(nav_series.iloc[0])
    if np.isclose(first_value, 1.0, atol=1e-10):
        return nav_series
    base_date = nav_series.index.min() - pd.Timedelta(days=1)
    base_series = pd.Series([1.0], index=[base_date], dtype=float)
    return pd.concat([base_series, nav_series]).sort_index()


def _period_return(nav_series: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    if nav_series.empty or start > end:
        return None
    window = nav_series[(nav_series.index >= start) & (nav_series.index <= end)]
    if window.empty:
        return None
    anchor = nav_series[nav_series.index < start]
    start_value = float(anchor.iloc[-1]) if not anchor.empty else float(window.iloc[0])
    end_value = float(window.iloc[-1])
    if start_value == 0:
        return None
    return end_value / start_value - 1


def _rolling_return(nav_series: pd.Series, days: int) -> tuple[float | None, str | None]:
    if nav_series.empty:
        return None, None
    latest_date = nav_series.index.max()
    target_date = latest_date - pd.Timedelta(days=days)
    anchor = nav_series[nav_series.index <= target_date]
    if not anchor.empty:
        anchor_date = anchor.index[-1]
        anchor_value = float(anchor.iloc[-1])
        latest_value = float(nav_series.iloc[-1])
        if anchor_value != 0:
            return latest_value / anchor_value - 1, anchor_date.strftime("%Y-%m-%d")
    if len(nav_series) >= 2:
        anchor_date = nav_series.index[0]
        anchor_value = float(nav_series.iloc[0])
        latest_value = float(nav_series.iloc[-1])
        if anchor_value != 0:
            return latest_value / anchor_value - 1, anchor_date.strftime("%Y-%m-%d")
    return 0.0 if len(nav_series) == 1 else None, nav_series.index[0].strftime("%Y-%m-%d") if len(nav_series) == 1 else None


def _infer_entry_point(series: pd.Series, configured_entry_nav: float | None) -> tuple[pd.Timestamp, float]:
    clean = series.dropna().sort_index()
    first_date = clean.index[0]
    first_nav = float(clean.iloc[0])
    if configured_entry_nav is None or configured_entry_nav <= 0:
        return first_date, first_nav
    return first_date, float(configured_entry_nav)


def _normalize_manual_positions(manual_positions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(manual_positions or []):
        if not isinstance(item, dict):
            continue
        product_name = str(item.get("product_name", "")).strip()
        amount = _positive_float(item.get("amount"))
        entry_nav = _positive_float(item.get("entry_nav"))
        latest_nav = _positive_float(item.get("latest_nav"))
        if not product_name and amount is None and entry_nav is None and latest_nav is None:
            continue
        normalized.append(
            {
                "product_key": str(item.get("product_key") or f"manual::{idx}"),
                "product_name": product_name or f"手动产品{idx + 1}",
                "amount": amount,
                "entry_nav": entry_nav,
                "latest_nav": latest_nav,
            }
        )
    return normalized


def _append_manual_positions(
    result: dict,
    manual_positions: list[dict[str, Any]] | None,
    configured_initial_nav: float,
    configured_latest_nav: float | None,
    as_of_date: str | None,
) -> dict:
    normalized = _normalize_manual_positions(manual_positions)
    if not normalized:
        return result

    positions = list(result.get("positions", []))
    metrics = dict(result.get("metrics", {}))
    warnings = list(result.get("warnings", []))

    manual_initial_scale = 0.0
    manual_current_scale = 0.0
    estimated_count = 0

    for item in normalized:
        amount = _positive_float(item.get("amount"))
        entry_nav = _positive_float(item.get("entry_nav"))
        latest_nav = _positive_float(item.get("latest_nav"))
        current_asset_scale = None
        since_invest_return = None
        if amount is not None:
            manual_initial_scale += amount
        if amount is not None and entry_nav is not None and latest_nav is not None and entry_nav > 0:
            current_asset_scale = float(amount * latest_nav / entry_nav)
            since_invest_return = float(latest_nav / entry_nav - 1)
            manual_current_scale += current_asset_scale
            estimated_count += 1
        positions.append(
            {
                "product_key": item["product_key"],
                "product_name": item["product_name"],
                "initial_investment_scale": amount,
                "current_asset_scale": current_asset_scale,
                "first_invest_date": None,
                "entry_nav": entry_nav,
                "latest_nav": latest_nav,
                "latest_observed_date": as_of_date,
                "stale_days": 0 if as_of_date else None,
                "entry_matches_latest_nav": bool(
                    entry_nav is not None and latest_nav is not None and np.isclose(entry_nav, latest_nav, atol=1e-8)
                ),
                "since_invest_return": since_invest_return,
                "is_manual_only": True,
                "history_included": False,
            }
        )

    metrics["manual_only_position_count"] = len(normalized)
    metrics["initial_investment_scale"] = float(metrics.get("initial_investment_scale") or 0.0) + manual_initial_scale
    if manual_current_scale > 0:
        metrics["current_asset_scale"] = float(metrics.get("current_asset_scale") or 0.0) + manual_current_scale

    warnings.append(
        f"当前有 {len(normalized)} 个手动新增产品仅按你填写的首次建仓净值和最新净值纳入规模快照；在同步到历史净值前，它们不会进入组合历史曲线、回撤和夏普指标。"
    )

    if (metrics.get("history_points") or 0) == 0 and manual_initial_scale > 0 and estimated_count == len(normalized):
        estimated_nav = manual_current_scale / manual_initial_scale
        metrics["computed_latest_nav"] = float(estimated_nav)
        metrics["latest_nav"] = float(configured_latest_nav) if configured_latest_nav is not None else float(estimated_nav)
        metrics["since_invest_return"] = float(estimated_nav - 1)
        warnings.append("当前组合仅包含手动新增产品，组合单位净值按手工快照规模估算。")

    result["positions"] = sorted(positions, key=lambda item: str(item["product_name"]))
    result["metrics"] = metrics
    result["warnings"] = warnings
    return result


def build_portfolio_nav(
    nav_df: pd.DataFrame,
    allocations: dict[str, Any],
    risk_free_rate: float,
    annual_trading_days: int,
    weekly_periods: int,
    initial_portfolio_nav: float | None = None,
    latest_portfolio_nav: float | None = None,
    manual_positions: list[dict[str, Any]] | None = None,
) -> dict:
    configured_initial_nav = _positive_float(initial_portfolio_nav) or 1.0
    configured_latest_nav = _positive_float(latest_portfolio_nav)
    normalized_config = _normalize_portfolio_config(allocations)
    if nav_df.empty or not normalized_config:
        result = _empty_portfolio_result()
        result["metrics"]["configured_initial_nav"] = float(configured_initial_nav)
        result["metrics"]["configured_latest_nav"] = float(configured_latest_nav) if configured_latest_nav is not None else None
        return _append_manual_positions(result, manual_positions, configured_initial_nav, configured_latest_nav, None)

    filtered = nav_df[nav_df["product_key"].isin(normalized_config.keys())].copy()
    if filtered.empty:
        result = _empty_portfolio_result()
        result["metrics"]["configured_initial_nav"] = float(configured_initial_nav)
        result["metrics"]["configured_latest_nav"] = float(configured_latest_nav) if configured_latest_nav is not None else None
        return _append_manual_positions(result, manual_positions, configured_initial_nav, configured_latest_nav, None)

    pivot = filtered.pivot_table(index="nav_date", columns="product_key", values="nav_value", aggfunc="last")
    pivot = pivot.sort_index().ffill().dropna(how="all")
    if pivot.empty:
        result = _empty_portfolio_result()
        result["metrics"]["configured_initial_nav"] = float(configured_initial_nav)
        result["metrics"]["configured_latest_nav"] = float(configured_latest_nav) if configured_latest_nav is not None else None
        return _append_manual_positions(result, manual_positions, configured_initial_nav, configured_latest_nav, None)

    amounts = pd.Series({key: value["amount"] for key, value in normalized_config.items()}, dtype=float)
    amounts = amounts[amounts > 0]
    entry_nav_config = {key: value.get("entry_nav") for key, value in normalized_config.items()}
    aligned = pivot.reindex(columns=amounts.index).sort_index().ffill()
    if aligned.empty:
        result = _empty_portfolio_result()
        result["metrics"]["configured_initial_nav"] = float(configured_initial_nav)
        result["metrics"]["configured_latest_nav"] = float(configured_latest_nav) if configured_latest_nav is not None else None
        return _append_manual_positions(result, manual_positions, configured_initial_nav, configured_latest_nav, None)

    name_map = (
        filtered.sort_values("nav_date")
        .drop_duplicates(subset=["product_key"], keep="last")
        .set_index("product_key")["product_name"]
        .to_dict()
    )
    entry_points = {
        product_key: _infer_entry_point(aligned[product_key], entry_nav_config.get(product_key))
        for product_key in aligned.columns
        if not aligned[product_key].dropna().empty
    }

    share_counts: dict[str, float] = {}
    entry_nav_used: dict[str, float] = {}
    first_dates: dict[str, str] = {}
    positions: list[dict] = []
    portfolio_rows: list[tuple[pd.Timestamp, float, float]] = []
    current_total_units = 0.0
    previous_unit_nav = 1.0

    for nav_date in aligned.index:
        contribution_amounts_today = 0.0
        contribution_assets_today = 0.0
        for product_key, (entry_date, inferred_entry_nav) in entry_points.items():
            if entry_date != nav_date or product_key in share_counts:
                continue
            nav_value = aligned.at[nav_date, product_key]
            if pd.isna(nav_value):
                continue
            nav_float = float(nav_value)
            initial_amount = float(amounts.get(product_key, 0.0))
            if initial_amount <= 0 or nav_float == 0:
                continue
            effective_entry_nav = inferred_entry_nav if inferred_entry_nav > 0 else nav_float
            if effective_entry_nav == 0:
                continue
            share_counts[product_key] = initial_amount / effective_entry_nav
            entry_nav_used[product_key] = float(effective_entry_nav)
            first_dates[product_key] = nav_date.strftime("%Y-%m-%d")
            contribution_amounts_today += initial_amount
            contribution_assets_today += share_counts[product_key] * nav_float

        date_asset = 0.0
        for product_key, shares in share_counts.items():
            nav_value = aligned.at[nav_date, product_key]
            if pd.isna(nav_value):
                continue
            asset = shares * float(nav_value)
            date_asset += asset

        if date_asset <= 0:
            continue

        if current_total_units == 0:
            current_total_units = contribution_amounts_today if contribution_amounts_today > 0 else date_asset
        else:
            if contribution_assets_today > 0 and previous_unit_nav > 0:
                current_total_units += contribution_assets_today / previous_unit_nav
        unit_nav = date_asset / current_total_units if current_total_units > 0 else previous_unit_nav

        previous_unit_nav = unit_nav
        portfolio_rows.append((nav_date, unit_nav, date_asset))

    if not portfolio_rows:
        return _empty_portfolio_result()

    portfolio_nav = pd.Series({nav_date: nav for nav_date, nav, _ in portfolio_rows}).sort_index()
    performance_nav = _with_inception_base(portfolio_nav)
    latest_nav_display = float(configured_latest_nav) if configured_latest_nav is not None else float(portfolio_nav.iloc[-1])
    total_asset = pd.Series({nav_date: asset for nav_date, _, asset in portfolio_rows}).sort_index()
    initial_investment_scale = float(amounts.sum())
    daily_returns = portfolio_nav.pct_change().dropna()
    weekly_nav = portfolio_nav.resample("W-FRI").last().dropna()
    latest_date = portfolio_nav.index.max()
    latest_trade_date = portfolio_nav.index.max()
    current_year = latest_date.year
    first_actual_date = portfolio_nav.index.min()
    base_date = portfolio_nav.index.min()
    weekly_return, weekly_anchor_date = _rolling_return(portfolio_nav, 7)
    ytd_reference_start = pd.Timestamp(year=current_year, month=1, day=1)
    ytd_window = portfolio_nav[(portfolio_nav.index >= ytd_reference_start) & (portfolio_nav.index <= latest_date)]
    ytd_anchor = portfolio_nav[portfolio_nav.index < ytd_reference_start]
    ytd_return = _period_return(
        portfolio_nav,
        ytd_reference_start,
        latest_date,
    )
    since_invest_return = (
        float(latest_nav_display / configured_initial_nav - 1)
        if configured_initial_nav > 0 and latest_nav_display is not None
        else None
    )
    annual_returns: list[dict[str, float | int]] = []
    for year in sorted({int(idx.year) for idx in portfolio_nav.index}, reverse=True):
        start = pd.Timestamp(year=year, month=1, day=1)
        end = pd.Timestamp(year=year, month=12, day=31)
        year_return = _period_return(portfolio_nav, start, min(end, latest_date))
        if year_return is None:
            continue
        annual_returns.append(
            {
                "year": int(year),
                "return": float(year_return),
            }
        )

    for product_key, initial_amount in amounts.items():
        series = aligned[product_key].dropna() if product_key in aligned.columns else pd.Series(dtype=float)
        if series.empty or product_key not in share_counts:
            continue
        latest_nav = float(series.iloc[-1])
        entry_nav = float(entry_nav_used.get(product_key, series.iloc[0]))
        positions.append(
            {
                "product_key": product_key,
                "product_name": name_map.get(product_key, product_key),
                "initial_investment_scale": float(initial_amount),
                "current_asset_scale": float(share_counts[product_key] * latest_nav),
                "first_invest_date": first_dates.get(product_key),
                "entry_nav": entry_nav,
                "latest_nav": latest_nav,
                "latest_observed_date": series.index[-1].strftime("%Y-%m-%d"),
                "stale_days": int((latest_trade_date - series.index[-1]).days),
                "entry_matches_latest_nav": bool(np.isclose(entry_nav, latest_nav, atol=1e-8)),
                "since_invest_return": float(latest_nav / entry_nav - 1) if entry_nav not in (None, 0) else None,
                "is_manual_only": False,
                "history_included": True,
            }
        )
    positions.sort(key=lambda item: str(item["product_name"]))

    recent_entry_threshold = latest_trade_date - pd.Timedelta(days=7)
    recent_entry_count = sum(
        1
        for item in positions
        if item.get("first_invest_date") and pd.Timestamp(item["first_invest_date"]) >= recent_entry_threshold
    )
    stale_position_count = sum(1 for item in positions if int(item.get("stale_days", 0) or 0) > 0)
    warnings: list[str] = []
    if len(portfolio_nav) < 5:
        warnings.append(f"组合净值样本仅 {len(portfolio_nav)} 个交易日，周度收益和风险指标会按可用样本计算。")
    if recent_entry_count >= max(1, len(positions) // 2):
        warnings.append(
            f"当前有 {recent_entry_count} 个持仓的首个可用净值日期落在最近 7 天内，说明这些产品本身同步历史较短，组合曲线会从这些产品开始有数据的日期起逐步纳入。"
        )
    if stale_position_count > 0:
        warnings.append(
            f"当前有 {stale_position_count} 个持仓最近净值日期早于组合最新日期，系统会沿用该产品最新一条净值继续估算规模。"
        )

    metrics = {
        "configured_initial_nav": float(configured_initial_nav),
        "configured_latest_nav": float(configured_latest_nav) if configured_latest_nav is not None else None,
        "computed_latest_nav": float(portfolio_nav.iloc[-1]),
        "latest_nav": latest_nav_display,
        "weekly_return": weekly_return,
        "weekly_anchor_date": weekly_anchor_date,
        "ytd_return": ytd_return,
        "since_invest_return": since_invest_return,
        "daily_max_drawdown": max_drawdown(portfolio_nav),
        "weekly_max_drawdown": max_drawdown(weekly_nav) if len(weekly_nav) >= 2 else max_drawdown(portfolio_nav),
        "sharpe_ratio": sharpe_ratio(daily_returns, risk_free_rate, annual_trading_days),
        "calmar_ratio": calmar_ratio(portfolio_nav, annual_trading_days),
        "current_asset_scale": float(total_asset.iloc[-1]),
        "initial_investment_scale": initial_investment_scale,
        "as_of_date": latest_date.strftime("%Y-%m-%d"),
        "base_date": base_date.strftime("%Y-%m-%d"),
        "first_actual_date": first_actual_date.strftime("%Y-%m-%d"),
        "history_points": int(len(portfolio_nav)),
        "history_days": int((latest_trade_date - first_actual_date).days),
        "stale_position_count": int(stale_position_count),
        "recent_entry_position_count": int(recent_entry_count),
        "manual_only_position_count": 0,
        "ytd_anchor_date": (
            ytd_anchor.index[-1].strftime("%Y-%m-%d")
            if not ytd_anchor.empty
            else (ytd_window.index[0].strftime("%Y-%m-%d") if not ytd_window.empty else None)
        ),
    }

    result = {
        "series": [
            {"date": idx.strftime("%Y-%m-%d"), "nav": round(float(value), 6)}
            for idx, value in portfolio_nav.items()
        ],
        "annual_returns": annual_returns,
        "product_series": {
            product_key: [
                {"date": idx.strftime("%Y-%m-%d"), "nav": round(float(value), 6)}
                for idx, value in aligned[product_key].dropna().items()
            ]
            for product_key in aligned.columns
            if product_key in name_map
        },
        "product_names": name_map,
        "positions": positions,
        "metrics": metrics,
        "warnings": warnings,
    }
    return _append_manual_positions(
        result,
        manual_positions,
        configured_initial_nav,
        configured_latest_nav,
        metrics.get("as_of_date"),
    )
