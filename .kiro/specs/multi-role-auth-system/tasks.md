# 实现计划：多角色认证系统（multi-role-auth-system）

## 概述

基于现有 Flask 智能排课系统，叠加多角色认证与权限控制体系。技术栈：Flask + SQLAlchemy + SQLite + Bootstrap 5 + Chart.js + D3.js + Jinja2。实现顺序遵循"基础设施 → 数据模型 → 认证核心 → 三端视图 → 可视化 → API → 测试"的渐进式策略，确保每阶段均可独立验证。

## 任务列表

- [x] 1. 基础设施搭建
  - [x] 1.1 安装依赖并创建 `extensions.py`
    - 在 `requirements.txt` 中新增：`flask-login`, `flask-bcrypt`, `flask-limiter`, `hypothesis`, `Pillow`
    - 新建 `extensions.py`，初始化 `LoginManager`（`login_view='auth.login'`，`login_message='请先登录'`）、`Bcrypt`、`Limiter`（`key_func=get_remote_address`）三个扩展实例
    - 在 `app.py` 的 `create_app()` 或初始化块中调用 `login_manager.init_app(app)`、`bcrypt.init_app(app)`、`limiter.init_app(app)`
    - _需求：2.1、2.4、9.2_

  - [x] 1.2 创建 `decorators.py` RBAC 权限装饰器
    - 实现 `role_required(*roles)` 装饰器：检查 `current_user.is_authenticated`，不满足则 `abort(401)`；检查 `current_user.role not in roles`，不满足则 `abort(403)`
    - 实现三个快捷装饰器：`admin_required`、`teacher_required`、`student_required`，分别调用 `role_required('admin')`、`role_required('admin','teacher')`、`role_required('admin','teacher','student')`
    - _需求：3.1、3.2、3.3、3.4_

  - [x] 1.3 创建 `utils/audit.py` 审计日志工具
    - 实现 `log_action(action_type: str, result: str, detail: str = '')` 函数
    - 函数内创建 `AuditLog` 实例，填充 `operator=current_user.username`、`action_type`、`ip_address=request.remote_addr`、`result`、`detail`，执行 `db.session.add` + `db.session.commit`
    - 支持的 `action_type` 枚举常量：`LOGIN`、`LOGOUT`、`USER_CREATE`、`USER_DISABLE`、`USER_ENABLE`、`PASSWORD_RESET`、`PASSWORD_CHANGE`、`XML_IMPORT`、`SCHEDULE_GENERATE`、`NOTIFICATION_PUBLISH`、`CONFIG_CHANGE`、`APPLICATION_REVIEW`
    - _需求：10.1、10.2_

  - [x] 1.4 注册 Blueprint 并配置错误处理器
    - 在 `app.py` 中注册 `auth_bp`、`admin_bp`、`teacher_bp`、`student_bp`、`api_bp` 五个 Blueprint，前缀分别为 `/auth`、`/admin`、`/teacher`、`/student`、`/api`
    - 注册全局错误处理器：`403` → 渲染 `errors/403.html`；`404` → 渲染 `errors/404.html`；`429` → 渲染登录页并展示锁定剩余时间；`500` → 渲染 `errors/500.html` 并记录异常
    - 注册 `before_request` 钩子：检测 `session['last_active']`，超过 120 分钟则调用 `logout_user()` 并重定向登录页；每次请求刷新 `session['last_active']`
    - _需求：2.7、2.8、2.9、3.1_

- [x] 2. 数据模型扩展与数据库迁移
  - [x] 2.1 在 `models.py` 中新增 `User` 模型
    - 实现 `User(db.Model, UserMixin)` 类，字段：`id`、`username`（唯一索引）、`display_name`、`password_hash`、`role`（admin/teacher/student）、`is_active`、`must_change_password`、`avatar_path`、`teacher_id`（外键→Teacher）、`api_token`（唯一）、`api_token_expires`、`created_at`
    - 实现 `set_password(password)`（bcrypt 哈希）、`check_password(password)`（bcrypt 验证）、`validate_password_policy(password)` 静态方法（长度≥8，含字母和数字）
    - 实现 `get_id()` 方法供 Flask-Login 使用；实现 `is_active` property 返回 `self._is_active`
    - 注册 `@login_manager.user_loader` 回调函数
    - _需求：1.1、1.3、9.1、9.2_

  - [x] 2.2 在 `models.py` 中新增 `LoginRecord` 模型
    - 字段：`id`、`user_id`（外键→User）、`ip_address`、`logged_in_at`、`success`
    - 在 `User` 模型中添加 `login_records = db.relationship('LoginRecord', backref='user', lazy='dynamic', order_by='LoginRecord.logged_in_at.desc()')`
    - _需求：7.8_

  - [x] 2.3 在 `models.py` 中新增 `AuditLog` 和 `ArchivedAuditLog` 模型
    - `AuditLog` 字段：`id`、`operator`、`action_type`、`ip_address`、`result`（success/failure）、`detail`、`created_at`；在 `created_at` 上建立索引
    - `ArchivedAuditLog` 字段与 `AuditLog` 相同，额外增加 `archived_at`；表名 `archived_audit_log`
    - 实现 `AuditLog.archive_old_logs()` 类方法：查询 90 天前记录，批量插入 `ArchivedAuditLog`，删除原记录，仅在总记录数超过 10000 时触发
    - _需求：10.1、10.2、10.5_

  - [x] 2.4 在 `models.py` 中新增 `Notification` 模型
    - 字段：`id`、`recipient_id`（外键→User）、`title`、`content`、`is_read`、`created_at`、`source`（manual/schedule_done/application_result）
    - 在 `User` 模型中添加 `notifications = db.relationship('Notification', backref='recipient', lazy='dynamic')`
    - 实现 `Notification.unread_count(user_id)` 类方法
    - _需求：8.1、8.2、8.3_

  - [x] 2.5 在 `models.py` 中新增 `CourseApplication` 和 `CourseReview` 模型
    - `CourseApplication` 字段：`id`、`student_id`（外键→User）、`course_id`（外键→Course）、`status`（pending/approved/rejected）、`applied_at`、`reviewed_at`、`reviewer_id`（外键→User）、`review_comment`；添加联合唯一约束 `uq_student_course`
    - `CourseReview` 字段：`id`、`student_id`（外键→User）、`course_id`（外键→Course）、`score`（1-5）、`content`、`created_at`；添加联合唯一约束 `uq_review_student_course` 和 CHECK 约束 `score BETWEEN 1 AND 5`
    - _需求：6.2、6.3、6.6、6.7_

  - [x] 2.6 执行数据库迁移并创建初始管理员账号
    - 在 `app.py` 或独立脚本 `init_db.py` 中调用 `db.create_all()` 创建所有新表
    - 实现 `create_default_admin()` 函数：若 `User` 表为空，创建用户名 `admin`、角色 `admin`、密码 `Admin123` 的初始管理员账号
    - 在应用启动时自动调用 `create_default_admin()`
    - _需求：1.1、1.3_

- [x] 3. 认证模块（auth Blueprint）
  - [x] 3.1 创建 `blueprints/auth.py` 并实现登录视图
    - 实现 `GET /auth/login`：渲染 `auth/login.html`，已登录用户重定向至对应角色首页
    - 实现 `POST /auth/login`：使用 Flask-Limiter 装饰（`@limiter.limit("5 per 10 minutes")`）；验证用户名和密码，失败时统一返回"用户名或密码错误"（不区分两者）；成功时创建 `LoginRecord`、调用 `login_user()`、记录 `AuditLog(LOGIN, success)`、重定向至角色对应首页（admin→`/admin/dashboard`，teacher→`/teacher/dashboard`，student→`/student/dashboard`）
    - 检测 `user.must_change_password`，若为 True 则重定向至 `/auth/change-password`
    - _需求：2.1、2.2、2.3、2.4、2.5、10.1_

  - [x] 3.2 实现登出与密码修改视图
    - 实现 `GET /auth/logout`：调用 `logout_user()`，记录 `AuditLog(LOGOUT, success)`，重定向至 `/auth/login`
    - 实现 `GET/POST /auth/change-password`：GET 渲染修改密码表单；POST 验证旧密码（`check_password`），验证新密码符合 PasswordPolicy，验证新旧密码不同，更新 `password_hash`，清除 `must_change_password`，记录 `AuditLog(PASSWORD_CHANGE, success)`
    - _需求：2.6、5.4、5.5、9.1、9.5、9.6_

  - [x] 3.3 创建登录页模板 `templates/auth/login.html`
    - 独立布局（不继承 `role_base.html`），居中卡片式设计，Bootstrap 5 `container` + `row justify-content-center`
    - 包含：系统 Logo/标题区域、用户名输入框（`id="username"`）、密码输入框（`id="password"`，`type="password"`）、登录按钮
    - 前端验证：`blur` 事件触发，用户名非空检查，密码非空检查，Bootstrap `was-validated` 样式
    - 显示 Flask `flash` 消息（错误提示红色 alert，成功提示绿色 alert）
    - 429 锁定时展示倒计时提示："登录已被锁定，请 X 分钟后重试"
    - _需求：2.1、13.2_

  - [x] 3.4 创建基础模板 `templates/role_base.html`
    - 继承 `base.html`，新增角色感知导航栏：左侧品牌 Logo + 导航链接（根据 `current_user.role` 条件渲染）；右上角展示用户头像（`<img>` 或默认 SVG 占位）、显示名称、角色标签（Badge）、未读通知角标（红色 Badge，数量来自 `Notification.unread_count`）、退出登录按钮
    - admin 导航项：仪表盘、用户管理、审计日志、通知发布、选课审核、排课可视化
    - teacher 导航项：我的课表、通知中心、个人中心
    - student 导航项：公开课表、选课申请、我的看板、通知中心、个人中心
    - 响应式：`navbar-toggler` 汉堡菜单，移动端折叠
    - Toast 容器：`<div id="toast-container" class="position-fixed bottom-0 end-0 p-3">`，配套 JS 函数 `showToast(message, type)`
    - _需求：3.5、3.6、8.3、13.1、13.3、13.4、13.6_

- [x] 4. 管理员端（admin Blueprint）
  - [x] 4.1 创建 `blueprints/admin.py` 并实现仪表盘视图
    - 实现 `GET /admin/dashboard`：查询统计数据（用户总数、课程总数、教室总数、教师总数、最近排课时间）；查询各角色用户数量（admin/teacher/student 各自计数）；查询近 7 天每日登录次数；查询教室使用率（已排课教室数/总教室数）；将所有数据传入模板
    - _需求：4.1、12.1_

  - [x] 4.2 创建仪表盘模板 `templates/admin/dashboard.html`
    - 继承 `role_base.html`，顶部 4 个统计卡片（用户总数、课程总数、教室总数、教师总数），使用 Bootstrap `card` + `col-md-3`
    - 第一行图表：用户角色分布饼图（Chart.js `doughnut`，`id="roleChart"`）+ 近 7 天登录趋势折线图（Chart.js `line`，`id="loginTrendChart"`）
    - 第二行图表：教室使用率柱状图（Chart.js `bar`，`id="roomUsageChart"`）+ 最近排课时间信息卡
    - 所有图表数据通过 Jinja2 `{{ data | tojson }}` 注入，Chart.js 初始化代码内联在 `<script>` 块中
    - _需求：4.1、12.1_

  - [x] 4.3 实现用户管理视图（CRUD）
    - 实现 `GET /admin/users`：分页查询所有用户（每页 20 条），支持按角色、状态筛选；传入 Teacher 列表供关联选择
    - 实现 `POST /admin/users/create`：验证用户名唯一性，验证密码策略，bcrypt 哈希密码，创建 User，记录 `AuditLog(USER_CREATE)`；若角色为 teacher 且提供 `teacher_id` 则关联
    - 实现 `POST /admin/users/<id>/toggle`：切换 `is_active` 状态；停用时使该用户 Session 失效（通过 `flask_login.logout_user` 或标记 `is_active=False` 使 `user_loader` 返回 None）；记录 `AuditLog(USER_DISABLE/USER_ENABLE)`
    - 实现 `POST /admin/users/<id>/reset-password`：生成随机 12 位密码（含字母数字），哈希存储，设置 `must_change_password=True`，记录 `AuditLog(PASSWORD_RESET)`，在响应中展示明文密码给管理员
    - 实现 `POST /admin/users/<id>/delete`：软删除（设置 `is_active=False`）或硬删除，记录审计日志
    - _需求：1.2、1.3、1.4、1.5、1.6、9.3、9.4、9.5_

  - [x] 4.4 创建用户管理模板 `templates/admin/users.html`
    - 继承 `role_base.html`，顶部"新建用户"按钮触发 Bootstrap Modal
    - 新建用户 Modal：用户名输入、密码输入（含策略提示）、角色下拉（admin/teacher/student）、关联教师下拉（角色为 teacher 时显示）、提交按钮
    - 用户列表表格：列（用户名、显示名称、角色 Badge、关联教师、状态 Badge、创建时间、操作列）；操作列包含"停用/启用"切换按钮、"重置密码"按钮、"删除"按钮
    - 分页组件（Bootstrap `pagination`），支持每页 10/20/50 条切换
    - 角色/状态筛选下拉，提交后刷新页面
    - 重置密码后弹出 Modal 展示生成的临时密码，提示管理员记录
    - 前端表单验证：用户名非空、密码符合策略（实时强度提示）
    - _需求：1.2、1.4、1.7、13.5、13.7_

  - [x] 4.5 实现审计日志视图
    - 实现 `GET /admin/audit-log`：支持按 `operator`、`action_type`、`start_date`、`end_date` 组合筛选；分页查询 `AuditLog`；支持 `?export=csv` 参数触发 CSV 导出（使用 Python `csv` 模块，`Content-Disposition: attachment`）
    - _需求：10.3、10.4_

  - [x] 4.6 创建审计日志模板 `templates/admin/audit_log.html`
    - 继承 `role_base.html`，顶部筛选表单（操作人文本框、操作类型下拉、开始日期、结束日期、查询按钮、导出 CSV 按钮）
    - 日志表格：列（操作人、操作类型、IP 地址、结果 Badge（成功绿/失败红）、详情、操作时间）
    - 分页组件，每页 20 条
    - _需求：10.3、10.4_

  - [x] 4.7 实现通知发布视图
    - 实现 `GET /admin/notifications`：展示已发布通知列表（按时间降序）
    - 实现 `POST /admin/notifications/publish`：接收 `title`、`content`、`target_role`（all/teacher/student）；根据 `target_role` 查询目标用户；为每位目标用户创建独立 `Notification` 记录（`source='manual'`）；使用 `db.session` 事务；记录 `AuditLog(NOTIFICATION_PUBLISH)`
    - _需求：4.6、8.2、10.1_

  - [x] 4.8 创建通知发布模板 `templates/admin/notifications.html`
    - 继承 `role_base.html`，左侧发布表单（标题输入、内容 Textarea、目标角色单选按钮组：全体/仅教师/仅学生、发布按钮）
    - 右侧已发布通知列表（标题、目标角色 Badge、发布时间、接收人数）
    - 发布成功后 Toast 提示"通知已发送给 X 位用户"
    - _需求：4.6、8.2_

  - [x] 4.9 实现选课申请审核视图
    - 实现 `GET /admin/applications`：查询所有 `CourseApplication`，支持按状态筛选；关联查询学生姓名和课程名称
    - 实现 `POST /admin/applications/review`：接收 `application_ids[]`（批量）、`action`（approve/reject）、`comment`；批量更新 `status`、`reviewed_at`、`reviewer_id`、`review_comment`；为每位对应学生创建审批结果 `Notification`（`source='application_result'`，标题"选课申请结果"，内容含课程名和审批意见）；使用事务
    - _需求：4.7、6.4、8.7_

  - [x] 4.10 创建选课审核模板 `templates/admin/applications.html`
    - 继承 `role_base.html`，状态筛选 Tab（全部/待审核/已通过/已拒绝）
    - 申请列表表格：列（复选框、学生用户名、课程名称、申请时间、状态 Badge、审批意见、操作）
    - 批量操作工具栏：全选复选框、"批量通过"按钮、"批量拒绝"按钮、审批意见输入框
    - 单条操作：通过/拒绝按钮 + 意见输入
    - _需求：4.7_

- [ ] 5. 检查点 —— 确保基础设施、数据模型、认证模块、管理员端所有测试通过，向用户确认后继续。

- [x] 6. 教师端（teacher Blueprint）
  - [x] 6.1 创建 `blueprints/teacher.py` 并实现教师仪表盘
    - 实现 `GET /teacher/dashboard`：查询当前教师关联的 Teacher 记录；统计本学期已排课时数（查询 `ScheduleEntry` 中该教师的课程数）；查询未读通知数；将数据传入模板
    - _需求：5.3_

  - [x] 6.2 实现教师 CalendarView 课表视图
    - 实现 `GET /teacher/calendar`：查询当前教师的所有排课记录（`ScheduleEntry` 关联 Teacher）；将数据整理为 `{day: {section: [course_info]}}` 结构传入模板
    - _需求：5.1、5.2、16.1_

  - [x] 6.3 创建教师 CalendarView 模板 `templates/teacher/calendar.html`
    - 继承 `role_base.html`，实现类 Google Calendar 周网格布局：横轴为星期一至星期五（5列），纵轴为第 1-8 节（8行），使用 CSS Grid 或 Bootstrap `table`
    - 每个课程块：彩色背景（按课程 ID 哈希分配颜色），显示课程名称、教室编号、班级人数
    - 点击课程块触发 Bootstrap Modal，展示详细信息：课程名称、教室、班级人数、教室容量、课程描述
    - 空闲格子显示灰色背景
    - 响应式：移动端切换为列表视图
    - _需求：5.2、16.1、16.2_

  - [x] 6.4 实现教师个人中心视图
    - 实现 `GET /teacher/profile`：查询当前用户信息、关联 Teacher 记录、课程列表、本学期课时统计（已排/总计）；查询最近 10 条 `LoginRecord`
    - 实现 `POST /teacher/profile/update`：更新 `display_name`（验证 2-50 字符），返回 JSON `{"code":0,"message":"保存成功"}`
    - 实现 `POST /teacher/profile/avatar`：接收上传文件，验证格式（JPG/PNG）和大小（≤2MB），使用 Pillow 裁剪缩放至 200×200，保存至 `static/avatars/<user_id>.jpg`，更新 `User.avatar_path`
    - _需求：5.3、5.4、7.1、7.2、7.3、7.4、7.5、7.6、7.7、7.8_

  - [x] 6.5 创建教师个人中心模板 `templates/teacher/profile.html`
    - 继承 `role_base.html`，左侧：头像展示（200×200，圆形裁剪）+ 上传按钮（触发文件选择，AJAX 上传，上传中显示 Spinner）；用户名、角色 Badge、注册时间、最近登录时间
    - 右侧上方：显示名称修改表单（输入框 + 保存按钮，AJAX 提交，成功后 Toast 提示）；密码修改表单（旧密码、新密码、确认密码，前端验证策略）
    - 右侧下方：本学期课时统计环形图（Chart.js `doughnut`，`id="hoursChart"`，环形中心显示完成百分比）
    - 底部：最近 10 条登录记录表格（登录时间、IP 地址、成功/失败 Badge）
    - _需求：7.1、7.2、7.3、7.4、7.5、7.8、16.3_

  - [x] 6.6 实现教师通知中心视图
    - 实现 `GET /teacher/notifications`：查询当前用户所有通知，按 `created_at` 降序，分页（每页 20 条）
    - 实现 `POST /teacher/notifications/<id>/read`：标记单条通知为已读，返回 JSON
    - 实现 `POST /teacher/notifications/read-all`：标记所有通知为已读，返回 JSON
    - 实现 `DELETE /teacher/notifications/<id>`：删除当前用户的通知副本（验证 `recipient_id == current_user.id`）
    - _需求：5.6、5.7、8.4、8.5、8.6_

  - [x] 6.7 创建教师通知中心模板 `templates/teacher/notifications.html`
    - 继承 `role_base.html`，顶部操作栏："全部标为已读"按钮（AJAX）
    - 通知列表：每条通知卡片显示标题、内容摘要（截断 100 字）、发布时间、已读/未读状态（未读加粗 + 蓝色左边框）
    - 点击通知卡片展开全文并标记已读（AJAX）
    - 每条通知右侧"删除"按钮（AJAX，删除后淡出动画）
    - 分页组件
    - _需求：5.6、5.7、8.4、8.5、8.6_

  - [x] 6.8 实现教师课程评价与可视化视图
    - 实现 `GET /teacher/reviews`：查询当前教师关联课程的所有 `CourseReview`；计算每门课程的平均评分；提取所有评价文本中的词频（jieba 分词或简单空格分词）；将词云数据 `[{text, weight}]` 和评分趋势数据传入模板
    - _需求：5.8、16.5、16.6_

  - [x] 6.9 创建教师评价模板 `templates/teacher/reviews.html`
    - 继承 `role_base.html`，顶部课程选择下拉，切换后 AJAX 刷新图表
    - 词云区域：使用 D3.js `d3-cloud` 插件渲染词云（`<div id="wordcloud-container">`），词频越高字体越大，颜色随机从预设调色板选取
    - 评分趋势折线图：Chart.js `line`（`id="scoreTrendChart"`），X 轴为时间，Y 轴为平均评分（1-5）
    - 评价列表：每条评价显示学生用户名（脱敏）、评分星级（★）、评价内容、提交时间
    - RadarChart 区域：Chart.js `radar`（`id="radarChart"`），展示该教师周一至周五各天课程数量分布
    - _需求：5.8、16.4、16.5、16.6_

- [x] 7. 学生端（student Blueprint）
  - [x] 7.1 创建 `blueprints/student.py` 并实现公开课表视图
    - 实现 `GET /student/schedule`：查询所有排课记录（`ScheduleEntry`），支持按 `teacher_id`、`room_id`、`day` 筛选；将筛选选项（教师列表、教室列表）传入模板
    - _需求：6.1_

  - [x] 7.2 创建公开课表模板 `templates/student/schedule.html`
    - 继承 `role_base.html`，顶部筛选栏：教师下拉、教室下拉、星期下拉、查询按钮（GET 表单提交）
    - 课表以 Bootstrap `table` 展示：行为节次（1-8），列为星期一至五；单元格显示课程名称、教师、教室
    - 每个课程单元格右上角"申请选课"按钮（链接至 `/student/apply?course_id=xxx`）
    - _需求：6.1_

  - [x] 7.3 实现选课申请视图
    - 实现 `GET /student/apply`：展示可申请课程列表（或接收 `course_id` 参数直接展示单课程申请表单）
    - 实现 `POST /student/apply`：检查该学生对该课程是否已有 `pending` 或 `approved` 的申请（查询 `CourseApplication`），若存在返回"已申请"提示；否则创建新 `CourseApplication`（`status='pending'`）；返回 JSON `{"code":0,"message":"申请已提交"}`
    - _需求：6.2、6.3_

  - [x] 7.4 实现学生 KanbanBoard 视图
    - 实现 `GET /student/kanban`：查询当前学生所有 `CourseApplication`，按 `status` 分组为 `pending`、`approved`、`rejected` 三组；关联查询课程名称、教师姓名
    - _需求：6.5、17.2_

  - [x] 7.5 创建 KanbanBoard 模板 `templates/student/kanban.html`
    - 继承 `role_base.html`，三列看板布局（Bootstrap `col-md-4`）：待审核（黄色标题）、已通过（绿色标题）、已拒绝（红色标题）
    - 每张申请卡片（Bootstrap `card`）：课程名称（加粗）、申请时间、教师姓名；已通过/已拒绝卡片额外显示审批时间和审批意见
    - 点击卡片触发 Bootstrap Modal 展示详细信息（课程名称、申请时间、审批时间、审批意见）
    - 已通过卡片底部显示"去评价"按钮（链接至 `/student/review?course_id=xxx`）
    - 列标题旁显示该列卡片数量 Badge
    - _需求：6.5、17.2、17.3_

  - [x] 7.6 实现课程评价视图
    - 实现 `GET /student/review`：接收 `course_id` 参数，验证该学生对该课程有 `approved` 的申请；查询该课程历史评分分布（1-5分各频次）
    - 实现 `POST /student/review`：验证评分为 1-5 整数；检查是否已评价（查询 `CourseReview`），若存在返回"已评价"提示；创建 `CourseReview` 记录；返回 JSON `{"code":0,"message":"评价已提交"}`
    - _需求：6.6、6.7_

  - [x] 7.7 创建课程评价模板 `templates/student/review.html`
    - 继承 `role_base.html`，评价表单：课程名称展示、星级评分选择器（5颗星，点击选择，CSS 高亮）、评价内容 Textarea（可选）、提交按钮
    - 历史评分分布柱状图：Chart.js `bar`（`id="scoreDistChart"`），X 轴为 1-5 分，Y 轴为频次
    - 提交成功后 Toast 提示，表单禁用（防止重复提交）
    - _需求：6.6、6.7、17.4_

  - [x] 7.8 实现学生 CalendarView 个人课表视图
    - 实现 `GET /student/calendar`：查询当前学生所有 `approved` 状态的 `CourseApplication`，关联查询对应课程的排课记录；整理为周网格数据结构
    - _需求：6.9、17.1_

  - [x] 7.9 创建学生 CalendarView 模板 `templates/student/schedule_calendar.html`
    - 继承 `role_base.html`，与教师 CalendarView 布局一致（CSS Grid 周网格，5列×8行）
    - 课程块显示课程名称、教室、教师姓名
    - 底部学习负荷分析图：Chart.js `bar`（`id="workloadChart"`），X 轴为周一至周五，Y 轴为当天课时数
    - _需求：6.9、17.1、17.5_

  - [x] 7.10 实现学生通知中心视图
    - 实现 `GET /student/notifications`、`POST /student/notifications/<id>/read`、`POST /student/notifications/read-all`、`DELETE /student/notifications/<id>`（逻辑与教师端相同，路由前缀不同）
    - _需求：6.8、8.4、8.5、8.6_

  - [x] 7.11 创建学生通知中心模板 `templates/student/notifications.html`
    - 与教师通知中心模板结构相同，继承 `role_base.html`
    - _需求：6.8、8.4、8.5、8.6_

  - [x] 7.12 实现学生个人中心视图与模板
    - 实现 `GET /student/profile`、`POST /student/profile/update`、`POST /student/profile/avatar`（逻辑与教师端相同）
    - 创建 `templates/student/profile.html`：与教师个人中心布局相同，但不显示课时统计环形图；底部显示选课统计（已通过申请数、待审核数）
    - _需求：7.1、7.2、7.3、7.4、7.5、7.6、7.7、7.8_

- [ ] 8. 检查点 —— 确保教师端和学生端所有视图可正常访问，CalendarView 和 KanbanBoard 渲染正确，向用户确认后继续。

- [x] 9. 排课可视化（admin Blueprint 下的 viz 子模块）
  - [x] 9.1 实现 GanttChart 数据接口与视图
    - 实现 `GET /api/viz/gantt`：查询所有 `ScheduleEntry`，返回 `[{room_id, room_name, day, section, course_name, teacher_name, class_size}]` JSON 数组；按 `room_id` 和 `day` 排序
    - 实现 `GET /admin/viz/gantt`：渲染 `admin/viz/gantt.html`，传入教室列表和排课数据
    - _需求：15.1、15.2_

  - [x] 9.2 创建 GanttChart 模板 `templates/admin/viz/gantt.html`
    - 继承 `role_base.html`，使用 Chart.js `bar`（水平方向，`indexAxis: 'y'`）实现甘特图
    - Y 轴为教室列表，X 轴为时间段（节次 1-8，按星期分组）；每个占用块为彩色矩形，空闲时段为灰色
    - 鼠标悬停 Tooltip 显示：课程名称、授课教师、班级人数
    - 顶部星期筛选按钮组（周一至周五），切换后重新渲染图表（AJAX 获取数据）
    - 图表容器 `<canvas id="ganttChart" height="600">`，Chart.js 完整初始化代码
    - _需求：15.1、15.2_

  - [x] 9.3 实现 SankeyChart 数据接口与视图
    - 实现 `GET /api/viz/sankey`：查询排课数据，构建三层节点（课程→教师→教室）和连接（`{source, target, value}`）；返回 `{nodes:[{id,name,layer}], links:[{source,target,value}]}` JSON
    - 实现 `GET /admin/viz/sankey`：渲染 `admin/viz/sankey.html`
    - _需求：15.3_

  - [x] 9.4 创建 SankeyChart 模板 `templates/admin/viz/sankey.html`
    - 继承 `role_base.html`，使用 D3.js `d3-sankey` 插件渲染桑基图
    - SVG 容器 `<svg id="sankeyChart" width="100%" height="500">`
    - 节点按层（课程/教师/教室）着色，节点宽度与课程数量成正比
    - 连接线透明度 0.5，鼠标悬停高亮并显示 Tooltip（流量数值）
    - 引入 D3.js CDN 和 `d3-sankey` CDN，完整 JS 渲染代码
    - _需求：15.3_

  - [x] 9.5 实现 ConvergenceCurve 数据接口与视图
    - 在遗传算法排课完成后，将每代 `hard_conflicts` 数据序列化存储（可存入 `SystemConfig` 表的 `convergence_data` 键，JSON 格式 `{generations:[],conflicts:[]}`）
    - 实现 `GET /api/viz/convergence`：读取最近一次排课的收敛数据，返回 `{generations:[int], conflicts:[int]}`
    - 实现 `GET /admin/viz/convergence`：渲染 `admin/viz/convergence.html`
    - _需求：15.4_

  - [x] 9.6 创建 ConvergenceCurve 模板 `templates/admin/viz/convergence.html`
    - 继承 `role_base.html`，Chart.js `line`（`id="convergenceChart"`）
    - X 轴为迭代代数（generations），Y 轴为 hard conflicts 数量
    - 折线平滑（`tension: 0.3`），填充区域半透明蓝色
    - 图表标题"遗传算法收敛曲线"，X/Y 轴标签，网格线
    - 若无数据则显示"请先运行排课算法"提示
    - _需求：15.4_

  - [x] 9.7 实现 CapacityChart 数据接口与视图
    - 实现 `GET /api/viz/capacity`：查询所有教室的 `capacity` 和实际使用人数（`ScheduleEntry` 中该教室课程的最大班级人数）；返回 `[{room_id, room_name, capacity, actual, over_capacity}]`
    - 实现 `GET /admin/viz/capacity`：渲染 `admin/viz/capacity.html`
    - _需求：15.5_

  - [x] 9.8 创建 CapacityChart 模板 `templates/admin/viz/capacity.html`
    - 继承 `role_base.html`，Chart.js `bar`（`id="capacityChart"`）分组柱状图
    - 每间教室两根柱子：额定容量（蓝色）和实际使用人数（绿色，超容量时红色）
    - X 轴为教室名称，Y 轴为人数；超容量教室柱子颜色通过 `backgroundColor` 数组动态设置
    - 图例、标题、Tooltip 完整配置
    - _需求：15.5_

  - [x] 9.9 实现冲突热力图数据接口与视图
    - 实现 `GET /api/viz/heatmap`：统计每个时段（5天×8节次）的冲突数量（同一时段同一教室有多门课程则计为冲突）；返回 `[[int]*8]*5` 二维数组
    - 实现 `GET /admin/viz/heatmap`：渲染 `admin/viz/heatmap.html`
    - _需求：15.6_

  - [x] 9.10 创建冲突热力图模板 `templates/admin/viz/heatmap.html`
    - 继承 `role_base.html`，使用 Chart.js `matrix` 插件（或自定义 D3.js）渲染 5×8 热力图网格
    - 行为星期一至五，列为第 1-8 节；单元格颜色深浅表示冲突严重程度（白→浅红→深红）
    - 鼠标悬停显示 Tooltip：星期、节次、冲突数
    - 颜色图例（0冲突→白色，高冲突→深红色）
    - _需求：15.6_

  - [x] 9.11 实现排课历史切换功能
    - 在 `SystemConfig` 或新建 `ScheduleHistory` 表中存储多次排课结果的元数据（排课时间、冲突数、版本号）
    - 在所有可视化页面顶部添加"排课历史"下拉选择器，切换后通过 AJAX 传入 `schedule_version` 参数重新获取数据并更新图表
    - _需求：15.7_

- [x] 10. 个人中心统一模块
  - [x] 10.1 实现头像上传通用处理函数
    - 在 `utils/avatar.py` 中实现 `save_avatar(file, user_id) -> str`：验证 MIME 类型（`image/jpeg`、`image/png`）和文件大小（≤2MB）；使用 Pillow 打开图片（捕获 `UnidentifiedImageError`）；裁剪为正方形（取短边）；缩放至 200×200；保存为 JPEG 至 `static/avatars/<user_id>.jpg`；返回相对路径
    - 若验证失败抛出自定义 `AvatarValidationError` 异常，视图层捕获后返回"文件格式或大小不符合要求"
    - _需求：7.5、7.6、7.7_

  - [x] 10.2 实现管理员个人中心视图与模板
    - 实现 `GET /admin/profile`、`POST /admin/profile/update`、`POST /admin/profile/avatar`（逻辑与教师端相同）
    - 创建 `templates/admin/profile.html`：与教师个人中心布局相同，底部显示系统统计摘要（总用户数、总审计日志数）
    - _需求：7.1、7.2、7.3、7.4、7.5、7.6、7.7、7.8_

- [x] 11. RESTful API 端点（api Blueprint）
  - [x] 11.1 创建 `blueprints/api.py` 并实现认证 API
    - 实现 `POST /api/auth/login`：接收 JSON `{username, password}`，验证参数完整性（缺参返回 400 + `{"error":"缺少参数 username/password"}`）；验证用户名密码；成功时生成 `api_token`（`secrets.token_urlsafe(32)`）、设置 `api_token_expires`（24小时后）、保存至数据库；返回 `{"code":0,"data":{"token":"...","role":"..."},"message":"登录成功"}`；失败返回 401
    - 实现 `POST /api/auth/logout`：验证 Token（`token_required` 装饰器）；清除 `api_token` 和 `api_token_expires`；返回 `{"code":0,"message":"已登出"}`
    - 实现 `token_required` 装饰器：从 `Authorization: Bearer <token>` 头提取 Token；查询 `User`；验证 Token 存在且未过期；注入 `current_token_user` 至请求上下文
    - _需求：14.1、14.2、14.3、14.6_

  - [x] 11.2 实现通知 API 端点
    - 实现 `GET /api/notifications`（`token_required`）：返回当前用户通知列表，格式 `{"code":0,"data":[{id,title,content,is_read,created_at}],"message":""}`
    - 实现 `POST /api/notifications/<id>/read`（`token_required`）：标记已读，返回标准格式
    - 实现 `DELETE /api/notifications/<id>`（`token_required`）：删除通知副本，验证所有权
    - _需求：14.5_

  - [x] 11.3 实现选课申请 API 端点
    - 实现 `GET /api/applications`（`token_required`，student 角色）：返回当前学生申请列表，按状态分组
    - 实现 `POST /api/applications`（`token_required`，student 角色）：接收 `{course_id}`，执行重复申请检查，创建申请；缺参返回 400
    - 实现 `GET /api/applications/<id>`（`token_required`）：返回单条申请详情
    - _需求：14.5_

  - [x] 11.4 实现课程评价 API 端点
    - 实现 `POST /api/reviews`（`token_required`，student 角色）：接收 `{course_id, score, content}`；验证参数完整性（缺参返回 400）；验证评分范围（1-5，否则返回 400）；检查重复评价；创建 `CourseReview`
    - 实现 `GET /api/viz/course/<id>/score_dist`：返回课程评分分布 `{"code":0,"data":{1:n,2:n,3:n,4:n,5:n}}`
    - _需求：14.5_

  - [x] 11.5 实现可视化数据 API 端点
    - 实现 `GET /api/viz/teacher/<id>/radar`：返回教师周一至周五课程数量 `{"code":0,"data":{"labels":["周一"...],"values":[n...]}}`
    - 实现 `GET /api/viz/teacher/<id>/wordcloud`：提取该教师课程评价文本词频，返回 `{"code":0,"data":[{text,weight}]}`
    - 实现 `GET /api/viz/student/<id>/workload`：返回学生每日课时数 `{"code":0,"data":{"days":["周一"...],"hours":[n...]}}`
    - _需求：14.5_

- [x] 12. 错误页面与前端 UX 完善
  - [x] 12.1 创建错误页面模板
    - 创建 `templates/errors/403.html`：继承 `role_base.html`（若已登录）或独立布局；显示"403 权限不足"大标题、说明文字"您没有访问此页面的权限"、返回首页按钮
    - 创建 `templates/errors/404.html`：显示"404 页面不存在"、说明文字、返回首页按钮
    - 创建 `templates/errors/500.html`：显示"500 服务器错误"、说明文字"请稍后重试或联系管理员"、返回首页按钮
    - 三个页面均使用 Bootstrap 5 居中布局，包含适当的图标（Bootstrap Icons 或 emoji）
    - _需求：3.3、3.4_

  - [x] 12.2 完善全局前端 UX 组件
    - 在 `role_base.html` 的 `<script>` 块中实现：`showToast(message, type='success')` 函数（创建 Bootstrap Toast DOM，3秒后自动消失）；`confirmAction(message, callback)` 函数（Bootstrap Modal 确认对话框，用于删除等危险操作）
    - 实现全局 AJAX 错误拦截：`$(document).ajaxError()` 捕获 401（重定向登录页）、403（Toast 提示权限不足）、500（Toast 提示服务器错误）
    - 实现表格分页组件：封装 `renderPagination(currentPage, totalPages, urlTemplate)` 函数，生成 Bootstrap `pagination` HTML
    - _需求：13.5、13.6、13.7_

  - [x] 12.3 为原有路由添加 `@login_required` 守卫
    - 在 `app.py` 中为所有原有路由（XML 导入、排课生成、课表展示、Excel 导出）添加 `@login_required` 装饰器
    - XML 导入和排课生成路由额外添加 `@role_required('admin')` 装饰器
    - 在 XML 导入完成后调用 `log_action(XML_IMPORT, 'success')`；在排课生成完成后调用 `log_action(SCHEDULE_GENERATE, 'success')` 并触发全体教师通知（`source='schedule_done'`）
    - _需求：4.2、4.3、4.8、8.7_

- [ ] 13. 检查点 —— 确保所有路由可访问、权限控制正确、可视化图表渲染正常，向用户确认后继续。

- [ ] 14. 属性测试套件（Hypothesis）
  - [ ] 14.1 创建测试基础设施 `tests/conftest.py`
    - 配置 Flask 测试应用（`TESTING=True`，`SQLALCHEMY_DATABASE_URI='sqlite:///:memory:'`）
    - 实现 `app` fixture（应用上下文）、`client` fixture（测试客户端）、`db` fixture（每个测试前重建表）
    - 实现辅助函数：`create_user(role, username, password)`、`login_client(client, username, password)`
    - _需求：全部_

  - [ ] 14.2 实现属性 1 和属性 2 的测试
    - 实现属性 1 测试（用户角色合法性）：`@given(st.text())` 生成任意角色字符串，验证非法角色被拒绝，合法角色（admin/teacher/student）被接受
      - `# Feature: multi-role-auth-system, Property 1: 用户角色合法性`
    - 实现属性 2 测试（用户名唯一性不变量）：`@given(st.lists(st.text(min_size=1, max_size=20), min_size=2))` 生成用户名列表，验证重复用户名被拒绝且数据库用户数不变
      - `# Feature: multi-role-auth-system, Property 2: 用户名唯一性不变量`
    - _需求：1.1、1.2_

  - [ ]* 14.3 实现属性 3 的测试（密码安全存储）
    - `# Feature: multi-role-auth-system, Property 3: 密码安全存储与策略`
    - `@given(st.text(min_size=8).filter(lambda p: any(c.isalpha() for c in p) and any(c.isdigit() for c in p)))` 生成合法密码，验证哈希 round-trip；`@given(st.text(max_size=7))` 生成不合法密码，验证被拒绝
    - _需求：1.3、9.1、9.2_

  - [ ]* 14.4 实现属性 4 的测试（账号停用使 Session 失效）
    - `# Feature: multi-role-auth-system, Property 4: 账号停用使 Session 失效`
    - `@given(st.sampled_from(['teacher','student']))` 生成角色，创建用户并登录，停用账号，验证后续受保护路由请求被重定向至登录页
    - _需求：1.5、1.6_

  - [ ]* 14.5 实现属性 5 的测试（登录错误消息一致性）
    - `# Feature: multi-role-auth-system, Property 5: 登录错误消息一致性`
    - `@given(st.text(), st.text())` 生成任意用户名/密码组合（确保不匹配任何真实用户），验证错误消息始终为"用户名或密码错误"
    - _需求：2.3_

  - [ ]* 14.6 实现属性 6 的测试（登录成功后角色路由重定向）
    - `# Feature: multi-role-auth-system, Property 6: 登录成功后角色路由重定向`
    - `@given(st.sampled_from(['admin','teacher','student']))` 生成角色，创建对应用户并登录，验证重定向目标 URL 与角色匹配
    - _需求：2.5_

  - [ ]* 14.7 实现属性 7 的测试（登出后 Session 失效）
    - `# Feature: multi-role-auth-system, Property 7: 登出后 Session 失效（Round-Trip）`
    - `@given(st.sampled_from(['/admin/dashboard','/teacher/dashboard','/student/dashboard']))` 生成受保护路由，登录后登出，验证访问该路由被重定向至登录页且 URL 含 `next` 参数
    - _需求：2.6、2.9_

  - [ ]* 14.8 实现属性 8 的测试（Session 活跃时间刷新）
    - `# Feature: multi-role-auth-system, Property 8: Session 活跃时间刷新`
    - `@given(st.datetimes())` 生成请求时间，验证每次请求后 `session['last_active']` 大于等于请求前的值
    - _需求：2.7_

  - [ ]* 14.9 实现属性 9 的测试（角色权限矩阵）
    - `# Feature: multi-role-auth-system, Property 9: 角色权限矩阵`
    - `@given(st.sampled_from(['teacher','student']), st.sampled_from(['/admin/users','/admin/audit-log']))` 生成角色和 admin 专属路由，验证非 admin 角色访问返回 403
    - _需求：3.1、3.2、3.3、3.4_

  - [ ]* 14.10 实现属性 10 的测试（关键操作触发审计日志）
    - `# Feature: multi-role-auth-system, Property 10: 关键操作触发审计日志`
    - `@given(st.sampled_from(['LOGIN','LOGOUT','USER_CREATE','USER_DISABLE','PASSWORD_RESET']))` 生成操作类型，执行对应操作，验证 `AuditLog` 表中存在包含五个必填字段的记录
    - _需求：4.2、4.3、10.1、10.2_

  - [ ]* 14.11 实现属性 11 的测试（教师课表数据隔离）
    - `# Feature: multi-role-auth-system, Property 11: 教师课表数据隔离`
    - `@given(st.integers(min_value=1, max_value=100))` 生成教师 ID，验证课表页面返回的所有课程条目的教师字段均等于当前登录教师
    - _需求：5.1_

  - [ ]* 14.12 实现属性 12 的测试（密码修改需验证旧密码）
    - `# Feature: multi-role-auth-system, Property 12: 密码修改需验证旧密码`
    - `@given(st.text(min_size=8), st.text(min_size=8))` 生成旧密码和错误旧密码，验证错误旧密码时修改被拒绝
    - _需求：5.5_

  - [ ]* 14.13 实现属性 13 的测试（重复提交防护）
    - `# Feature: multi-role-auth-system, Property 13: 重复提交防护（幂等性）`
    - `@given(st.integers(min_value=1), st.text(min_size=1, max_size=20))` 生成学生 ID 和课程 ID，提交申请后再次提交，验证被拒绝且数据库申请数不变
    - _需求：6.3、6.7_

  - [ ]* 14.14 实现属性 14 的测试（评分范围约束）
    - `# Feature: multi-role-auth-system, Property 14: 评分范围约束`
    - `@given(st.integers().filter(lambda x: x < 1 or x > 5))` 生成非法评分，验证被拒绝且数据库不存储该记录；`@given(st.integers(min_value=1, max_value=5))` 生成合法评分，验证被接受
    - _需求：6.6_

  - [ ]* 14.15 实现属性 15 的测试（显示名称长度约束）
    - `# Feature: multi-role-auth-system, Property 15: 显示名称长度约束`
    - `@given(st.text(max_size=1))` 生成过短名称，`@given(st.text(min_size=51))` 生成过长名称，验证均被拒绝且数据库不更新
    - _需求：7.3_

  - [ ]* 14.16 实现属性 16 的测试（头像文件格式与大小约束）
    - `# Feature: multi-role-auth-system, Property 16: 头像文件格式与大小约束`
    - `@given(st.binary(min_size=1))` 生成随机二进制内容（非有效图片），验证被拒绝；生成超过 2MB 的内容，验证被拒绝
    - _需求：7.5、7.7_

  - [ ]* 14.17 实现属性 17 的测试（通知广播完整性）
    - `# Feature: multi-role-auth-system, Property 17: 通知广播完整性`
    - `@given(st.sampled_from(['teacher','student','all']), st.integers(min_value=1, max_value=10))` 生成目标角色和用户数，创建对应用户，发布通知，验证 `Notification` 表中记录数等于目标角色活跃用户数
    - _需求：8.2_

  - [ ]* 14.18 实现属性 18 的测试（通知删除隔离性）
    - `# Feature: multi-role-auth-system, Property 18: 通知删除隔离性`
    - `@given(st.integers(min_value=2, max_value=5))` 生成用户数，发布通知后某用户删除，验证其他用户通知数量不变
    - _需求：8.6_

  - [ ]* 14.19 实现属性 19 的测试（API 参数缺失返回 400）
    - `# Feature: multi-role-auth-system, Property 19: API 参数缺失返回 400`
    - `@given(st.fixed_dictionaries({}))` 生成空请求体，对 `POST /api/auth/login`、`POST /api/applications`、`POST /api/reviews` 发送，验证返回 400 且响应含 `error` 字段
    - _需求：14.2_

  - [ ]* 14.20 实现属性 20 的测试（无效 Token 返回 401）
    - `# Feature: multi-role-auth-system, Property 20: 无效 Token 返回 401`
    - `@given(st.text())` 生成任意 Token 字符串，对需要 Token 认证的 API 端点发送，验证返回 401 且响应含 `message` 字段
    - _需求：14.3_

- [ ] 15. 最终检查点 —— 运行完整测试套件（`pytest tests/ --tb=short`），确保所有非可选测试通过，向用户确认后完成。

## 备注

- 标有 `*` 的子任务为可选测试任务，可在 MVP 阶段跳过以加快进度
- 每个任务均引用具体需求条款，确保可追溯性
- 检查点任务确保增量验证，避免后期集成问题
- 属性测试每条最少运行 100 次迭代（`@settings(max_examples=100)`）
- 所有图表数据均通过 API 端点获取，前后端解耦，便于后续移动端对接
