import csv
import io
import string
import secrets
import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, g
from flask_login import login_required, current_user
from models import db, User, Teacher, Course, Room, AuditLog, Notification, CourseApplication, LoginRecord
from decorators import admin_required
from utils.audit import log_action, USER_CREATE, USER_DISABLE, USER_ENABLE, PASSWORD_RESET, NOTIFICATION_PUBLISH, APPLICATION_REVIEW

admin_bp = Blueprint('admin', __name__)


def _inject_unread():
    from models import Notification
    return Notification.unread_count(current_user.id) if current_user.is_authenticated else 0


@admin_bp.context_processor
def inject_unread():
    return {'unread_count': _inject_unread()}


# ── 仪表盘 ────────────────────────────────────────────────────
@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    total_users = User.query.count()
    total_courses = Course.query.count()
    total_rooms = Room.query.count()
    total_teachers = Teacher.query.count()

    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           total_courses=total_courses,
                           total_rooms=total_rooms,
                           total_teachers=total_teachers,
                           now=datetime.datetime.now())


# ── 排课结果 ──────────────────────────────────────────────────
@admin_bp.route('/schedule-result')
@login_required
@admin_required
def schedule_result():
    from app import scheduler, DAYS, DAY_NAMES_MAP, SECTIONS
    schedule_data = scheduler.get_result()
    schedule_teachers = sorted(set(item['teacher'] for item in schedule_data)) if schedule_data else []
    schedule_rooms = sorted(set(item['room'] for item in schedule_data)) if schedule_data else []

    # 多目标最终值
    prog = scheduler.get_progress()
    obj_values = {
        'f1': prog.get('f1', prog.get('hard_conflicts', '-')),
        'f2': round(float(prog.get('f2', 0)), 4) if prog.get('f2') is not None else '-',
        'f3': round(float(prog.get('f3', 0)), 4) if prog.get('f3') is not None else '-',
        'status': prog.get('status', 'IDLE'),
        'generation': prog.get('generation', 0),
    }
    # 教室利用率：已分配教室数 / 总教室数
    total_rooms = len(set(item['room'] for item in schedule_data)) if schedule_data else 0
    from models import Room
    all_rooms = Room.query.count()
    obj_values['room_util'] = round(total_rooms / all_rooms * 100, 1) if all_rooms else 0

    return render_template('admin/schedule_result.html',
                           schedule_data=schedule_data,
                           schedule_teachers=schedule_teachers,
                           schedule_rooms=schedule_rooms,
                           schedule_days=DAYS,
                           schedule_day_names=DAY_NAMES_MAP,
                           schedule_sections=SECTIONS,
                           obj_values=obj_values,
                           now=datetime.datetime.now())


# ── 用户管理 ──────────────────────────────────────────────────
@admin_bp.route('/users')
@login_required
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    role_filter = request.args.get('role', '')
    status_filter = request.args.get('status', '')

    query = User.query
    if role_filter:
        query = query.filter_by(role=role_filter)
    if status_filter == 'active':
        query = query.filter_by(_is_active=True)
    elif status_filter == 'inactive':
        query = query.filter_by(_is_active=False)

    pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    teachers = Teacher.query.order_by(Teacher.name).all()
    return render_template('admin/users.html', pagination=pagination, teachers=teachers,
                           role_filter=role_filter, status_filter=status_filter, per_page=per_page)


@admin_bp.route('/users/create', methods=['POST'])
@login_required
@admin_required
def create_user():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'student')
    display_name = request.form.get('display_name', '').strip() or username
    teacher_id = request.form.get('teacher_id', type=int)

    if not username or not password:
        flash('用户名和密码不能为空', 'danger')
        return redirect(url_for('admin.users'))

    if User.query.filter_by(username=username).first():
        flash(f'用户名 "{username}" 已存在', 'danger')
        return redirect(url_for('admin.users'))

    if role not in ('admin', 'teacher', 'student'):
        flash('无效的角色', 'danger')
        return redirect(url_for('admin.users'))

    user = User(username=username, role=role, display_name=display_name)
    user.set_password(password)
    if role == 'teacher' and teacher_id:
        user.teacher_id = teacher_id
    db.session.add(user)
    db.session.commit()
    log_action(USER_CREATE, 'success', f'创建用户：{username}（{role}）')
    flash(f'用户 {username} 创建成功', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({'code': 1, 'message': '不能停用自己的账号'}), 400
    user.is_active = not user.is_active
    db.session.commit()
    action = USER_ENABLE if user.is_active else USER_DISABLE
    log_action(action, 'success', f'用户 {user.username} 状态变更为 {"启用" if user.is_active else "停用"}')
    return jsonify({'code': 0, 'is_active': user.is_active,
                    'message': f'用户已{"启用" if user.is_active else "停用"}'})


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    alphabet = string.ascii_letters + string.digits
    new_pwd = ''.join(secrets.choice(alphabet) for _ in range(12))
    user.set_password(new_pwd)
    user.must_change_password = True
    db.session.commit()
    log_action(PASSWORD_RESET, 'success', f'重置用户 {user.username} 的密码')
    return jsonify({'code': 0, 'password': new_pwd, 'message': '密码已重置'})


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    from models import LoginRecord, CourseApplication, CourseReview, Notification
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({'code': 1, 'message': '不能删除自己的账号'}), 400
    username = user.username
    # 先删除所有关联子记录，避免外键/NOT NULL 约束错误
    LoginRecord.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    Notification.query.filter_by(recipient_id=user_id).delete(synchronize_session=False)
    CourseApplication.query.filter_by(student_id=user_id).delete(synchronize_session=False)
    CourseReview.query.filter_by(student_id=user_id).delete(synchronize_session=False)
    db.session.flush()  # 确保子记录先落地，再删主记录
    db.session.delete(user)
    db.session.commit()
    log_action(USER_DISABLE, 'success', f'删除用户：{username}')
    return jsonify({'code': 0, 'message': f'用户 {username} 已删除'})


# ── 审计日志 ──────────────────────────────────────────────────
@admin_bp.route('/audit-log')
@login_required
@admin_required
def audit_log():
    page = request.args.get('page', 1, type=int)
    operator = request.args.get('operator', '').strip()
    action_type = request.args.get('action_type', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    export = request.args.get('export', '')

    query = AuditLog.query
    if operator:
        query = query.filter(AuditLog.operator.ilike(f'%{operator}%'))
    if action_type:
        query = query.filter_by(action_type=action_type)
    if start_date:
        try:
            query = query.filter(AuditLog.created_at >= datetime.datetime.strptime(start_date, '%Y-%m-%d'))
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.datetime.strptime(end_date, '%Y-%m-%d') + datetime.timedelta(days=1)
            query = query.filter(AuditLog.created_at < end_dt)
        except ValueError:
            pass

    query = query.order_by(AuditLog.created_at.desc())

    if export == 'csv':
        logs = query.all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['操作人', '操作类型', 'IP地址', '结果', '详情', '操作时间'])
        for log in logs:
            writer.writerow([log.operator, log.action_type, log.ip_address,
                             log.result, log.detail, log.created_at.strftime('%Y-%m-%d %H:%M:%S')])
        output.seek(0)
        return Response(
            output.getvalue().encode('utf-8-sig'),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=audit_log.csv'}
        )

    pagination = query.paginate(page=page, per_page=20, error_out=False)
    from utils.audit import ACTION_LABELS
    return render_template('admin/audit_log.html', pagination=pagination,
                           action_labels=ACTION_LABELS,
                           operator=operator, action_type=action_type,
                           start_date=start_date, end_date=end_date)


# ── 通知发布 ──────────────────────────────────────────────────
@admin_bp.route('/notifications')
@login_required
@admin_required
def notifications():
    # 查询最近发布的通知（去重，按标题+时间）
    recent = db.session.query(
        Notification.title, Notification.source, Notification.created_at,
        db.func.count(Notification.id).label('count')
    ).group_by(Notification.title, Notification.created_at).order_by(
        Notification.created_at.desc()
    ).limit(20).all()
    return render_template('admin/notifications.html', recent=recent)


@admin_bp.route('/notifications/publish', methods=['POST'])
@login_required
@admin_required
def publish_notification():
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    target_role = request.form.get('target_role', 'all')

    if not title or not content:
        flash('标题和内容不能为空', 'danger')
        return redirect(url_for('admin.notifications'))

    if target_role == 'all':
        targets = User.query.filter_by(_is_active=True).all()
    elif target_role in ('teacher', 'student'):
        targets = User.query.filter_by(role=target_role, _is_active=True).all()
    else:
        flash('无效的目标角色', 'danger')
        return redirect(url_for('admin.notifications'))

    for user in targets:
        notif = Notification(
            recipient_id=user.id,
            title=title,
            content=content,
            source='manual'
        )
        db.session.add(notif)
    db.session.commit()
    log_action(NOTIFICATION_PUBLISH, 'success', f'发布通知"{title}"给{len(targets)}位用户')
    flash(f'通知已发送给 {len(targets)} 位用户', 'success')
    return redirect(url_for('admin.notifications'))


# ── 选课审核 ──────────────────────────────────────────────────
@admin_bp.route('/applications')
@login_required
@admin_required
def applications():
    status_filter = request.args.get('status', 'all')
    query = CourseApplication.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    apps = query.order_by(CourseApplication.applied_at.desc()).all()
    return render_template('admin/applications.html', apps=apps, status_filter=status_filter)


@admin_bp.route('/applications/review', methods=['POST'])
@login_required
@admin_required
def review_applications():
    app_ids = request.form.getlist('application_ids[]')
    action = request.form.get('action')
    comment = request.form.get('comment', '')

    if not app_ids or action not in ('approve', 'reject'):
        flash('参数错误', 'danger')
        return redirect(url_for('admin.applications'))

    new_status = 'approved' if action == 'approve' else 'rejected'
    action_label = '通过' if action == 'approve' else '拒绝'
    now = datetime.datetime.utcnow()

    for app_id in app_ids:
        app = CourseApplication.query.get(int(app_id))
        if app and app.status == 'pending':
            app.status = new_status
            app.reviewed_at = now
            app.reviewer_id = current_user.id
            app.review_comment = comment
            # 通知学生
            notif = Notification(
                recipient_id=app.student_id,
                title=f'选课申请结果：{action_label}',
                content=f'您申请的课程 [{app.course_id}] 已被{action_label}。审批意见：{comment or "无"}',
                source='application_result'
            )
            db.session.add(notif)

    db.session.commit()
    log_action(APPLICATION_REVIEW, 'success', f'批量{action_label} {len(app_ids)} 条申请')
    flash(f'已{action_label} {len(app_ids)} 条申请', 'success')
    return redirect(url_for('admin.applications'))


# ── 个人中心 ──────────────────────────────────────────────────
@admin_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@admin_required
def profile():
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        display_name = (data.get('display_name') or '').strip()
        if len(display_name) < 2 or len(display_name) > 50:
            return jsonify({'code': 1, 'message': '显示名称长度需在2-50字符之间'})
        current_user.display_name = display_name
        db.session.commit()
        return jsonify({'code': 0, 'message': '保存成功'})

    total_users = User.query.count()
    total_logs = AuditLog.query.count()
    recent_logins = LoginRecord.query.filter_by(user_id=current_user.id).limit(10).all()
    return render_template('admin/profile.html',
                           total_users=total_users,
                           total_logs=total_logs,
                           recent_logins=recent_logins)


@admin_bp.route('/profile/avatar', methods=['POST'])
@login_required
@admin_required
def upload_avatar():
    from utils.avatar import save_avatar, AvatarValidationError
    if 'avatar' not in request.files:
        return jsonify({'code': 1, 'message': '未选择文件'})
    file = request.files['avatar']
    try:
        path = save_avatar(file, current_user.id)
        current_user.avatar_path = path
        db.session.commit()
        return jsonify({'code': 0, 'message': '头像上传成功', 'path': '/' + path})
    except AvatarValidationError as e:
        return jsonify({'code': 1, 'message': str(e)})


# ── 可视化页面 ────────────────────────────────────────────────
@admin_bp.route('/viz/convergence')
@login_required
@admin_required
def viz_convergence():
    return render_template('admin/viz/convergence.html')


@admin_bp.route('/viz/capacity')
@login_required
@admin_required
def viz_capacity():
    return render_template('admin/viz/capacity.html')


@admin_bp.route('/viz/heatmap')
@login_required
@admin_required
def viz_heatmap():
    return render_template('admin/viz/heatmap.html')
