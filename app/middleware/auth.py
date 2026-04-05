from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from app.models.user import User, Role


def _current_user() -> User | None:
    user_id = get_jwt_identity()
    return User.query.get(user_id)


def _role_rank(role: Role) -> int:
    return {Role.VIEWER: 0, Role.ANALYST: 1, Role.ADMIN: 2}[role]


def require_auth(fn):
    """Ensure request carries a valid JWT and the user is active."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user = _current_user()
        if not user or not user.is_active:
            return jsonify({"error": "Account inactive or not found."}), 403
        return fn(*args, **kwargs)
    return wrapper


def require_role(*roles: Role):
    """Ensure the authenticated user has one of the required roles."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = _current_user()
            if not user or not user.is_active:
                return jsonify({"error": "Account inactive or not found."}), 403
            if user.role not in roles:
                return jsonify({
                    "error": "Insufficient permissions.",
                    "required_roles": [r.value for r in roles],
                    "your_role": user.role.value,
                }), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def require_min_role(min_role: Role):
    """Ensure the user's role is at least as privileged as min_role."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = _current_user()
            if not user or not user.is_active:
                return jsonify({"error": "Account inactive or not found."}), 403
            if _role_rank(user.role) < _role_rank(min_role):
                return jsonify({
                    "error": "Insufficient permissions.",
                    "minimum_required": min_role.value,
                    "your_role": user.role.value,
                }), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator
