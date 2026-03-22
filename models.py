import json
import secrets
import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# ── 关联表：课程与教师的多对多关系 ────────────────────────────
course_teacher = db.Table(
    'course_teacher',
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True),
    db.Column('teacher_id', db.Integer, db.ForeignKey('teacher.id'), primary_key=True)
)


# ══════════════════════════════════════════════════════════════
#  原有模型（保留）
# ══════════════════════════════════════════════════════════════

class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f'<Teacher {self.name}>'


class Room(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    capacity = db.Column(db.Integer, default=0)


class Course(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    class_limit = db.Column(db.Integer, default=0)
    possible_times_json = db.Column(db.Text, nullable=True)
    possible_rooms_json = db.Column(db.Text, nullable=True)
    instructors = db.relationship(
        'Teacher', secondary=course_teacher, lazy='subquery',
        backref=db.backref('courses', lazy=True)
    )


class SystemConfig(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.Text)


# ══════════════════════════════════════════════════════════════
#  新增模型
# ══════════════════════════════════════════════════════════════

class User(db.Model, UserMixin):
    """系统用户（管理员 / 教师 / 学生）"""
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(100), nullable=False, default='')
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')  # admin/teacher/student
    _is_active = db.Column('is_active', db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False)
    avatar_path = db.Column(db.String(200), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=True)
    api_token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    api_token_expires = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # 关系
    teacher = db.relationship('Teacher', backref='user_account', foreign_keys=[teacher_id])
    login_records = db.relationship(
        'LoginRecord', backref='user', lazy='dynamic',
        order_by='LoginRecord.logged_in_at.desc()'
    )
    notifications = db.relationship(
        'Notification', backref='recipient', lazy='dynamic',
        foreign_keys='Notification.recipient_id'
    )

    # ── UserMixin 要求 ──────────────────────────────────────
    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self._is_active

    @is_active.setter
    def is_active(self, value):
        self._is_active = value

    # ── 密码处理 ────────────────────────────────────────────
    def set_password(self, password):
        from extensions import bcrypt
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        from extensions import bcrypt
        return bcrypt.check_password_hash(self.password_hash, password)

    @staticmethod
    def validate_password_policy(password: str) -> bool:
        """密码策略：长度≥8，含字母和数字"""
        if len(password) < 8:
            return False
        has_alpha = any(c.isalpha() for c in password)
        has_digit = any(c.isdigit() for c in password)
        return has_alpha and has_digit

    # ── API Token ───────────────────────────────────────────
    def generate_api_token(self):
        self.api_token = secrets.token_urlsafe(32)
        self.api_token_expires = datetime.datetime.utcnow() + datetime.timedelta(hours=24)

    def revoke_api_token(self):
        self.api_token = None
        self.api_token_expires = None

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class LoginRecord(db.Model):
    """登录记录"""
    __tablename__ = 'login_record'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ip_address = db.Column(db.String(50))
    logged_in_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)
    success = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<LoginRecord user={self.user_id} success={self.success}>'


class AuditLog(db.Model):
    """审计日志"""
    __tablename__ = 'audit_log'

    id = db.Column(db.Integer, primary_key=True)
    operator = db.Column(db.String(80), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)
    ip_address = db.Column(db.String(50))
    result = db.Column(db.String(20), default='success')  # success / failure
    detail = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)

    @classmethod
    def archive_old_logs(cls):
        """将 90 天前的日志归档（仅在总记录数超过 10000 时触发）"""
        total = cls.query.count()
        if total <= 10000:
            return 0
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=90)
        old_logs = cls.query.filter(cls.created_at < cutoff).all()
        count = 0
        for log in old_logs:
            archived = ArchivedAuditLog(
                operator=log.operator,
                action_type=log.action_type,
                ip_address=log.ip_address,
                result=log.result,
                detail=log.detail,
                created_at=log.created_at,
                archived_at=datetime.datetime.utcnow()
            )
            db.session.add(archived)
            db.session.delete(log)
            count += 1
        db.session.commit()
        return count

    def __repr__(self):
        return f'<AuditLog {self.action_type} by {self.operator}>'


class ArchivedAuditLog(db.Model):
    """归档审计日志"""
    __tablename__ = 'archived_audit_log'

    id = db.Column(db.Integer, primary_key=True)
    operator = db.Column(db.String(80), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)
    ip_address = db.Column(db.String(50))
    result = db.Column(db.String(20), default='success')
    detail = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime)
    archived_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class Notification(db.Model):
    """通知"""
    __tablename__ = 'notification'

    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)
    source = db.Column(db.String(50), default='manual')  # manual / schedule_done / application_result

    @classmethod
    def unread_count(cls, user_id: int) -> int:
        return cls.query.filter_by(recipient_id=user_id, is_read=False).count()

    def __repr__(self):
        return f'<Notification {self.title} → user {self.recipient_id}>'


class CourseApplication(db.Model):
    """学生选课申请"""
    __tablename__ = 'course_application'
    __table_args__ = (
        db.UniqueConstraint('student_id', 'course_id', name='uq_student_course'),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.String(50), db.ForeignKey('course.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending / approved / rejected
    applied_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    review_comment = db.Column(db.Text, default='')

    # 关系
    student = db.relationship('User', foreign_keys=[student_id], backref='applications')
    course = db.relationship('Course', backref='applications')
    reviewer = db.relationship('User', foreign_keys=[reviewer_id])

    def __repr__(self):
        return f'<CourseApplication student={self.student_id} course={self.course_id} status={self.status}>'


class CourseReview(db.Model):
    """课程评价"""
    __tablename__ = 'course_review'
    __table_args__ = (
        db.UniqueConstraint('student_id', 'course_id', name='uq_review_student_course'),
        db.CheckConstraint('score >= 1 AND score <= 5', name='ck_score_range'),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.String(50), db.ForeignKey('course.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)  # 1-5
    content = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # 关系
    student = db.relationship('User', foreign_keys=[student_id], backref='reviews')
    course = db.relationship('Course', backref='reviews')

    def __repr__(self):
        return f'<CourseReview student={self.student_id} course={self.course_id} score={self.score}>'
