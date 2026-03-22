# 技术设计文档：多角色认证系统

## 概述

本设计在现有 Flask 智能排课系统基础上，叠加多角色认证与权限控制体系。系统保留原有遗传算法排课、XML 导入、课表展示、Excel 导出等核心能力，通过引入 Flask-Login 实现会话管理，通过 RBAC 装饰器实现路由级权限隔离，并为管理员、教师、学生三端分别提供差异化的功能视图与可视化图表模块。

核心设计原则：
- **最小侵入**：在现有 `app.py` / `models.py` 基础上扩展，不重写已有逻辑
- **角色隔离**：三端路由前缀分离（`/admin`、`/teacher`、`/student`），权限装饰器统一守卫
- **渐进增强**：通知、选课申请、课程评价、可视化图表均以独立 Blueprint 实现，便于后续迭代

---

## 架构

### 整体分层

```
┌─────────────────────────────────────────────────────┐
│                    前端层（Jinja2 + Bootstrap 5）      │
│  base.html → role_base.html → 各角色页面模板          │
│  Chart.js（柱/饼/折线）+ D3.js（Sankey/词云）         │
└────────────────────────┬────────────────────────────┘
                         │ HTTP / AJAX
┌────────────────────────▼────────────────────────────┐
│                    Flask 应用层                       │
│  auth Blueprint   → 登录/登出/会话管理                │
│  admin Blueprint  → 管理员端路由                      │
│  teacher Blueprint→ 教师端路由                        │
│  student Blueprint→ 学生端路由                        │
│  api Blueprint    → RESTful JSON API                 │
│  (原有路由保留，加 @login_required 守卫)               │
└────────────────────────┬────────────────────────────┘
                         │ SQLAlchemy ORM
┌────────────────────────▼────────────────────────────┐
│                    数据层（SQLite）                    │
│  原有表：Teacher / Room / Course / SystemConfig       │
│  新增表：User / LoginRecord / AuditLog /              │
│          Notification / CourseApplication /           │
│          CourseReview / ArchivedAuditLog              │
└─────────────────────────────────────────────────────┘
```

### Blueprint 划分

| Blueprint | 前缀 | 职责 |
|-----------|------|------|
| `auth` | `/auth` | 登录、登出、密码修改、会话管理 |
| `admin` | `/admin` | 仪表盘、用户管理、审计日志、通知发布、可视化 |
| `teacher` | `/teacher` | 个人课表、通知、评价词云、可视化 |
| `student` | `/student` | 公开课表、选课申请、课程评价、看板 |
| `api` | `/api` | 无状态 JSON API（Token 认证） |
| (原有) | `/` | 保留原有路由，加 `@login_required` |

---

## 组件与接口

### Flask-Login 集成

```python
# extensions.py（新建）
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录'

bcrypt = Bcrypt()
limiter = Limiter(key_func=get_remote_address)
```

`User` 模型实现 `UserMixin`，`login_manager.user_loader` 通过 `user_id` 从数据库加载用户。

### RBAC 权限装饰器

```python
# decorators.py（新建）
from functools import wraps
from flask import abort
from flask_login import current_user

def role_required(*roles):
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

# 使用示例
@admin_bp.route('/users')
@login_required
@role_required('admin')
def user_list(): ...
```

### 登录频率限制

使用 Flask-Limiter，对 `POST /auth/login` 应用规则：
- 同一 IP 10 分钟内最多 5 次失败尝试
- 超限后锁定 15 分钟，返回 429 状态码

### 密码安全

- 使用 `flask-bcrypt` 的 `generate_password_hash` / `check_password_hash`
- 密码策略验证函数：长度 ≥ 8，同时含字母和数字
- 强制修改密码标志：`User.must_change_password` 字段，登录后检测并重定向至修改页

### 会话管理

- Flask-Login 的 `remember_me=False`，Session 存储于服务端（Flask 默认 cookie-based，可升级为 Redis）
- 通过 `before_request` 钩子检测 Session 活跃时间，超过 120 分钟未活动则调用 `logout_user()`
- 每次请求刷新 `session['last_active']` 时间戳

### Token API 认证

```python
# 生成 Token（登录时）
import secrets, datetime
token = secrets.token_urlsafe(32)
user.api_token = token
user.api_token_expires = datetime.datetime.utcnow() + datetime.timedelta(hours=24)

# 验证 Token（API 请求）
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        user = User.query.filter_by(api_token=token).first()
        if not user or user.api_token_expires < datetime.datetime.utcnow():
            return jsonify({'code': 401, 'message': 'Token 无效或已过期'}), 401
        ...
    return decorated
```

### 审计日志记录

```python
# utils/audit.py（新建）
def log_action(action_type: str, result: str, detail: str = ''):
    log = AuditLog(
        operator=current_user.username,
        action_type=action_type,
        ip_address=request.remote_addr,
        result=result,
        detail=detail
    )
    db.session.add(log)
    db.session.commit()
```

在需要审计的视图函数末尾调用，或通过 `after_request` 信号自动触发。

### 可视化数据接口

| 图表 | API 端点 | 返回格式 |
|------|----------|----------|
| GanttChart | `GET /api/viz/gantt` | `[{room, day, section, course, teacher, class_size}]` |
| SankeyChart | `GET /api/viz/sankey` | `{nodes:[{id,name}], links:[{source,target,value}]}` |
| ConvergenceCurve | `GET /api/viz/convergence` | `{generations:[int], conflicts:[int]}` |
| CapacityChart | `GET /api/viz/capacity` | `[{room_id, capacity, actual}]` |
| ConflictHeatmap | `GET /api/viz/heatmap` | `[[int]*8]*5`（5天×8节次冲突数） |
| RadarChart | `GET /api/viz/teacher/<id>/radar` | `{labels:[str], values:[int]}` |
| WordCloud | `GET /api/viz/teacher/<id>/wordcloud` | `[{text, weight}]` |
| KanbanBoard | `GET /api/student/applications` | `{pending:[],approved:[],rejected:[]}` |
| ScoreDistribution | `GET /api/viz/course/<id>/score_dist` | `{1:n,2:n,3:n,4:n,5:n}` |
| WorkloadChart | `GET /api/viz/student/<id>/workload` | `{days:[str], hours:[int]}` |

---

## 数据模型

### User（新增）

```python
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(50), nullable=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin / teacher / student
    is_active = db.Column(db.Boolean, default=True)
    must_change_password = db.Column(db.Boolean, default=False)
    avatar_path = db.Column(db.String(200), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=True)
    api_token = db.Column(db.String(64), nullable=True, unique=True)
    api_token_expires = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # relationships
    login_records = db.relationship('LoginRecord', backref='user', lazy='dynamic')
    notifications = db.relationship('Notification', backref='recipient', lazy='dynamic')
```

### LoginRecord（新增）

```python
class LoginRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ip_address = db.Column(db.String(45))
    logged_in_at = db.Column(db.DateTime, default=datetime.utcnow)
    success = db.Column(db.Boolean, default=True)
```

### AuditLog（新增）

```python
class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    operator = db.Column(db.String(80), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)
    # 枚举：login/logout/user_create/user_disable/password_reset/
    #       xml_import/schedule_generate/notification_publish/config_change
    ip_address = db.Column(db.String(45))
    result = db.Column(db.String(10))  # success / failure
    detail = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ArchivedAuditLog(db.Model):
    """90天前日志自动归档至此表"""
    __tablename__ = 'archived_audit_log'
    # 字段与 AuditLog 相同
    id = db.Column(db.Integer, primary_key=True)
    operator = db.Column(db.String(80))
    action_type = db.Column(db.String(50))
    ip_address = db.Column(db.String(45))
    result = db.Column(db.String(10))
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime)
    archived_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### Notification（新增）

```python
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # 触发来源：manual / schedule_done / application_result
    source = db.Column(db.String(30), default='manual')
```

### CourseApplication（新增）

```python
class CourseApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.String(50), db.ForeignKey('course.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending/approved/rejected
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    review_comment = db.Column(db.Text, nullable=True)
    # 唯一约束：同一学生对同一课程只能有一条 pending/approved 记录
    __table_args__ = (
        db.UniqueConstraint('student_id', 'course_id', name='uq_student_course'),
    )
```

### CourseReview（新增）

```python
class CourseReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.String(50), db.ForeignKey('course.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)  # 1-5
    content = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint('student_id', 'course_id', name='uq_review_student_course'),
        db.CheckConstraint('score >= 1 AND score <= 5', name='ck_score_range'),
    )
```

### 前端模板结构

```
templates/
├── auth/
│   └── login.html          # 独立布局，无主导航
├── base.html               # 原有基础模板（保留）
├── role_base.html          # 新增：含角色导航、通知角标、用户头像
├── admin/
│   ├── dashboard.html
│   ├── users.html
│   ├── audit_log.html
│   ├── notifications.html
│   └── viz/
│       ├── gantt.html
│       ├── sankey.html
│       ├── convergence.html
│       └── capacity.html
├── teacher/
│   ├── dashboard.html
│   ├── calendar.html       # CalendarView
│   ├── reviews.html        # WordCloud + 评分趋势
│   └── profile.html
└── student/
    ├── schedule.html       # CalendarView
    ├── kanban.html         # KanbanBoard
    ├── apply.html
    └── profile.html
```

`role_base.html` 继承 `base.html`，通过 `current_user.role` 条件渲染三套导航菜单，并在右上角展示头像、显示名称、角色标签和未读通知角标。

---
## 正确性属性

*属性（Property）是在系统所有有效执行路径上都应成立的特征或行为——本质上是对系统应做什么的形式化陈述。属性是人类可读规范与机器可验证正确性保证之间的桥梁。*

### 属性 1：用户角色合法性

*对于任意*通过系统创建的用户，其 `role` 字段的值必须是 `admin`、`teacher`、`student` 三者之一；任何尝试创建角色值不在此集合内的用户请求，系统应拒绝并返回错误。

**验证需求：1.1**

---

### 属性 2：用户名唯一性不变量

*对于任意*两个已存在于系统中的用户，其用户名不能相同；当尝试创建与已有用户名重复的新用户时，系统应拒绝并返回"用户名已存在"提示，且数据库中的用户总数不变。

**验证需求：1.2**

---

### 属性 3：密码安全存储与策略

*对于任意*满足 PasswordPolicy（长度 ≥ 8，同时含字母和数字）的密码，系统存储的哈希值应能通过 bcrypt 验证（round-trip）；对于任意不满足策略的密码字符串，系统应拒绝设置并返回错误，且数据库中不存储任何明文密码。

**验证需求：1.3、9.1、9.2**

---

### 属性 4：账号停用使 Session 失效

*对于任意*处于活跃状态的用户，当管理员将其账号停用后，该用户的 `is_active` 为 `False`，Flask-Login 的 `is_active` 属性返回 `False`，后续任何受保护路由的请求均应被重定向至登录页面。

**验证需求：1.5、1.6**

---

### 属性 5：登录错误消息一致性

*对于任意*用户名错误或密码错误的登录请求，系统返回的错误消息应完全相同（"用户名或密码错误"），不得通过消息内容区分是用户名还是密码出错。

**验证需求：2.3**

---

### 属性 6：登录成功后角色路由重定向

*对于任意*有效用户（admin/teacher/student），成功登录后应被重定向到其角色对应的默认首页（admin→`/admin/dashboard`，teacher→`/teacher/dashboard`，student→`/student/dashboard`），不同角色的重定向目标互不相同。

**验证需求：2.5**

---

### 属性 7：登出后 Session 失效（Round-Trip）

*对于任意*已登录用户，执行登出操作后，再次访问任意受保护路由，系统应将其重定向至登录页面，且重定向 URL 中包含 `next` 参数保留原始目标。

**验证需求：2.6、2.9**

---

### 属性 8：Session 活跃时间刷新

*对于任意*已登录用户，每次成功的 HTTP 请求后，`session['last_active']` 时间戳应被更新为当前时间，且新值大于等于请求前的值。

**验证需求：2.7**

---

### 属性 9：角色权限矩阵

*对于任意*受保护路由和任意用户，若该用户的角色不在该路由允许的角色列表中，系统应返回 403 状态码；具体地：teacher 访问 admin 专属路由返回 403，student 访问 admin 或 teacher 专属路由返回 403，API 请求权限不足时同样返回 403。

**验证需求：3.1、3.2、3.3、3.4、14.4**

---

### 属性 10：关键操作触发审计日志

*对于任意*关键操作（用户登录、登出、创建用户、停用用户、密码重置、XML 导入、排课生成、通知发布、配置修改），操作完成后 `AuditLog` 表中应存在一条对应记录，且该记录包含操作人用户名、操作类型、操作时间、客户端 IP 和操作结果（成功/失败）五个必填字段。

**验证需求：4.2、4.3、10.1、10.2**

---

### 属性 11：教师课表数据隔离

*对于任意*教师用户，其课表页面返回的所有课程条目中，授课教师字段均应等于该用户关联的 Teacher 记录姓名，不包含其他教师的课程。

**验证需求：5.1**

---

### 属性 12：密码修改需验证旧密码

*对于任意*密码修改请求，若提供的旧密码与数据库中存储的哈希不匹配，系统应拒绝修改并返回错误；只有旧密码验证通过后，新密码才会被哈希存储。

**验证需求：5.5**

---

### 属性 13：重复提交防护（幂等性）

*对于任意*学生和课程的组合，若已存在状态为 `pending` 或 `approved` 的 `CourseApplication` 记录，再次提交申请应被拒绝并返回"已申请"提示，数据库中的申请记录数不变；同理，若已存在该学生对该课程的 `CourseReview` 记录，再次提交评价应被拒绝并返回"已评价"提示。

**验证需求：6.3、6.7**

---

### 属性 14：评分范围约束

*对于任意*课程评价提交请求，若评分值不是 1 到 5 之间的整数，系统应拒绝并返回错误，且数据库中不存储该条评价记录。

**验证需求：6.6**

---

### 属性 15：显示名称长度约束

*对于任意*显示名称修改请求，若新名称的字符长度小于 2 或大于 50，系统应拒绝并返回错误，且数据库中的显示名称不被更新。

**验证需求：7.3**

---

### 属性 16：头像文件格式与大小约束

*对于任意*头像上传请求，若文件格式不是 JPG 或 PNG，或文件大小超过 2MB，系统应拒绝并返回"文件格式或大小不符合要求"错误，且不存储任何文件。

**验证需求：7.5、7.7**

---

### 属性 17：通知广播完整性

*对于任意*通知发布操作，若目标角色为 X，则系统中所有角色为 X 的活跃用户都应在 `Notification` 表中收到一条独立的通知记录，且通知总数等于目标角色的活跃用户数。

**验证需求：8.2**

---

### 属性 18：通知删除隔离性

*对于任意*用户删除其通知的操作，该操作只应删除该用户的通知副本（`recipient_id` 匹配），其他用户的同源通知记录数量不变。

**验证需求：8.6**

---

### 属性 19：API 参数缺失返回 400

*对于任意* API 端点，若请求体缺少该端点声明的必要参数，系统应返回 400 状态码，且响应体包含 `error` 字段说明缺失的参数。

**验证需求：14.2**

---

### 属性 20：无效 Token 返回 401

*对于任意*携带无效或已过期 Token 的 API 请求，系统应返回 401 状态码，且响应体包含 `message` 字段。

**验证需求：14.3**

---

## 错误处理

### HTTP 错误页面

| 状态码 | 触发场景 | 处理方式 |
|--------|----------|----------|
| 400 | API 参数缺失/格式错误 | JSON 响应 `{"code":400,"error":"..."}` |
| 401 | API Token 无效/过期 | JSON 响应 `{"code":401,"message":"..."}` |
| 403 | 角色权限不足 | 渲染 `errors/403.html`，展示"权限不足"提示页 |
| 404 | 路由不存在 | 渲染 `errors/404.html` |
| 413 | 上传文件超过 16MB | JSON 响应或 Flash 消息 |
| 429 | 登录频率超限 | 渲染登录页并展示锁定剩余时间 |
| 500 | 服务端异常 | 渲染 `errors/500.html`，记录异常至日志 |

### 表单验证错误

所有表单提交均采用前端即时验证（`blur` 事件触发）+ 后端二次验证的双重策略：
- 前端：Bootstrap 5 的 `was-validated` 类 + 自定义 JS 验证函数
- 后端：返回 Flash 消息或 JSON `{"code": 1, "message": "..."}` 格式

### 数据库事务

涉及多表写入的操作（如发布通知、审批申请）均使用 `db.session` 事务，异常时执行 `db.session.rollback()`，确保数据一致性。

### 文件上传错误

头像上传使用 `Pillow` 处理图片，捕获 `UnidentifiedImageError` 等异常，统一返回"文件格式或大小不符合要求"提示，不暴露内部错误详情。

---

## 测试策略

### 双轨测试方法

本功能采用单元测试与基于属性的测试（PBT）相结合的方式：
- **单元测试**：验证具体示例、边界条件和集成点
- **属性测试**：通过随机输入验证上述 20 条正确性属性

两者互补，共同保障系统正确性。

### 属性测试配置

- 使用 Python 的 `hypothesis` 库进行属性测试
- 每条属性测试最少运行 **100 次**迭代（`@settings(max_examples=100)`）
- 每条属性测试必须通过注释标注对应的设计属性编号
- 标注格式：`# Feature: multi-role-auth-system, Property {N}: {属性标题}`

```python
from hypothesis import given, settings, strategies as st

# Feature: multi-role-auth-system, Property 3: 密码安全存储与策略
@given(st.text(min_size=8).filter(
    lambda p: any(c.isalpha() for c in p) and any(c.isdigit() for c in p)
))
@settings(max_examples=100)
def test_password_hash_round_trip(password):
    hashed = bcrypt.generate_password_hash(password).decode('utf-8')
    assert hashed != password
    assert bcrypt.check_password_hash(hashed, password)
```

### 单元测试重点

单元测试聚焦以下场景，避免与属性测试重复：

1. **登录流程集成测试**：使用 Flask 测试客户端模拟完整登录→访问→登出流程
2. **频率限制边界**：连续 5 次失败后第 6 次被锁定（需求 2.4）
3. **Session 超时**：模拟 `last_active` 超过 120 分钟后访问受保护路由（需求 2.8）
4. **审计日志归档**：插入 10001 条记录后触发归档，验证主表记录数和归档表记录数（需求 10.5）
5. **密码相同拒绝**：新密码与当前密码相同时返回提示（需求 9.6）
6. **管理员仪表盘渲染**：验证页面包含统计数据（需求 4.1）
7. **导航菜单角色渲染**：不同角色登录后导航菜单项不同（需求 3.5）

### 属性测试覆盖矩阵

| 属性编号 | 测试类型 | Hypothesis 策略 |
|----------|----------|-----------------|
| 属性 1 | property | `st.text()` 生成任意角色字符串 |
| 属性 2 | property | `st.lists(st.text())` 生成用户名列表 |
| 属性 3 | property | `st.text()` 生成密码字符串 |
| 属性 4 | property | `st.booleans()` 切换账号状态 |
| 属性 5 | property | `st.text()` 生成任意用户名/密码组合 |
| 属性 6 | property | `st.sampled_from(['admin','teacher','student'])` |
| 属性 7 | property | `st.text()` 生成任意受保护路由路径 |
| 属性 8 | property | `st.datetimes()` 生成请求时间 |
| 属性 9 | property | `st.sampled_from(roles)` × `st.sampled_from(routes)` |
| 属性 10 | property | `st.sampled_from(action_types)` |
| 属性 11 | property | `st.integers()` 生成教师 ID |
| 属性 12 | property | `st.text()` 生成旧密码/新密码 |
| 属性 13 | property | `st.integers()` 生成学生/课程 ID 对 |
| 属性 14 | property | `st.integers()` 生成评分值 |
| 属性 15 | property | `st.text()` 生成显示名称 |
| 属性 16 | property | `st.binary()` 生成文件内容 |
| 属性 17 | property | `st.lists(st.builds(User))` 生成用户列表 |
| 属性 18 | property | `st.integers()` 生成用户 ID |
| 属性 19 | property | `st.fixed_dictionaries({})` 生成缺参请求 |
| 属性 20 | property | `st.text()` 生成 Token 字符串 |
