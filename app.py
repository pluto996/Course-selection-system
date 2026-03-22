import os
import threading
import json
import datetime
import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, session
from flask_login import login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from algorithm.genetic_scheduler import GeneticScheduler, XMLBasedScheduler
from models import db, Teacher, Room, Course, SystemConfig
from extensions import login_manager, bcrypt, limiter

app = Flask(__name__)

# 配置
DATA_FOLDER = os.path.join(os.getcwd(), 'data')
if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)

app.config['UPLOAD_FOLDER'] = DATA_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(DATA_FOLDER, 'scheduler.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=2)

# 初始化扩展
db.init_app(app)
login_manager.init_app(app)
bcrypt.init_app(app)
limiter.init_app(app)

# 全局调度器实例
scheduler = GeneticScheduler()

# 辅助常量
DAYS = ['0100000', '0010000', '0001000', '0000100', '0000010']
DAY_NAMES_MAP = {
    '0100000': '星期一', '0010000': '星期二', '0001000': '星期三',
    '0000100': '星期四', '0000010': '星期五'
}
SECTIONS = [{'id': i, 'label': f'第{i}节'} for i in range(1, 9)]


# ── Session 超时检测 ──────────────────────────────────────────
@app.before_request
def check_session_timeout():
    if current_user.is_authenticated:
        last_active = session.get('last_active')
        if last_active:
            elapsed = (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(last_active)).total_seconds()
            if elapsed > 7200:  # 120 分钟
                logout_user()
                session.clear()
                return redirect(url_for('auth.login'))
        session['last_active'] = datetime.datetime.utcnow().isoformat()


# ── 注册 Blueprint ────────────────────────────────────────────
from blueprints.auth import auth_bp
from blueprints.admin import admin_bp
from blueprints.teacher import teacher_bp
from blueprints.student import student_bp
from blueprints.api import api_bp

app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(teacher_bp, url_prefix='/teacher')
app.register_blueprint(student_bp, url_prefix='/student')
app.register_blueprint(api_bp, url_prefix='/api')


# ── 错误处理器 ────────────────────────────────────────────────
@app.errorhandler(401)
def unauthorized(e):
    return redirect(url_for('auth.login', next=request.url))


@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403


@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404


@app.errorhandler(429)
def too_many_requests(e):
    return render_template('auth/login.html', lock_message='登录尝试过于频繁，请 15 分钟后重试'), 429


@app.errorhandler(500)
def internal_error(e):
    db.session.rollback()
    return render_template('errors/500.html'), 500


# ── 数据库初始化 ──────────────────────────────────────────────
def init_db_data():
    """应用启动时从数据库加载数据到调度器内存，并恢复上次排课结果"""
    with app.app_context():
        db.create_all()
        _create_default_admin()

        if Course.query.first():
            print("从数据库加载排课数据...")
            data = {'slots_per_day': 288, 'classrooms': [], 'courses': []}
            config = SystemConfig.query.get('slotsPerDay')
            if config:
                data['slots_per_day'] = int(config.value)
            for r in Room.query.all():
                data['classrooms'].append({'id': r.id, 'capacity': r.capacity})
            for c in Course.query.all():
                data['courses'].append({
                    'id': c.id,
                    'limit': c.class_limit,
                    'instructors': [t.name for t in c.instructors],
                    'possible_times': json.loads(c.possible_times_json) if c.possible_times_json else [],
                    'possible_rooms': json.loads(c.possible_rooms_json) if c.possible_rooms_json else []
                })
            scheduler.load_from_memory(data)

            # 恢复上次排课结果
            saved_result = SystemConfig.query.get('schedule_result')
            if saved_result:
                scheduler.result = json.loads(saved_result.value)
                scheduler.progress['status'] = 'COMPLETED'
                print(f"已恢复排课结果，共 {len(scheduler.result)} 条记录。")

            # 恢复收敛历史
            saved_conv = SystemConfig.query.get('convergence_data')
            if saved_conv:
                conv = json.loads(saved_conv.value)
                gens = conv.get('generations', [])
                scheduler.progress['history'] = [
                    {'gen': g, 'hard': conv['conflicts'][i],
                     'f2': conv['f2'][i] if 'f2' in conv else 0,
                     'f3': conv['f3'][i] if 'f3' in conv else 0}
                    for i, g in enumerate(gens)
                ]
            print("数据加载完成。")
        else:
            print("数据库中暂无排课数据。")


def _create_default_admin():
    """若 User 表为空则创建默认管理员账号"""
    from models import User
    if User.query.first() is None:
        admin = User(username='admin', role='admin', display_name='系统管理员')
        admin.set_password('Admin123')
        db.session.add(admin)
        db.session.commit()
        print("已创建默认管理员账号：admin / Admin123")


init_db_data()


# ── 原有路由（保留，加权限守卫）────────────────────────────────
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif current_user.role == 'teacher':
            return redirect(url_for('teacher.dashboard'))
        else:
            return redirect(url_for('student.schedule'))
    return redirect(url_for('auth.login'))


@app.route('/schedule')
@login_required
def schedule():
    data_to_show = scheduler.get_result()
    teachers = sorted(list(set(item['teacher'] for item in data_to_show)))
    rooms = sorted(list(set(item['room'] for item in data_to_show)))
    return render_template('schedule.html',
                           schedule=data_to_show,
                           days=DAYS,
                           day_names=DAY_NAMES_MAP,
                           sections=SECTIONS,
                           teachers=teachers,
                           rooms=rooms,
                           page='schedule')


@app.route('/data')
@login_required
def data_management():
    data = scheduler.get_data()
    return render_template('data.html', tasks=data['tasks'], page='data')


@app.route('/generate')
@login_required
def generate_page():
    return render_template('generate.html', page='generate')


# ── 原有 API（保留，加权限守卫）──────────────────────────────
@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    from decorators import role_required
    from utils.audit import log_action, XML_IMPORT
    if current_user.role != 'admin':
        return jsonify({'error': '权限不足'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and file.filename.endswith('.xml'):
        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)
        try:
            parsed_data = XMLBasedScheduler.parse_xml_to_dict(save_path)
            db.session.query(Course).delete()
            db.session.query(Room).delete()
            db.session.query(Teacher).delete()
            db.session.execute(db.text("DELETE FROM course_teacher"))
            db.session.commit()

            conf = SystemConfig.query.get('slotsPerDay')
            if not conf:
                conf = SystemConfig(key='slotsPerDay')
            conf.value = str(parsed_data['slots_per_day'])
            db.session.add(conf)

            for r in parsed_data['classrooms']:
                db.session.add(Room(id=r['id'], capacity=r['capacity']))

            teacher_cache = {}
            for c in parsed_data['courses']:
                course_obj = Course(
                    id=c['id'],
                    class_limit=c['limit'],
                    possible_times_json=json.dumps(c['possible_times']),
                    possible_rooms_json=json.dumps(c['possible_rooms'])
                )
                for t_name in c['instructors']:
                    if t_name not in teacher_cache:
                        t_obj = Teacher.query.filter_by(name=t_name).first()
                        if not t_obj:
                            t_obj = Teacher(name=t_name)
                            db.session.add(t_obj)
                        teacher_cache[t_name] = t_obj
                    course_obj.instructors.append(teacher_cache[t_name])
                db.session.add(course_obj)

            db.session.commit()
            scheduler.load_from_memory(parsed_data)
            log_action(XML_IMPORT, 'success', f'导入文件：{filename}')
            return jsonify({'message': '文件上传并更新数据库成功', 'filename': filename}), 200
        except Exception as e:
            db.session.rollback()
            log_action(XML_IMPORT, 'failure', str(e))
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': '文件类型无效，请上传 .xml 文件'}), 400


@app.route('/api/start_optimization', methods=['POST'])
@login_required
def start_optimization():
    from utils.audit import log_action, SCHEDULE_GENERATE
    if current_user.role != 'admin':
        return jsonify({'error': '权限不足'}), 403

    if scheduler.progress['status'] == 'RUNNING':
        return jsonify({'error': '排课算法正在运行中'}), 400

    params = request.get_json() or {}

    def run_and_notify():
        scheduler.run_optimization(params)
        with app.app_context():
            # 排课完成后通知全体教师
            from models import User, Notification
            teachers = User.query.filter_by(role='teacher', is_active=True).all()
            for t in teachers:
                notif = Notification(
                    recipient_id=t.id,
                    title='排课完成通知',
                    content='本轮排课已完成，请登录查看最新课表。',
                    source='schedule_done'
                )
                db.session.add(notif)
            # 保存排课结果
            result_conf = SystemConfig.query.get('schedule_result')
            if not result_conf:
                result_conf = SystemConfig(key='schedule_result')
            result_conf.value = json.dumps(scheduler.result)
            db.session.add(result_conf)

            # 保存收敛数据（含多目标）
            history = scheduler.progress.get('history', [])
            if history:
                conv_data = json.dumps({
                    'generations': [h['gen']  for h in history],
                    'conflicts':   [h['hard'] for h in history],
                    'f2':          [h.get('f2', 0) for h in history],
                    'f3':          [h.get('f3', 0) for h in history],
                    'pareto_history': scheduler.progress.get('pareto_history', [])
                })
                conf = SystemConfig.query.get('convergence_data')
                if not conf:
                    conf = SystemConfig(key='convergence_data')
                conf.value = conv_data
                db.session.add(conf)
            db.session.commit()
            log_action(SCHEDULE_GENERATE, 'success', f'参数：{json.dumps(params)}')

    thread = threading.Thread(target=run_and_notify)
    thread.daemon = True
    thread.start()
    return jsonify({'status': 'started'})


@app.route('/api/progress', methods=['GET'])
@login_required
def get_progress():
    return jsonify(scheduler.get_progress())


@app.route('/api/stop', methods=['POST'])
@login_required
def stop_optimization():
    if current_user.role != 'admin':
        return jsonify({'error': '权限不足'}), 403
    scheduler.stop()
    return jsonify({'status': 'stopped'})


@app.route('/api/export_schedule')
@login_required
def export_schedule():
    results = scheduler.get_result()
    if not results:
        return "暂无排课结果", 404

    export_data = []
    for item in results:
        export_data.append({
            '星期': DAY_NAMES_MAP.get(item['day'], item['day']),
            '节次': f"第{item['section']}节",
            '课程': item['course_name'],
            '教师': item['teacher'],
            '教室': item['room']
        })

    df = pd.DataFrame(export_data)
    output_file = os.path.join(app.config['UPLOAD_FOLDER'], 'schedule_export.xlsx')
    df.to_excel(output_file, index=False)
    return send_file(output_file, as_attachment=True, download_name='course_schedule.xlsx')


if __name__ == '__main__':
    app.run(debug=True, port=5000)
