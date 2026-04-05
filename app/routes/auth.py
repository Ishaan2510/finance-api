from flask import Blueprint, request
from flask_jwt_extended import create_access_token, get_jwt_identity

from app import db
from app.models.user import User, Role
from app.middleware.auth import require_auth
from app.utils.validators import validate_register
from app.utils.helpers import success, error

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
def register():
    """
    Public registration — new users get Viewer role by default.
    Admins can assign roles via /api/users/:id/role.
    """
    data = request.get_json(silent=True) or {}
    errors = validate_register(data)
    if errors:
        return error("Validation failed.", 422, errors)

    if User.query.filter_by(email=data["email"].strip().lower()).first():
        return error("An account with this email already exists.", 409)

    user = User(
        name=data["name"].strip(),
        email=data["email"].strip().lower(),
        role=Role.VIEWER,
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return success(
        {"user": user.to_dict(), "access_token": token},
        "Account created successfully.",
        201,
    )


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return error("Email and password are required.", 422)

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return error("Invalid email or password.", 401)

    if not user.is_active:
        return error("This account has been deactivated.", 403)

    token = create_access_token(identity=str(user.id))
    return success(
        {"user": user.to_dict(), "access_token": token},
        "Logged in successfully.",
    )


@auth_bp.get("/me")
@require_auth
def me():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    return success(user.to_dict())
