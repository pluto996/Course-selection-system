import json
import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, g
from flask_login import current_user, login_required
from models import db, User, Notification, CourseApplication, ClassRecord, Instructor, Room, SystemConfig

api_bp = Blueprint('api', __name__)


# ── Token 认证装饰器 ──────────────────────────────────────────
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'code': 1, 'message': '缺少认证 Token'}), 401
        token = auth_header[7:]
        user = User.query.filter_by(api_token=token).first()
        if not user or not user.api_token_expires or user.api_token_expires < datetime.datetime.utcnow():
            return jsonify({'code': 1, 'message': 'Token 无效或已过期'}), 401
        g.token_user = user
        return f(*args, **kwargs)
    return decorated


def role_token_required(*roles):
    def decorator(f):
        @wraps(f)
        @token_required
        def decorated(*args, **kwargs):
            if g.token_user.role not in roles:
                return jsonify({'code': 1, 'message': '权限不足'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── 认证 API ──────────────────────────────────────────────────
@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')

    if not username:
        return jsonify({'code': 1, 'error': '缺少参数 username'}), 400
    if not password:
        return jsonify({'code': 1, 'error': '缺少参数 password'}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password) or not user.is_active:
        return jsonify({'code': 1, 'message': '用户名或密码错误'}), 401

    user.generate_api_token()
    db.session.commit()
    return jsonify({
        'code': 0,
        'data': {'token': user.api_token, 'role': user.role, 'username': user.username},
        'message': '登录成功'
    })


@api_bp.route('/auth/logout', methods=['POST'])
@token_required
def api_logout():
    g.token_user.revoke_api_token()
    db.session.commit()
    return jsonify({'code': 0, 'message': '已登出'})


# ── 通知 API ──────────────────────────────────────────────────
@api_bp.route('/notifications', methods=['GET'])
@token_required
def api_notifications():
    notifs = Notification.query.filter_by(recipient_id=g.token_user.id).order_by(
        Notification.created_at.desc()
    ).limit(50).all()
    return jsonify({
        'code': 0,
        'data': [{
            'id': n.id, 'title': n.title, 'content': n.content,
            'is_read': n.is_read, 'created_at': n.created_at.isoformat()
        } for n in notifs],
        'message': ''
    })


@api_bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@token_required
def api_mark_read(notif_id):
    notif = Notification.query.filter_by(id=notif_id, recipient_id=g.token_user.id).first()
    if not notif:
        return jsonify({'code': 1, 'message': '通知不存在'}), 404
    notif.is_read = True
    db.session.commit()
    return jsonify({'code': 0, 'message': '已标记为已读'})


@api_bp.route('/notifications/<int:notif_id>', methods=['DELETE'])
@token_required
def api_delete_notification(notif_id):
    notif = Notification.query.filter_by(id=notif_id, recipient_id=g.token_user.id).first()
    if not notif:
        return jsonify({'code': 1, 'message': '通知不存在'}), 404
    db.session.delete(notif)
    db.session.commit()
    return jsonify({'code': 0, 'message': '已删除'})


# ── 选课申请 API ──────────────────────────────────────────────
@api_bp.route('/applications', methods=['GET'])
@token_required
def api_get_applications():
    if g.token_user.role not in ('student', 'admin'):
        return jsonify({'code': 1, 'message': '权限不足'}), 403
    apps = CourseApplication.query.filter_by(student_id=g.token_user.id).all()
    grouped = {'pending': [], 'approved': [], 'rejected': []}
    for app in apps:
        grouped[app.status].append({
            'id': app.id, 'course_id': app.course_id,
            'status': app.status, 'applied_at': app.applied_at.isoformat(),
            'review_comment': app.review_comment
        })
    return jsonify({'code': 0, 'data': grouped, 'message': ''})


@api_bp.route('/applications', methods=['POST'])
@token_required
def api_create_application():
    if g.token_user.role != 'student':
        return jsonify({'code': 1, 'message': '仅学生可申请选课'}), 403
    data = request.get_json() or {}
    course_id = data.get('course_id')
    if not course_id:
        return jsonify({'code': 1, 'error': '缺少参数 course_id'}), 400

    existing = CourseApplication.query.filter_by(
        student_id=g.token_user.id, course_id=course_id
    ).filter(CourseApplication.status.in_(['pending', 'approved'])).first()
    if existing:
        return jsonify({'code': 1, 'message': '您已申请过该课程'}), 400

    app = CourseApplication(student_id=g.token_user.id, course_id=course_id, status='pending')
    db.session.add(app)
    db.session.commit()
    return jsonify({'code': 0, 'message': '申请已提交'})


@api_bp.route('/applications/<int:app_id>', methods=['GET'])
@token_required
def api_get_application(app_id):
    app = CourseApplication.query.get_or_404(app_id)
    if app.student_id != g.token_user.id and g.token_user.role != 'admin':
        return jsonify({'code': 1, 'message': '权限不足'}), 403
    return jsonify({'code': 0, 'data': {
        'id': app.id, 'course_id': app.course_id, 'status': app.status,
        'applied_at': app.applied_at.isoformat(),
        'reviewed_at': app.reviewed_at.isoformat() if app.reviewed_at else None,
        'review_comment': app.review_comment
    }, 'message': ''})


# ── 可视化数据 API ────────────────────────────────────────────
@api_bp.route('/viz/convergence', methods=['GET'])
@login_required
def api_viz_convergence():
    config = SystemConfig.query.get('convergence_data')
    if not config or not config.value:
        return jsonify({'generations': [], 'conflicts': []})
    try:
        data = json.loads(config.value)
        return jsonify(data)
    except Exception:
        return jsonify({'generations': [], 'conflicts': []})


@api_bp.route('/viz/capacity', methods=['GET'])
@login_required
def api_viz_capacity():
    from app import scheduler
    rooms = Room.query.all()
    # 从调度器结果统计每个教室的实际使用人数
    result = scheduler.get_result()
    room_usage = {}
    for item in result:
        rid = item['room']
        room_usage[rid] = room_usage.get(rid, 0) + 1

    out = []
    for room in rooms:
        actual = room_usage.get(room.room_id, 0)
        out.append({
            'room_id': room.room_id,
            'capacity': room.capacity,
            'actual': actual,
            'over_capacity': actual > room.capacity
        })
    return jsonify(out)


@api_bp.route('/viz/heatmap', methods=['GET'])
@login_required
def api_viz_heatmap():
    from app import scheduler
    day_keys = ['0100000', '0010000', '0001000', '0000100', '0000010']
    matrix = [[0] * 8 for _ in range(5)]
    for item in scheduler.get_result():
        day = item['day']
        section = item['section']
        if day in day_keys and 1 <= section <= 8:
            matrix[day_keys.index(day)][section - 1] += 1
    return jsonify(matrix)


@api_bp.route('/viz/teacher/<teacher_id>/radar', methods=['GET'])
@login_required
def api_teacher_radar(teacher_id):
    from app import scheduler
    day_keys = ['0100000', '0010000', '0001000', '0000100', '0000010']
    values = [0] * 5
    for item in scheduler.get_result():
        if teacher_id in item['teacher']:
            day = item['day']
            if day in day_keys:
                values[day_keys.index(day)] += 1
    return jsonify({'code': 0, 'data': {'labels': ['周一', '周二', '周三', '周四', '周五'], 'values': values}})


@api_bp.route('/viz/teacher/<teacher_id>/wordcloud', methods=['GET'])
@login_required
def api_teacher_wordcloud(teacher_id):
    instructor = Instructor.query.get_or_404(teacher_id)
    classes = ClassRecord.query.filter_by(instructor_id=instructor.instructor_id).all()
    word_freq = {}
    for c in classes:
        reviews = CourseReview.query.filter_by(course_id=c.class_id).all()
        for r in reviews:
            for word in (r.content or '').split():
                if len(word) >= 2:
                    word_freq[word] = word_freq.get(word, 0) + 1
    data = [{'text': k, 'weight': v} for k, v in sorted(word_freq.items(), key=lambda x: -x[1])[:50]]
    return jsonify({'code': 0, 'data': data})


@api_bp.route('/viz/student/<int:student_id>/workload', methods=['GET'])
@login_required
def api_student_workload(student_id):
    from app import scheduler
    apps = CourseApplication.query.filter_by(student_id=student_id, status='approved').all()
    approved_ids = {a.course_id for a in apps}
    day_keys = ['0100000', '0010000', '0001000', '0000100', '0000010']
    day_labels = ['周一', '周二', '周三', '周四', '周五']
    hours = [0] * 5
    for item in scheduler.get_result():
        if item['course_name'] in approved_ids and item['day'] in day_keys:
            hours[day_keys.index(item['day'])] += 1
    return jsonify({'code': 0, 'data': {'days': day_labels, 'hours': hours}})
