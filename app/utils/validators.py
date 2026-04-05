from datetime import date
from app.models.user import Role
from app.models.transaction import TransactionType


def validate_register(data: dict) -> list[str]:
    errors = []
    if not data.get("name", "").strip():
        errors.append("name is required.")
    email = data.get("email", "").strip()
    if not email or "@" not in email:
        errors.append("A valid email is required.")
    password = data.get("password", "")
    if len(password) < 6:
        errors.append("Password must be at least 6 characters.")
    return errors


def validate_transaction(data: dict) -> list[str]:
    errors = []

    try:
        amount = float(data.get("amount", 0))
        if amount <= 0:
            errors.append("amount must be a positive number.")
    except (TypeError, ValueError):
        errors.append("amount must be a valid number.")

    if data.get("type") not in [t.value for t in TransactionType]:
        errors.append(f"type must be one of: {[t.value for t in TransactionType]}.")

    if not data.get("category", "").strip():
        errors.append("category is required.")

    date_str = data.get("date", "")
    if not date_str:
        errors.append("date is required (YYYY-MM-DD).")
    else:
        try:
            date.fromisoformat(date_str)
        except ValueError:
            errors.append("date must be in YYYY-MM-DD format.")

    return errors


def validate_role(role_str: str) -> list[str]:
    valid = [r.value for r in Role]
    if role_str not in valid:
        return [f"role must be one of: {valid}."]
    return []
