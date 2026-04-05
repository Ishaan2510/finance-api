from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity

from app import db
from app.models.user import User, Role
from app.middleware.auth import require_auth, require_role
from app.utils.validators import validate_register, validate_role
from app.utils.helpers import success, error, paginate_query

users_bp = Blueprint("users", __name__)


@users_bp.get("/")
@require_role(Role.ADMIN)
def list_users():
    """Admin — list all users with optional filters."""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    role_filter = request.args.get("role")
    active_filter = request.args.get("is_active")

    query = User.query

    if role_filter and role_filter in [r.value for r in Role]:
        query = query.filter_by(role=Role(role_filter))

    if active_filter is not None:
        query = query.filter_by(is_active=active_filter.lower() == "true")

    result = paginate_query(query.order_by(User.created_at.desc()), page, per_page)
    result["items"] = [u.to_dict() for u in result["items"]]
    return success(result)


@users_bp.post("/")
@require_role(Role.ADMIN)
def create_user():
    """Admin — create a user with any role."""
    data = request.get_json(silent=True) or {}
    errors = validate_register(data)
    if errors:
        return error("Validation failed.", 422, errors)

    role_str = data.get("role", Role.VIEWER.value)
    role_errors = validate_role(role_str)
    if role_errors:
        return error("Validation failed.", 422, role_errors)

    if User.query.filter_by(email=data["email"].strip().lower()).first():
        return error("An account with this email already exists.", 409)

    user = User(
        name=data["name"].strip(),
        email=data["email"].strip().lower(),
        role=Role(role_str),
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()

    return success(user.to_dict(), "User created.", 201)


@users_bp.get("/<int:user_id>")
@require_role(Role.ADMIN)
def get_user(user_id):
    user = User.query.get_or_404(user_id, description="User not found.")
    return success(user.to_dict())


@users_bp.patch("/<int:user_id>")
@require_role(Role.ADMIN)
def update_user(user_id):
    """Admin — update name, email, or active status."""
    user = User.query.get_or_404(user_id, description="User not found.")
    data = request.get_json(silent=True) or {}

    if "name" in data:
        if not data["name"].strip():
            return error("name cannot be empty.", 422)
        user.name = data["name"].strip()

    if "email" in data:
        new_email = data["email"].strip().lower()
        if "@" not in new_email:
            return error("A valid email is required.", 422)
        existing = User.query.filter_by(email=new_email).first()
        if existing and existing.id != user_id:
            return error("Email already in use.", 409)
        user.email = new_email

    if "is_active" in data:
        if not isinstance(data["is_active"], bool):
            return error("is_active must be a boolean.", 422)
        # Prevent admin from deactivating themselves
        caller_id = int(get_jwt_identity())
        if caller_id == user_id and not data["is_active"]:
            return error("You cannot deactivate your own account.", 403)
        user.is_active = data["is_active"]

    db.session.commit()
    return success(user.to_dict(), "User updated.")


@users_bp.patch("/<int:user_id>/role")
@require_role(Role.ADMIN)
def update_role(user_id):
    """Admin — assign a new role to a user."""
    caller_id = int(get_jwt_identity())
    if caller_id == user_id:
        return error("You cannot change your own role.", 403)

    user = User.query.get_or_404(user_id, description="User not found.")
    data = request.get_json(silent=True) or {}
    role_str = data.get("role", "")
    errors = validate_role(role_str)
    if errors:
        return error("Validation failed.", 422, errors)

    user.role = Role(role_str)
    db.session.commit()
    return success(user.to_dict(), f"Role updated to '{role_str}'.")


@users_bp.delete("/<int:user_id>")
@require_role(Role.ADMIN)
def delete_user(user_id):
    """Admin — soft-delete by deactivating."""
    caller_id = int(get_jwt_identity())
    if caller_id == user_id:
        return error("You cannot delete your own account.", 403)

    user = User.query.get_or_404(user_id, description="User not found.")
    user.is_active = False
    db.session.commit()
    return success(message="User deactivated.")
