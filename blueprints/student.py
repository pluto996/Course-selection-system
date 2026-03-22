from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from models import db, ClassRecord, Instructor, Room, Notification, CourseApplication, AuditLog
from decorators import student_required

student_bp = Blueprint('student', __name__)

DAY_MAP = {'0100000': '周一', '0010000': '周二', '0001000': '周三', '0000100': '周四', '0000010': '周五'}
DAY_ORDER = ['周一', '周二', '周三', '周四', '周五']


@student_bp.context_processor
def inject_unread():
    return {'unread_count': Notification.unread_count(current_user.id) if current_user.is_authenticated else 0}


# ── 公开课表 ──────────────────────────────────────────────────
@student_bp.route('/schedule')
@login_required
@student_required
def schedule():
    from app import scheduler, DAY_NAMES_MAP
    teacher_filter = request.args.get('teacher_id', '')
    room_filter = request.args.get('room_id', '')
    day_filter = request.args.get('day', '')

    teachers = Instructor.query.order_by(Instructor.instructor_id).all()
    rooms = Room.query.order_by(Room.room_id).all()

    # 从调度器结果构建课表（day 是 '0100000' 格式，section 是 int）
    result = scheduler.get_result()
    schedule_data = {}  # {day_label: {section: [entry]}}

    for item in result:
        day = item['day']
        section = item['section']
        day_label = DAY_MAP.get(day, day)

        if day_filter and day != day_filter:
            continue
        if room_filter and item['room'] != room_filter:
            continue
        if teacher_filter:
            if teacher_filter not in item['teacher']:
                continue

        if day_label not in schedule_data:
            schedule_data[day_label] = {}
        if section not in schedule_data[day_label]:
            schedule_data[day_label][section] = []

        schedule_data[day_label][section].append({
            'course_id': item['course_name'],
            'course_name': item['course_name'],
            'teacher': item['teacher'],
            'room': item['room'],
            'class_size': '-'
        })

    return render_template('student/schedule.html',
                           schedule_data=schedule_data,
                           days_order=DAY_ORDER,
                           sections=range(1, 9),
                           teachers=teachers,
                           rooms=rooms,
                           teacher_filter=teacher_filter,
                           room_filter=room_filter,
                           day_filter=day_filter)


# ── 选课申请 ──────────────────────────────────────────────────
@student_bp.route('/apply', methods=['GET', 'POST'])
@login_required
@student_required
def apply():
    course_id = request.args.get('course_id', '')
    courses = ClassRecord.query.all()
    selected_course = ClassRecord.query.get(course_id) if course_id else None

    if request.method == 'POST':
        cid = request.form.get('course_id', '').strip()
        if not cid:
            return jsonify({'code': 1, 'message': '请选择课程'})

        # 检查重复申请
        existing = CourseApplication.query.filter_by(
            student_id=current_user.id, course_id=cid
        ).filter(CourseApplication.status.in_(['pending', 'approved'])).first()
        if existing:
            return jsonify({'code': 1, 'message': '您已申请过该课程'})

        app = CourseApplication(
            student_id=current_user.id,
            course_id=cid,
            status='pending'
        )
        db.session.add(app)
        db.session.commit()
        return jsonify({'code': 0, 'message': '申请已提交，等待审核'})

    return render_template('student/apply.html',
                           courses=courses,
                           selected_course=selected_course,
                           course_id=course_id)


# ── 看板 ──────────────────────────────────────────────────────
@student_bp.route('/kanban')
@login_required
@student_required
def kanban():
    apps = CourseApplication.query.filter_by(student_id=current_user.id).all()
    grouped = {'pending': [], 'approved': [], 'rejected': []}
    for app in apps:
        grouped[app.status].append(app)
    return render_template('student/kanban.html', grouped=grouped)


# ── 个人课表（CalendarView）────────────────────────────────────
@student_bp.route('/calendar')
@login_required
@student_required
def calendar():
    from app import scheduler
    approved_apps = CourseApplication.query.filter_by(
        student_id=current_user.id, status='approved'
    ).all()
    approved_course_ids = {app.course_id for app in approved_apps}

    result = scheduler.get_result()
    calendar_data = {}
    workload = {'周一': 0, '周二': 0, '周三': 0, '周四': 0, '周五': 0}

    for item in result:
        if item['course_name'] not in approved_course_ids:
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
            'teacher': item['teacher'],
            'room': item['room']
        })
        if day_label in workload:
            workload[day_label] += 1

    return render_template('student/schedule_calendar.html',
                           calendar_data=calendar_data,
                           days_order=DAY_ORDER,
                           sections=range(1, 9),
                           workload=workload)


# ── 通知中心 ──────────────────────────────────────────────────
@student_bp.route('/notifications')
@login_required
@student_required
def notifications_list():
    page = request.args.get('page', 1, type=int)
    pagination = Notification.query.filter_by(
        recipient_id=current_user.id
    ).order_by(Notification.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('student/notifications.html', pagination=pagination)


@student_bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
@student_required
def mark_read(notif_id):
    notif = Notification.query.filter_by(id=notif_id, recipient_id=current_user.id).first_or_404()
    notif.is_read = True
    db.session.commit()
    return jsonify({'code': 0, 'message': '已标记为已读'})


@student_bp.route('/notifications/read-all', methods=['POST'])
@login_required
@student_required
def mark_all_read():
    Notification.query.filter_by(recipient_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'code': 0, 'message': '全部已读'})


@student_bp.route('/notifications/<int:notif_id>', methods=['DELETE'])
@login_required
@student_required
def delete_notification(notif_id):
    notif = Notification.query.filter_by(id=notif_id, recipient_id=current_user.id).first_or_404()
    db.session.delete(notif)
    db.session.commit()
    return jsonify({'code': 0, 'message': '已删除'})


# ── 个人中心 ──────────────────────────────────────────────────
@student_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@student_required
def profile():
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        display_name = (data.get('display_name') or '').strip()
        if len(display_name) < 2 or len(display_name) > 50:
            return jsonify({'code': 1, 'message': '显示名称长度需在2-50字符之间'})
        current_user.display_name = display_name
        db.session.commit()
        return jsonify({'code': 0, 'message': '保存成功'})

    approved_count = CourseApplication.query.filter_by(
        student_id=current_user.id, status='approved'
    ).count()
    pending_count = CourseApplication.query.filter_by(
        student_id=current_user.id, status='pending'
    ).count()
    recent_logins = AuditLog.query.filter_by(
        user_id=current_user.id, action_type='LOGIN'
    ).order_by(AuditLog.created_at.desc()).limit(10).all()

    return render_template('student/profile.html',
                           approved_count=approved_count,
                           pending_count=pending_count,
                           recent_logins=recent_logins)


@student_bp.route('/profile/avatar', methods=['POST'])
@login_required
@student_required
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
