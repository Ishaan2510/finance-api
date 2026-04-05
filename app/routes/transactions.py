from datetime import date
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity

from app import db
from app.models.user import Role
from app.models.transaction import Transaction, TransactionType
from app.middleware.auth import require_auth, require_role, require_min_role
from app.utils.validators import validate_transaction
from app.utils.helpers import success, error, paginate_query

transactions_bp = Blueprint("transactions", __name__)


def _build_filter_query(args):
    """Parse query params into a filtered Transaction query."""
    query = Transaction.query.filter_by(is_deleted=False)

    # Type filter
    type_filter = args.get("type")
    if type_filter and type_filter in [t.value for t in TransactionType]:
        query = query.filter_by(type=TransactionType(type_filter))

    # Category filter
    category = args.get("category", "").strip()
    if category:
        query = query.filter(Transaction.category.ilike(f"%{category}%"))

    # Date range
    date_from = args.get("date_from")
    date_to = args.get("date_to")
    try:
        if date_from:
            query = query.filter(Transaction.date >= date.fromisoformat(date_from))
        if date_to:
            query = query.filter(Transaction.date <= date.fromisoformat(date_to))
    except ValueError:
        pass  # silently ignore malformed dates; validators handle user-facing errors

    # Creator filter (admin only — enforced at route level)
    created_by = args.get("created_by", type=int)
    if created_by:
        query = query.filter_by(created_by=created_by)

    return query


# ── READ ────────────────────────────────────────────────────────────────────


@transactions_bp.get("/")
@require_min_role(Role.VIEWER)
def list_transactions():
    """
    Viewer+: list transactions.
    Viewers see only their own; Analysts and Admins see all.
    """
    user_id = int(get_jwt_identity())
    from app.models.user import User
    caller = User.query.get(user_id)

    query = _build_filter_query(request.args)

    if caller.role == Role.VIEWER:
        query = query.filter_by(created_by=user_id)

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    result = paginate_query(query.order_by(Transaction.date.desc()), page, per_page)
    result["items"] = [t.to_dict() for t in result["items"]]
    return success(result)


@transactions_bp.get("/<int:tx_id>")
@require_min_role(Role.VIEWER)
def get_transaction(tx_id):
    user_id = int(get_jwt_identity())
    from app.models.user import User
    caller = User.query.get(user_id)

    tx = Transaction.query.filter_by(id=tx_id, is_deleted=False).first()
    if not tx:
        return error("Transaction not found.", 404)

    if caller.role == Role.VIEWER and tx.created_by != user_id:
        return error("You do not have access to this transaction.", 403)

    return success(tx.to_dict())


# ── WRITE ───────────────────────────────────────────────────────────────────


@transactions_bp.post("/")
@require_min_role(Role.ANALYST)
def create_transaction():
    """Analyst+: create a new transaction."""
    data = request.get_json(silent=True) or {}
    errors = validate_transaction(data)
    if errors:
        return error("Validation failed.", 422, errors)

    user_id = int(get_jwt_identity())
    tx = Transaction(
        amount=float(data["amount"]),
        type=TransactionType(data["type"]),
        category=data["category"].strip(),
        date=date.fromisoformat(data["date"]),
        notes=data.get("notes", "").strip() or None,
        created_by=user_id,
    )
    db.session.add(tx)
    db.session.commit()
    return success(tx.to_dict(), "Transaction created.", 201)


@transactions_bp.patch("/<int:tx_id>")
@require_min_role(Role.ANALYST)
def update_transaction(tx_id):
    """Analyst+: update own transactions. Admins can update any."""
    user_id = int(get_jwt_identity())
    from app.models.user import User
    caller = User.query.get(user_id)

    tx = Transaction.query.filter_by(id=tx_id, is_deleted=False).first()
    if not tx:
        return error("Transaction not found.", 404)

    if caller.role == Role.ANALYST and tx.created_by != user_id:
        return error("Analysts can only update their own transactions.", 403)

    data = request.get_json(silent=True) or {}

    if "amount" in data:
        try:
            amount = float(data["amount"])
            if amount <= 0:
                return error("amount must be positive.", 422)
            tx.amount = amount
        except (TypeError, ValueError):
            return error("amount must be a valid number.", 422)

    if "type" in data:
        if data["type"] not in [t.value for t in TransactionType]:
            return error(f"type must be one of: {[t.value for t in TransactionType]}.", 422)
        tx.type = TransactionType(data["type"])

    if "category" in data:
        if not data["category"].strip():
            return error("category cannot be empty.", 422)
        tx.category = data["category"].strip()

    if "date" in data:
        try:
            tx.date = date.fromisoformat(data["date"])
        except ValueError:
            return error("date must be in YYYY-MM-DD format.", 422)

    if "notes" in data:
        tx.notes = data["notes"].strip() or None

    db.session.commit()
    return success(tx.to_dict(), "Transaction updated.")


@transactions_bp.delete("/<int:tx_id>")
@require_min_role(Role.ANALYST)
def delete_transaction(tx_id):
    """Analyst+: soft-delete own transactions. Admins can delete any."""
    user_id = int(get_jwt_identity())
    from app.models.user import User
    caller = User.query.get(user_id)

    tx = Transaction.query.filter_by(id=tx_id, is_deleted=False).first()
    if not tx:
        return error("Transaction not found.", 404)

    if caller.role == Role.ANALYST and tx.created_by != user_id:
        return error("Analysts can only delete their own transactions.", 403)

    tx.is_deleted = True
    db.session.commit()
    return success(message="Transaction deleted.")
