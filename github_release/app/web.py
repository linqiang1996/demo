from __future__ import annotations

import logging
import os
import socket
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, Response, jsonify, redirect, render_template, request, send_from_directory, session, url_for

from .analytics import build_portfolio_nav, compute_product_snapshots, to_nav_frame
from .bootstrap import bootstrap_sample_nav_data
from .config import AppConfig, MailConfig, ensure_data_directories, load_env_file
from .db import Database
from .mail_sync import MailSyncService
from .product_names import looks_like_product_name, normalize_product_name, product_name_key


logging.basicConfig(level=logging.INFO)
AUTH_SESSION_KEY = "fof_authenticated"


def is_api_request() -> bool:
    return request.path.startswith("/api/")


def request_access_code() -> str:
    header_code = request.headers.get("X-FOF-Access-Code", "").strip()
    if header_code:
        return header_code
    param_code = request.args.get("access_code", "").strip()
    if param_code:
        return param_code
    body_code = request.form.get("access_code", "").strip()
    if body_code:
        return body_code
    return ""


def is_authorized(app_config: AppConfig) -> bool:
    if not app_config.access_code:
        return True
    if session.get(AUTH_SESSION_KEY) is True:
        return True
    return request_access_code() == app_config.access_code


def load_nav_dataframe(db: Database):
    rows = db.fetchall(
        """
        SELECT p.name AS product_key, p.display_name AS product_name, n.nav_date, n.nav_value
        FROM nav_records n
        JOIN products p ON p.id = n.product_id
        ORDER BY p.name, n.nav_date
        """
    )
    return to_nav_frame([dict(row) for row in rows])


def visible_product_keys(db: Database) -> tuple[list[str], bool]:
    rows = db.fetchall(
        """
        SELECT name, last_source
        FROM products
        ORDER BY name
        """
    )
    all_keys = [str(row["name"]) for row in rows if looks_like_product_name(str(row["name"]))]
    mail_keys = [str(row["name"]) for row in rows if row["last_source"] != "sample-excel" and looks_like_product_name(str(row["name"]))]
    if mail_keys:
        return mail_keys, True
    return all_keys, False


def filter_nav_dataframe(nav_df, product_keys: list[str]):
    if nav_df.empty or not product_keys:
        return nav_df.iloc[0:0].copy() if hasattr(nav_df, "iloc") else nav_df
    return nav_df[nav_df["product_key"].isin(product_keys)].copy()


def positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def default_entry_navs(nav_df) -> dict[str, float]:
    if nav_df.empty:
        return {}
    first_rows = (
        nav_df.sort_values(["product_key", "nav_date"])
        .dropna(subset=["nav_value"])
        .drop_duplicates(subset=["product_key"], keep="first")
    )
    return {str(row["product_key"]): float(row["nav_value"]) for _, row in first_rows.iterrows()}


def build_product_lookup(nav_df) -> dict[str, str]:
    lookup: dict[str, str] = {}
    if nav_df.empty:
        return lookup
    latest_rows = (
        nav_df.sort_values(["product_key", "nav_date"])
        .drop_duplicates(subset=["product_key"], keep="last")
    )
    for _, row in latest_rows.iterrows():
        product_key = str(row["product_key"])
        product_name = str(row["product_name"])
        candidates = {
            product_key,
            product_name,
            normalize_product_name(product_key),
            normalize_product_name(product_name),
            product_name_key(product_key),
            product_name_key(product_name),
        }
        for candidate in candidates:
            if candidate:
                lookup[candidate] = product_key
    return lookup


def resolve_product_key_by_name(product_name: str, product_lookup: dict[str, str]) -> str | None:
    clean_name = normalize_product_name(product_name)
    if not clean_name:
        return None
    return (
        product_lookup.get(clean_name)
        or product_lookup.get(product_name_key(clean_name))
        or product_lookup.get(product_name)
    )


def portfolio_settings(config: dict[str, Any] | None) -> dict[str, Any]:
    saved = config or {}
    return {
        "initial_nav": positive_float(saved.get("__portfolio_initial_nav")) if isinstance(saved, dict) else None,
        "latest_nav": positive_float(saved.get("__portfolio_latest_nav")) if isinstance(saved, dict) else None,
    }


def manual_portfolio_rows(config: dict[str, Any] | None) -> list[dict[str, Any]]:
    saved = config or {}
    rows: list[dict[str, Any]] = []
    raw_items = saved.get("__manual_products", []) if isinstance(saved, dict) else []
    if not isinstance(raw_items, list):
        return rows
    for idx, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        product_name = str(item.get("product_name", "")).strip()
        amount = positive_float(item.get("amount"))
        entry_nav = positive_float(item.get("entry_nav"))
        latest_nav = positive_float(item.get("latest_nav"))
        if not product_name and amount is None and entry_nav is None and latest_nav is None:
            continue
        product_key = str(item.get("product_key") or f"manual::{idx}")
        rows.append(
            {
                "product_key": product_key,
                "product_name": product_name,
                "amount": amount,
                "entry_nav": entry_nav,
                "manual_latest_nav": latest_nav,
                "default_entry_nav": None,
                "weight": None,
                "first_invest_date": None,
                "latest_nav": latest_nav,
                "is_manual": True,
            }
        )
    return rows


def resolve_portfolio_allocations(db: Database, product_keys: list[str], nav_df) -> tuple[dict[str, dict[str, float | None]], dict[str, Any], list[dict[str, Any]]]:
    saved = db.load_portfolio("default") or {}
    inferred_entry_navs = default_entry_navs(nav_df)
    product_lookup = build_product_lookup(nav_df)
    cleaned: dict[str, dict[str, float | None]] = {}
    for product_key in product_keys:
        value = saved.get(product_key)
        if value is None:
            continue
        amount = None
        entry_nav = None
        if isinstance(value, dict):
            amount = positive_float(value.get("amount"))
            entry_nav = positive_float(value.get("entry_nav"))
        else:
            amount = positive_float(value)
        if amount is None:
            continue
        cleaned[product_key] = {
            "amount": amount,
            "entry_nav": entry_nav or inferred_entry_navs.get(product_key),
        }
    settings = portfolio_settings(saved)
    unresolved_manual_rows: list[dict[str, Any]] = []
    for row in manual_portfolio_rows(saved):
        matched_key = resolve_product_key_by_name(str(row.get("product_name") or ""), product_lookup)
        if matched_key and matched_key not in cleaned and row.get("amount") is not None:
            cleaned[matched_key] = {
                "amount": row.get("amount"),
                "entry_nav": row.get("entry_nav") or inferred_entry_navs.get(matched_key),
            }
            continue
        unresolved_manual_rows.append(row)
    merged_to_save: dict[str, Any] = dict(cleaned)
    if settings.get("initial_nav") is not None:
        merged_to_save["__portfolio_initial_nav"] = settings["initial_nav"]
    if settings.get("latest_nav") is not None:
        merged_to_save["__portfolio_latest_nav"] = settings["latest_nav"]
    if unresolved_manual_rows:
        merged_to_save["__manual_products"] = [
            {
                "product_key": row["product_key"],
                "product_name": row["product_name"],
                "amount": row["amount"],
                "entry_nav": row["entry_nav"],
                "latest_nav": row.get("manual_latest_nav"),
            }
            for row in unresolved_manual_rows
        ]
    if merged_to_save != saved:
        db.save_portfolio("default", merged_to_save)
    return cleaned, settings, unresolved_manual_rows


def build_portfolio_form_rows(
    products,
    allocations: dict[str, dict[str, float | None]],
    inferred_entry_navs: dict[str, float],
    manual_rows: list[dict[str, Any]] | None = None,
) -> tuple[list[dict], float]:
    manual_rows = manual_rows or []
    total_amount = sum((value.get("amount") or 0.0) for value in allocations.values()) + sum((row.get("amount") or 0.0) for row in manual_rows)
    rows: list[dict] = []
    for product in products:
        position = allocations.get(product.product_key, {})
        amount = position.get("amount")
        default_entry_nav = inferred_entry_navs.get(product.product_key)
        entry_nav = position.get("entry_nav") or default_entry_nav
        weight = amount / total_amount if amount and total_amount > 0 else None
        rows.append(
            {
                "product_key": product.product_key,
                "product_name": product.product_name,
                "amount": amount,
                "entry_nav": entry_nav,
                "default_entry_nav": default_entry_nav,
                "weight": weight,
                "first_invest_date": product.first_invest_date,
                "latest_nav": product.latest_nav,
                "is_manual": False,
            }
        )
    for row in manual_rows:
        amount = row.get("amount")
        rows.append(
            {
                **row,
                "weight": amount / total_amount if amount and total_amount > 0 else None,
            }
        )
    return rows, total_amount


def create_app() -> Flask:
    load_env_file()
    ensure_data_directories()
    app_config = AppConfig()
    mail_config = MailConfig()
    db = Database(app_config.database_url)
    db.initialize()

    if app_config.bootstrap_samples:
        bootstrap_sample_nav_data(db, app_config.sample_data_dir)

    mail_sync = MailSyncService(db, mail_config)
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    sync_lock = threading.Lock()

    def run_mail_sync(full_rescan: bool = False, reprocess_existing: bool = False):
        if not sync_lock.acquire(blocking=False):
            raise RuntimeError("邮箱同步进行中，请稍后再试")
        try:
            result = mail_sync.sync(full_rescan=full_rescan, reprocess_existing=reprocess_existing)
            logging.info("mail sync finished: %s messages, %s records", result.synced_messages, result.inserted_records)
            return result
        except Exception:
            logging.exception("mail sync failed")
            raise
        finally:
            sync_lock.release()

    def scheduled_sync() -> None:
        try:
            run_mail_sync()
        except RuntimeError:
            logging.info("mail sync skipped because another sync is already running")
        except Exception:
            logging.exception("scheduled mail sync failed")

    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parent / "templates"))
    static_dir = Path(__file__).resolve().parent / "static"
    app.permanent_session_lifetime = timedelta(days=30)
    should_start_scheduler = not scheduler.get_jobs()
    if should_start_scheduler:
        scheduler.add_job(scheduled_sync, "interval", minutes=mail_config.poll_minutes, id="mail-sync", replace_existing=True)
    reloader_active = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if should_start_scheduler and (reloader_active or os.environ.get("FLASK_DEBUG") not in {"1", "true"}):
        scheduler.start()

    app.config["SECRET_KEY"] = app_config.secret_key
    app.config["db"] = db
    app.config["mail_sync"] = mail_sync
    app.config["app_config"] = app_config
    app.config["mail_config"] = mail_config

    if mail_config.configured:
        try:
            run_mail_sync()
        except RuntimeError:
            logging.info("startup mail sync skipped because another sync is already running")
        except Exception:
            logging.exception("startup mail sync failed")

    @app.before_request
    def require_access() -> Any:
        allowed_paths = {"/login", "/healthz", "/manifest.webmanifest", "/sw.js"}
        if request.path.startswith("/static/") or request.path in allowed_paths:
            return None
        if is_authorized(app_config):
            if app_config.access_code:
                session[AUTH_SESSION_KEY] = True
                session.permanent = True
            return None
        if is_api_request():
            return jsonify({"ok": False, "error": "未授权，请先提供访问口令"}), 401
        return redirect(url_for("login", next=request.path))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = ""
        next_url = request.values.get("next", "/") or "/"
        if not app_config.access_code:
            session[AUTH_SESSION_KEY] = True
            return redirect(next_url)
        if request.method == "POST":
            code = request.form.get("access_code", "").strip()
            if code == app_config.access_code:
                session[AUTH_SESSION_KEY] = True
                session.permanent = True
                return redirect(next_url)
            error = "访问口令不正确"
        return render_template("login.html", error=error, next_url=next_url)

    @app.post("/logout")
    def logout():
        session.pop(AUTH_SESSION_KEY, None)
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            local_ip = "127.0.0.1"
        all_nav_df = load_nav_dataframe(db)
        product_keys, using_mail_products = visible_product_keys(db)
        nav_df = filter_nav_dataframe(all_nav_df, product_keys)
        inferred_entry_navs = default_entry_navs(nav_df)
        snapshots = compute_product_snapshots(nav_df)
        sync_state = db.get_sync_state()
        selected_portfolio, selected_settings, manual_rows = resolve_portfolio_allocations(db, product_keys, nav_df)
        portfolio_rows, total_amount = build_portfolio_form_rows(snapshots, selected_portfolio, inferred_entry_navs, manual_rows)
        portfolio = build_portfolio_nav(
            nav_df,
            selected_portfolio,
            risk_free_rate=app_config.risk_free_rate,
            annual_trading_days=app_config.annual_trading_days,
            weekly_periods=app_config.weekly_periods,
            initial_portfolio_nav=selected_settings.get("initial_nav"),
            latest_portfolio_nav=selected_settings.get("latest_nav"),
            manual_positions=manual_rows,
        )
        return render_template(
            "index.html",
            products=snapshots,
            sync_state=sync_state,
            portfolio_allocations=selected_portfolio,
            portfolio_settings=selected_settings,
            portfolio_rows=portfolio_rows,
            portfolio_total_amount=total_amount,
            portfolio=portfolio,
            mail_configured=mail_config.configured,
            mail_poll_minutes=mail_config.poll_minutes,
            local_ip=local_ip,
            using_mail_products=using_mail_products,
        )

    @app.post("/portfolio")
    def save_portfolio():
        available_keys, _ = visible_product_keys(db)
        all_nav_df = load_nav_dataframe(db)
        nav_df = filter_nav_dataframe(all_nav_df, available_keys)
        inferred_entry_navs = default_entry_navs(nav_df)
        product_lookup = build_product_lookup(nav_df)
        allocations: dict[str, Any] = {}
        for product_key in available_keys:
            raw_value = request.form.get(f"amount::{product_key}", "").strip()
            if not raw_value:
                continue
            amount = positive_float(raw_value)
            if amount is None:
                continue
            entry_nav = positive_float(request.form.get(f"entry_nav::{product_key}", "").strip())
            allocations[product_key] = {
                "amount": amount,
                "entry_nav": entry_nav or inferred_entry_navs.get(product_key),
            }
        initial_portfolio_nav = positive_float(request.form.get("portfolio_initial_nav", "").strip())
        if initial_portfolio_nav is not None:
            allocations["__portfolio_initial_nav"] = initial_portfolio_nav
        latest_portfolio_nav = positive_float(request.form.get("portfolio_latest_nav", "").strip())
        if latest_portfolio_nav is not None:
            allocations["__portfolio_latest_nav"] = latest_portfolio_nav
        manual_products: list[dict[str, Any]] = []
        manual_names = request.form.getlist("manual_product_name[]")
        manual_selected_keys = request.form.getlist("manual_product_key[]")
        manual_amounts = request.form.getlist("manual_amount[]")
        manual_entry_navs = request.form.getlist("manual_entry_nav[]")
        manual_latest_navs = request.form.getlist("manual_latest_nav[]")
        for idx, product_name in enumerate(manual_names):
            selected_key = str(manual_selected_keys[idx] if idx < len(manual_selected_keys) else "").strip()
            clean_name = str(product_name or "").strip()
            amount = positive_float(manual_amounts[idx] if idx < len(manual_amounts) else "")
            entry_nav = positive_float(manual_entry_navs[idx] if idx < len(manual_entry_navs) else "")
            latest_nav = positive_float(manual_latest_navs[idx] if idx < len(manual_latest_navs) else "")
            chosen_name = clean_name
            matched_key = None
            if selected_key:
                matched_key = selected_key
                chosen_name = clean_name or selected_key
            else:
                matched_key = resolve_product_key_by_name(clean_name, product_lookup)
            if not chosen_name and amount is None and entry_nav is None and latest_nav is None:
                continue
            if matched_key and amount is not None and matched_key not in allocations:
                allocations[matched_key] = {
                    "amount": amount,
                    "entry_nav": entry_nav or inferred_entry_navs.get(matched_key),
                }
                continue
            manual_products.append(
                {
                    "product_key": f"manual::{idx}",
                    "product_name": chosen_name,
                    "amount": amount,
                    "entry_nav": entry_nav,
                    "latest_nav": latest_nav,
                }
            )
        if manual_products:
            allocations["__manual_products"] = manual_products
        db.save_portfolio("default", allocations)
        return redirect(url_for("index"))

    @app.post("/sync")
    def sync_now():
        try:
            full_rescan = str(request.args.get("full", "")).lower() in {"1", "true", "yes", "on"}
            if not full_rescan:
                full_rescan = True
            reprocess_existing = str(request.args.get("reprocess", "0")).lower() in {"1", "true", "yes", "on"}
            result = run_mail_sync(full_rescan=full_rescan, reprocess_existing=reprocess_existing)
            return jsonify(
                {
                    "ok": True,
                    "full_rescan": full_rescan,
                    "reprocess_existing": reprocess_existing,
                    "searched_messages": result.searched_messages,
                    "synced_messages": result.synced_messages,
                    "skipped_processed_messages": result.skipped_processed_messages,
                    "inserted_records": result.inserted_records,
                    "last_uid": result.last_uid,
                    "last_message_id": result.last_message_id,
                    "last_synced_at": result.last_synced_at,
                }
            )
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get("/api/products")
    def api_products():
        all_nav_df = load_nav_dataframe(db)
        product_keys, _ = visible_product_keys(db)
        nav_df = filter_nav_dataframe(all_nav_df, product_keys)
        products = [
            {
                "product_key": item.product_key,
                "product_name": item.product_name,
                "first_invest_date": item.first_invest_date,
                "latest_date": item.latest_date,
                "latest_nav": item.latest_nav,
                "daily_return": item.daily_return,
                "weekly_return": item.weekly_return,
                "since_invest_return": item.since_invest_return,
            }
            for item in compute_product_snapshots(nav_df)
        ]
        return jsonify(products)

    @app.get("/api/portfolio")
    def api_portfolio():
        all_nav_df = load_nav_dataframe(db)
        product_keys, _ = visible_product_keys(db)
        nav_df = filter_nav_dataframe(all_nav_df, product_keys)
        allocations, settings, manual_rows = resolve_portfolio_allocations(db, product_keys, nav_df)
        portfolio = build_portfolio_nav(
            nav_df,
            allocations,
            risk_free_rate=app_config.risk_free_rate,
            annual_trading_days=app_config.annual_trading_days,
            weekly_periods=app_config.weekly_periods,
            initial_portfolio_nav=settings.get("initial_nav"),
            latest_portfolio_nav=settings.get("latest_nav"),
            manual_positions=manual_rows,
        )
        portfolio["allocations"] = allocations
        portfolio["settings"] = settings
        portfolio["manual_products"] = manual_rows
        return jsonify(portfolio)

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.get("/manifest.webmanifest")
    def web_manifest():
        payload = {
            "name": "FOF净值跟踪看板",
            "short_name": "FOF看板",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#eef6ff",
            "theme_color": "#0f766e",
            "icons": [],
        }
        return jsonify(payload)

    @app.get("/sw.js")
    def service_worker():
        response = send_from_directory(static_dir, "sw.js")
        response.headers["Content-Type"] = "application/javascript"
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/api/offline-snapshot")
    def api_offline_snapshot():
        all_nav_df = load_nav_dataframe(db)
        product_keys, _ = visible_product_keys(db)
        nav_df = filter_nav_dataframe(all_nav_df, product_keys)
        allocations, settings, manual_rows = resolve_portfolio_allocations(db, product_keys, nav_df)
        portfolio = build_portfolio_nav(
            nav_df,
            allocations,
            risk_free_rate=app_config.risk_free_rate,
            annual_trading_days=app_config.annual_trading_days,
            weekly_periods=app_config.weekly_periods,
            initial_portfolio_nav=settings.get("initial_nav"),
            latest_portfolio_nav=settings.get("latest_nav"),
            manual_positions=manual_rows,
        )
        products = [
            {
                "product_key": item.product_key,
                "product_name": item.product_name,
                "first_invest_date": item.first_invest_date,
                "latest_date": item.latest_date,
                "latest_nav": item.latest_nav,
                "daily_return": item.daily_return,
                "weekly_return": item.weekly_return,
                "since_invest_return": item.since_invest_return,
            }
            for item in compute_product_snapshots(nav_df)
        ]
        return jsonify(
            {
                "products": products,
                "portfolio": portfolio,
                "settings": settings,
                "manual_products": manual_rows,
                "sync_state": db.get_sync_state(),
            }
        )

    return app
