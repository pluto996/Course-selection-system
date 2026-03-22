from functools import wraps
from flask import abort
from flask_login import current_user


def role_required(*roles):
    """通用角色权限装饰器，支持多角色"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def admin_required(f):
    """仅管理员可访问"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated


def teacher_required(f):
    """管理员和教师可访问"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if current_user.role not in ('admin', 'teacher'):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def student_required(f):
    """所有已登录角色可访问"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if current_user.role not in ('admin', 'teacher', 'student'):
            abort(403)
        return f(*args, **kwargs)
    return decorated
