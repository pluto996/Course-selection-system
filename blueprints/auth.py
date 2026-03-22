import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
from utils.audit import log_action, LOGIN, LOGOUT, PASSWORD_CHANGE

auth_bp = Blueprint('auth', __name__)


def _redirect_by_role(user):
    """根据角色重定向到对应首页"""
    if user.role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif user.role == 'teacher':
        return redirect(url_for('teacher.dashboard'))
    else:
        return redirect(url_for('student.schedule'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()
        success = user is not None and user.check_password(password) and user.is_active

        if success:
            login_user(user, remember=False)
            log_action(LOGIN, 'success', f'IP: {request.remote_addr}', user_id=user.id)

            if user.must_change_password:
                flash('首次登录请修改密码', 'warning')
                return redirect(url_for('auth.change_password'))

            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return _redirect_by_role(user)
        else:
            if user:
                log_action(LOGIN, 'failure', f'用户名: {username}', operator=username)
            flash('用户名或密码错误', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    username = current_user.username
    log_action(LOGOUT, 'success', f'用户 {username} 登出')
    logout_user()
    session.clear()
    flash('已成功退出登录', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old_password = request.form.get('old_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not current_user.check_password(old_password):
            flash('旧密码错误', 'danger')
            return render_template('auth/change_password.html')

        if new_password != confirm_password:
            flash('两次输入的新密码不一致', 'danger')
            return render_template('auth/change_password.html')

        if not User.validate_password_policy(new_password):
            flash('新密码不符合要求：长度至少8位，且包含字母和数字', 'danger')
            return render_template('auth/change_password.html')

        if old_password == new_password:
            flash('新密码不能与旧密码相同', 'danger')
            return render_template('auth/change_password.html')

        current_user.set_password(new_password)
        current_user.must_change_password = False
        db.session.commit()
        log_action(PASSWORD_CHANGE, 'success', '用户修改了密码')
        flash('密码修改成功', 'success')
        return _redirect_by_role(current_user)

    return render_template('auth/change_password.html')
