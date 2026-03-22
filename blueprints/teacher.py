import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from models import db, Teacher, Course, Notification, LoginRecord
from decorators import teacher_required

teacher_bp = Blueprint('teacher', __name__)

DAY_MAP = {'0100000': '周一', '0010000': '周二', '0001000': '周三', '0000100': '周四', '0000010': '周五'}
DAY_ORDER = {'0100000': 1, '0010000': 2, '0001000': 3, '0000100': 4, '0000010': 5}


@teacher_bp.context_processor
def inject_unread():
    return {'unread_count': Notification.unread_count(current_user.id) if current_user.is_authenticated else 0}


def _get_teacher_record():
    """获取当前用户关联的 Teacher 记录"""
    if current_user.teacher_id:
        return Teacher.query.get(current_user.teacher_id)
    return Teacher.query.filter_by(name=current_user.display_name or current_user.username).first()


# ── 仪表盘 ────────────────────────────────────────────────────
@teacher_bp.route('/dashboard')
@login_required
@teacher_required
def dashboard():
    from app import scheduler
    teacher = _get_teacher_record()
    schedule_count = 0
    if teacher:
        result = scheduler.get_result()
        schedule_count = sum(1 for item in result if teacher.name in item['teacher'])
    unread = Notification.unread_count(current_user.id)
    recent_notifs = Notification.query.filter_by(
        recipient_id=current_user.id
    ).order_by(Notification.created_at.desc()).limit(5).all()
    return render_template('teacher/dashboard.html',
                           teacher=teacher,
                           schedule_count=schedule_count,
                           unread=unread,
                           recent_notifs=recent_notifs)


# ── 课表（CalendarView）────────────────────────────────────────
@teacher_bp.route('/calendar')
@login_required
@teacher_required
def calendar():
    from app import scheduler
    teacher = _get_teacher_record()
    calendar_data = {}

    if teacher:
        result = scheduler.get_result()
        for item in result:
            # match by teacher name substring
            if teacher.name not in item['teacher']:
                continue
            day = item['day']
            section = item['section']
            day_label = DAY_MAP.get(day, day)
            if day_label not in calendar_data:
                calendar_data[day_label] = {}
            if section not in calendar_data[day_label]:
                calendar_data[day_label][section] = []
            calendar_data[day_label][section].append({
                'course_id': item['course_name'],
                'course_name': item['course_name'],
                'class_size': '-',
                'room': item['room']
            })

    days_order = ['周一', '周二', '周三', '周四', '周五']
    return render_template('teacher/calendar.html',
                           teacher=teacher,
                           calendar_data=calendar_data,
                           days_order=days_order,
                           sections=range(1, 9))


# ── 个人中心 ──────────────────────────────────────────────────
@teacher_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@teacher_required
def profile():
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        display_name = (data.get('display_name') or '').strip()
        if len(display_name) < 2 or len(display_name) > 50:
            return jsonify({'code': 1, 'message': '显示名称长度需在2-50字符之间'})
        current_user.display_name = display_name
        db.session.commit()
        return jsonify({'code': 0, 'message': '保存成功'})

    teacher = _get_teacher_record()
    total_courses = len(teacher.courses) if teacher else 0
    recent_logins = LoginRecord.query.filter_by(user_id=current_user.id).limit(10).all()
    return render_template('teacher/profile.html',
                           teacher=teacher,
                           total_courses=total_courses,
                           recent_logins=recent_logins)


@teacher_bp.route('/profile/avatar', methods=['POST'])
@login_required
@teacher_required
def upload_avatar():
    from utils.avatar import save_avatar, AvatarValidationError
    if 'avatar' not in request.files:
        return jsonify({'code': 1, 'message': '未选择文件'})
    file = request.files['avatar']
    try:
        path = save_avatar(file, current_user.id)
        current_user.avatar_path = path
        db.session.commit()
        return jsonify({'code': 0, 'message': '头像上传成功', 'path': '/static/' + path})
    except Exception as e:
        return jsonify({'code': 1, 'message': str(e)})


# ── 通知中心 ──────────────────────────────────────────────────
@teacher_bp.route('/notifications')
@login_required
@teacher_required
def notifications_list():
    page = request.args.get('page', 1, type=int)
    pagination = Notification.query.filter_by(
        recipient_id=current_user.id
    ).order_by(Notification.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('teacher/notifications.html', pagination=pagination)


@teacher_bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
@teacher_required
def mark_read(notif_id):
    notif = Notification.query.filter_by(id=notif_id, recipient_id=current_user.id).first_or_404()
    notif.is_read = True
    db.session.commit()
    return jsonify({'code': 0, 'message': '已标记为已读'})


@teacher_bp.route('/notifications/read-all', methods=['POST'])
@login_required
@teacher_required
def mark_all_read():
    Notification.query.filter_by(recipient_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'code': 0, 'message': '全部已读'})


@teacher_bp.route('/notifications/<int:notif_id>', methods=['DELETE'])
@login_required
@teacher_required
def delete_notification(notif_id):
    notif = Notification.query.filter_by(id=notif_id, recipient_id=current_user.id).first_or_404()
    db.session.delete(notif)
    db.session.commit()
    return jsonify({'code': 0, 'message': '已删除'})


