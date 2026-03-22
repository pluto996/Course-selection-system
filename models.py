import json
import secrets
import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


# ══════════════════════════════════════════════════════════════
#  排课核心模型（7 表结构，对应 pythonProject1/text.py）
# ══════════════════════════════════════════════════════════════

class Room(db.Model):
    """教室资源（含可用性掩码）"""
    __tablename__ = 'rooms'
    room_id = db.Column(db.String(50), primary_key=True)
    capacity = db.Column(db.Integer, default=0)
    loc_x = db.Column(db.Float, default=0.0)
    loc_y = db.Column(db.Float, default=0.0)
    availability_pattern = db.Column(db.Text, nullable=True)   # <sharing><pattern> 掩码字符串
    availability_unit = db.Column(db.Integer, nullable=True)   # pattern unit 属性

    def __repr__(self):
        return f'<Room {self.room_id} cap={self.capacity}>'


class Instructor(db.Model):
    """教师/讲师"""
    __tablename__ = 'instructors'
    instructor_id = db.Column(db.String(50), primary_key=True)

    def __repr__(self):
        return f'<Instructor {self.instructor_id}>'


class ClassRecord(db.Model):
    """教学班（合并了 Offering 和 Subpart ID）"""
    __tablename__ = 'classes'
    class_id = db.Column(db.String(50), primary_key=True)
    subpart_id = db.Column(db.String(50), nullable=True)
    offering_id = db.Column(db.String(50), nullable=True)
    class_limit = db.Column(db.Integer, default=0)
    instructor_id = db.Column(db.String(50), db.ForeignKey('instructors.instructor_id'), nullable=True)

    instructor = db.relationship('Instructor', backref='classes')

    def __repr__(self):
        return f'<Class {self.class_id} limit={self.class_limit}>'


class StudentRecord(db.Model):
    """学生主表"""
    __tablename__ = 'students'
    student_id = db.Column(db.String(50), primary_key=True)

    def __repr__(self):
        return f'<Student {self.student_id}>'


class StudentRequest(db.Model):
    """学生选课需求（CLASS / OFFERING 两种类型合并）"""
    __tablename__ = 'student_requests'
    student_id = db.Column(db.String(50), db.ForeignKey('students.student_id'), primary_key=True)
    target_id = db.Column(db.String(50), primary_key=True)
    request_type = db.Column(db.String(10), primary_key=True)  # 'CLASS' or 'OFFERING'

    student = db.relationship('StudentRecord', backref='requests')

    def __repr__(self):
        return f'<StudentRequest {self.student_id} -> {self.target_id} ({self.request_type})>'


class Preference(db.Model):
    """软偏好（教师/教室偏好评分）"""
    __tablename__ = 'preferences'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    class_id = db.Column(db.String(50), db.ForeignKey('classes.class_id'), nullable=False, index=True)
    pref_type = db.Column(db.String(10), nullable=False)   # 'ROOM' or 'TIME'
    target_val = db.Column(db.String(200), nullable=False)
    pref_score = db.Column(db.Float, default=0.0)

    def __repr__(self):
        return f'<Preference {self.class_id} {self.pref_type}={self.target_val}>'


class ScheduleConstraint(db.Model):
    """分布约束（全局硬/软分布规则）"""
    __tablename__ = 'constraints'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    constraint_id = db.Column(db.String(50), nullable=False, index=True)
    const_type = db.Column(db.String(50), nullable=False)
    pref = db.Column(db.String(10), nullable=True)
    class_id = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f'<Constraint {self.constraint_id} {self.const_type}>'


class SystemConfig(db.Model):
    __tablename__ = 'system_config'
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.Text)


# ══════════════════════════════════════════════════════════════
#  用户与权限模型
# ══════════════════════════════════════════════════════════════

class User(db.Model, UserMixin):
    """系统用户（管理员 / 教师 / 学生）"""
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(100), nullable=False, default='')
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')
    _is_active = db.Column('is_active', db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False)
    avatar_path = db.Column(db.String(200), nullable=True)
    instructor_id = db.Column(db.String(50), db.ForeignKey('instructors.instructor_id'), nullable=True)
    api_token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    api_token_expires = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    instructor = db.relationship('Instructor', backref='user_account', foreign_keys=[instructor_id])
    notifications = db.relationship(
        'Notification', backref='recipient', lazy='dynamic',
        foreign_keys='Notification.recipient_id'
    )

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self._is_active

    @is_active.setter
    def is_active(self, value):
        self._is_active = value

    def set_password(self, password):
        from extensions import bcrypt
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        from extensions import bcrypt
        return bcrypt.check_password_hash(self.password_hash, password)

    @staticmethod
    def validate_password_policy(password: str) -> bool:
        if len(password) < 8:
            return False
        return any(c.isalpha() for c in password) and any(c.isdigit() for c in password)

    def generate_api_token(self):
        self.api_token = secrets.token_urlsafe(32)
        self.api_token_expires = datetime.datetime.utcnow() + datetime.timedelta(hours=24)

    def revoke_api_token(self):
        self.api_token = None
        self.api_token_expires = None

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class AuditLog(db.Model):
    """审计日志（含登录记录，通过 action_type='LOGIN' 区分）"""
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    operator = db.Column(db.String(80), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)
    ip_address = db.Column(db.String(50))
    result = db.Column(db.String(20), default='success')
    detail = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)

    @classmethod
    def trim_old_logs(cls, keep=5000):
        """超过 keep 条时删除最旧的记录"""
        total = cls.query.count()
        if total <= keep:
            return 0
        cutoff_id = cls.query.order_by(cls.created_at.asc()).offset(total - keep).first()
        if cutoff_id:
            deleted = cls.query.filter(cls.id < cutoff_id.id).delete()
            db.session.commit()
            return deleted
        return 0


class Notification(db.Model):
    __tablename__ = 'notification'
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)
    source = db.Column(db.String(50), default='manual')

    @classmethod
    def unread_count(cls, user_id: int) -> int:
        return cls.query.filter_by(recipient_id=user_id, is_read=False).count()


class CourseApplication(db.Model):
    __tablename__ = 'course_application'
    __table_args__ = (
        db.UniqueConstraint('student_id', 'course_id', name='uq_student_course'),
    )
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.String(50), db.ForeignKey('classes.class_id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    applied_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    review_comment = db.Column(db.Text, default='')

    student = db.relationship('User', foreign_keys=[student_id], backref='applications')
    course = db.relationship('ClassRecord', backref='applications')
    reviewer = db.relationship('User', foreign_keys=[reviewer_id])



