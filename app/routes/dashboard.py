from datetime import date, timedelta
from collections import defaultdict

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import func

from app import db
from app.models.user import User, Role
from app.models.transaction import Transaction, TransactionType
from app.middleware.auth import require_min_role
from app.utils.helpers import success, error

dashboard_bp = Blueprint("dashboard", __name__)


def _base_query(caller: User):
    """Viewers see only their own data; Analysts and Admins see everything."""
    query = Transaction.query.filter_by(is_deleted=False)
    if caller.role == Role.VIEWER:
        query = query.filter_by(created_by=caller.id)
    return query


# ── SUMMARY ─────────────────────────────────────────────────────────────────


@dashboard_bp.get("/summary")
@require_min_role(Role.VIEWER)
def summary():
    """
    Top-level dashboard numbers:
      - total income, total expenses, net balance
      - count of transactions
    Supports optional date_from / date_to filters.
    """
    caller = User.query.get(int(get_jwt_identity()))
    query = _base_query(caller)

    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    try:
        if date_from:
            query = query.filter(Transaction.date >= date.fromisoformat(date_from))
        if date_to:
            query = query.filter(Transaction.date <= date.fromisoformat(date_to))
    except ValueError:
        return error("date_from / date_to must be in YYYY-MM-DD format.", 422)

    rows = query.with_entities(Transaction.type, func.sum(Transaction.amount)).group_by(
        Transaction.type
    ).all()

    totals = {TransactionType.INCOME: 0.0, TransactionType.EXPENSE: 0.0}
    for tx_type, total in rows:
        totals[tx_type] = float(total)

    income = totals[TransactionType.INCOME]
    expenses = totals[TransactionType.EXPENSE]
    tx_count = query.count()

    return success({
        "total_income": income,
        "total_expenses": expenses,
        "net_balance": round(income - expenses, 2),
        "transaction_count": tx_count,
    })


# ── CATEGORY BREAKDOWN ───────────────────────────────────────────────────────


@dashboard_bp.get("/by-category")
@require_min_role(Role.ANALYST)
def by_category():
    """
    Analyst+: totals grouped by category and type.
    Useful for pie / bar charts on the dashboard.
    """
    caller = User.query.get(int(get_jwt_identity()))
    query = _base_query(caller)

    type_filter = request.args.get("type")
    if type_filter and type_filter in [t.value for t in TransactionType]:
        query = query.filter_by(type=TransactionType(type_filter))

    rows = (
        query.with_entities(
            Transaction.category,
            Transaction.type,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .group_by(Transaction.category, Transaction.type)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    result = [
        {
            "category": r.category,
            "type": r.type.value,
            "total": float(r.total),
            "count": r.count,
        }
        for r in rows
    ]

    return success(result)


# ── MONTHLY TRENDS ───────────────────────────────────────────────────────────


@dashboard_bp.get("/monthly-trends")
@require_min_role(Role.ANALYST)
def monthly_trends():
    """
    Analyst+: income vs expenses aggregated by month for the given year.
    Defaults to current year. Pass ?year=2023 to override.
    """
    caller = User.query.get(int(get_jwt_identity()))

    try:
        year = int(request.args.get("year", date.today().year))
    except ValueError:
        return error("year must be a valid integer.", 422)

    query = _base_query(caller).filter(
        func.strftime("%Y", Transaction.date) == str(year)
    )

    rows = (
        query.with_entities(
            func.strftime("%m", Transaction.date).label("month"),
            Transaction.type,
            func.sum(Transaction.amount).label("total"),
        )
        .group_by("month", Transaction.type)
        .order_by("month")
        .all()
    )

    # Build a complete 12-month skeleton
    months = {str(m).zfill(2): {"income": 0.0, "expense": 0.0} for m in range(1, 13)}
    for r in rows:
        months[r.month][r.type.value] += float(r.total)

    result = [
        {
            "month": f"{year}-{m}",
            "income": v["income"],
            "expenses": v["expense"],
            "net": round(v["income"] - v["expense"], 2),
        }
        for m, v in months.items()
    ]

    return success({"year": year, "months": result})


# ── WEEKLY TRENDS ────────────────────────────────────────────────────────────


@dashboard_bp.get("/weekly-trends")
@require_min_role(Role.ANALYST)
def weekly_trends():
    """
    Analyst+: income vs expenses for each of the last N weeks.
    Pass ?weeks=8 (default 4, max 52).
    """
    caller = User.query.get(int(get_jwt_identity()))

    try:
        num_weeks = min(int(request.args.get("weeks", 4)), 52)
    except ValueError:
        return error("weeks must be a valid integer.", 422)

    today = date.today()
    start = today - timedelta(weeks=num_weeks)

    query = _base_query(caller).filter(Transaction.date >= start)

    rows = (
        query.with_entities(
            func.strftime("%Y-%W", Transaction.date).label("week"),
            Transaction.type,
            func.sum(Transaction.amount).label("total"),
        )
        .group_by("week", Transaction.type)
        .order_by("week")
        .all()
    )

    weekly: dict = defaultdict(lambda: {"income": 0.0, "expenses": 0.0})
    for r in rows:
        key = r.week
        if r.type == TransactionType.INCOME:
            weekly[key]["income"] += float(r.total)
        else:
            weekly[key]["expenses"] += float(r.total)

    result = [
        {
            "week": w,
            "income": v["income"],
            "expenses": v["expenses"],
            "net": round(v["income"] - v["expenses"], 2),
        }
        for w, v in sorted(weekly.items())
    ]

    return success({"weeks": result})


# ── RECENT ACTIVITY ──────────────────────────────────────────────────────────


@dashboard_bp.get("/recent")
@require_min_role(Role.VIEWER)
def recent_activity():
    """
    Latest N transactions. Pass ?limit=10 (default 10, max 50).
    Viewers see only their own; Analysts/Admins see all.
    """
    caller = User.query.get(int(get_jwt_identity()))

    try:
        limit = min(int(request.args.get("limit", 10)), 50)
    except ValueError:
        return error("limit must be a valid integer.", 422)

    txs = (
        _base_query(caller)
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .limit(limit)
        .all()
    )

    return success([t.to_dict() for t in txs])
