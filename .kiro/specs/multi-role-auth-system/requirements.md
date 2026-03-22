# 需求文档

## 简介

本功能在现有 Flask 智能排课系统基础上，新增多角色认证体系，包括登录验证界面、个人中心，以及管理员端、学生端、教师端三个角色的差异化功能视图。系统在保留原有遗传算法排课、XML 导入、课表展示、Excel 导出等核心能力的同时，通过角色权限控制实现数据隔离与功能分级，并新增丰富的可视化图表模块（甘特图、雷达图、桑基图、收敛曲线、词云等），预留通知公告、选课申请、课程评价、消息中心等可扩展模块，为后续功能迭代提供基础。

---

## 词汇表

- **Auth_System**：认证与授权系统，负责用户身份验证、会话管理和权限控制
- **User**：系统注册用户，拥有唯一用户名、密码和角色标识
- **Admin**：管理员角色用户，拥有系统全部操作权限
- **Teacher_User**：教师角色用户，与现有 Teacher 数据模型关联，可查看本人课表及管理个人信息
- **Student_User**：学生角色用户，可查看公开课表、提交选课申请及参与课程评价
- **Session**：用户登录后服务端维护的会话状态，包含用户 ID、角色和过期时间
- **Permission**：角色对应的操作权限集合，决定用户可访问的路由和功能
- **Profile**：用户个人中心，展示并允许修改个人基本信息
- **Notification**：系统向用户推送的公告或消息，包含标题、内容、已读状态
- **CourseApplication**：学生提交的选课申请记录，包含课程、学生、状态字段
- **CourseReview**：学生对已选课程提交的评价记录，包含评分和文字内容
- **AuditLog**：管理员操作审计日志，记录关键操作的操作人、时间和内容
- **PasswordPolicy**：密码复杂度规则，要求长度不少于 8 位且包含字母与数字
- **RateLimiter**：登录频率限制器，防止暴力破解攻击
- **GanttChart**：教室利用率甘特图，按时间轴展示每间教室的占用与空闲时段
- **RadarChart**：教师课程分布雷达图，多维度展示教师的课程类型与时段偏好
- **SankeyChart**：课程分配桑基图，展示课程→教师→教室的资源分配流向
- **ConvergenceCurve**：算法收敛曲线，展示遗传算法每次运行中 hard conflicts 的下降过程
- **CalendarView**：日历式周视图，类 Google Calendar 网格布局的个人课表展示
- **KanbanBoard**：看板视图，以 Kanban 三列形式展示选课申请的状态流转
- **WordCloud**：评价词云，基于课程评价文本生成关键词可视化
- **CapacityChart**：教室容量对比图，展示教室额定容量与实际使用人数的差异

---

## 需求

### 需求 1：用户注册与账号管理

**用户故事：** 作为管理员，我希望能够创建和管理系统用户账号，以便为教师和学生分配对应角色的访问权限。

#### 验收标准

1. THE Auth_System SHALL 支持三种用户角色：admin、teacher、student
2. WHEN 管理员提交新用户表单时，THE Auth_System SHALL 验证用户名唯一性，若重复则返回"用户名已存在"的错误提示
3. WHEN 管理员创建用户时，THE Auth_System SHALL 按照 PasswordPolicy 对初始密码进行哈希存储，不得以明文形式保存
4. WHEN 管理员为教师角色用户创建账号时，THE Auth_System SHALL 提供关联现有 Teacher 数据记录的选项
5. THE Auth_System SHALL 支持管理员停用或启用指定用户账号
6. WHEN 管理员停用某用户账号时，THE Auth_System SHALL 立即使该用户的所有活跃 Session 失效
7. THE Auth_System SHALL 在用户列表页面展示用户名、角色、关联信息、账号状态和创建时间

---

### 需求 2：登录与会话管理

**用户故事：** 作为系统用户，我希望通过用户名和密码登录系统，以便根据我的角色访问对应的功能模块。

#### 验收标准

1. THE Auth_System SHALL 提供独立的登录页面，包含用户名输入框、密码输入框和登录按钮
2. WHEN 用户提交登录表单时，THE Auth_System SHALL 在 500ms 内完成身份验证并返回结果
3. WHEN 用户名或密码错误时，THE Auth_System SHALL 返回"用户名或密码错误"的统一提示，不得区分两者
4. WHEN 同一 IP 地址在 10 分钟内连续登录失败达到 5 次时，THE RateLimiter SHALL 锁定该 IP 的登录请求 15 分钟
5. WHEN 用户成功登录时，THE Auth_System SHALL 创建 Session 并将用户重定向至对应角色的默认首页
6. WHEN 用户点击退出登录时，THE Auth_System SHALL 销毁服务端 Session 并重定向至登录页面
7. WHILE 用户 Session 处于活跃状态，THE Auth_System SHALL 在用户每次请求时自动刷新 Session 过期时间
8. WHEN 用户 Session 超过 120 分钟未活动时，THE Auth_System SHALL 使 Session 失效并在下次请求时重定向至登录页面
9. WHEN 未登录用户访问受保护路由时，THE Auth_System SHALL 重定向至登录页面并保留原始目标 URL

---

### 需求 3：基于角色的访问控制（RBAC）

**用户故事：** 作为系统设计者，我希望不同角色的用户只能访问其权限范围内的功能，以便保障数据安全和操作合规。

#### 验收标准

1. THE Auth_System SHALL 对每个受保护路由执行 Permission 检查，未授权访问返回 403 状态码
2. THE Auth_System SHALL 按以下规则划分路由权限：
   - admin 角色可访问全部路由
   - teacher 角色可访问课表查看、个人中心、通知中心路由
   - student 角色可访问课表查看、选课申请、课程评价、个人中心、通知中心路由
3. WHEN teacher 角色用户访问仅限 admin 的路由时，THE Auth_System SHALL 返回 403 并展示权限不足提示页面
4. WHEN student 角色用户访问仅限 admin 或 teacher 的路由时，THE Auth_System SHALL 返回 403 并展示权限不足提示页面
5. THE Auth_System SHALL 根据当前用户角色动态渲染导航菜单，隐藏无权限的菜单项
6. WHERE 管理员角色，THE Auth_System SHALL 在导航栏展示用户管理、数据管理、排课生成、系统配置入口

---

### 需求 4：管理员端功能

**用户故事：** 作为管理员，我希望拥有完整的系统管理能力，以便统一管理用户、数据、排课和系统配置。

#### 验收标准

1. THE Auth_System SHALL 为管理员提供数据概览仪表盘，展示用户总数、课程总数、教室总数、教师总数和最近一次排课时间
2. WHEN 管理员触发 XML 数据导入时，THE Auth_System SHALL 保留原有导入逻辑并在导入完成后记录 AuditLog
3. WHEN 管理员启动遗传算法排课时，THE Auth_System SHALL 保留原有排课逻辑并在排课完成后记录 AuditLog
4. THE Auth_System SHALL 为管理员提供用户管理页面，支持创建、编辑、停用和删除用户
5. THE Auth_System SHALL 为管理员提供 AuditLog 查询页面，支持按操作人、操作类型和时间范围筛选
6. WHEN 管理员发布 Notification 时，THE Auth_System SHALL 支持选择目标角色（全体、仅教师、仅学生）进行定向推送
7. THE Auth_System SHALL 为管理员提供选课申请审核页面，支持批量审批或拒绝 CourseApplication
8. WHEN 管理员导出课表时，THE Auth_System SHALL 保留原有 Excel 导出逻辑

---

### 需求 5：教师端功能

**用户故事：** 作为教师，我希望查看本人的课表安排并管理个人信息，以便合理规划教学工作。

#### 验收标准

1. WHEN 教师角色用户登录后访问课表页面时，THE Auth_System SHALL 默认按当前登录教师过滤课表，仅展示该教师的课程安排
2. THE Auth_System SHALL 为教师提供个人课表的 CalendarView 周视图，按星期和节次展示课程名称、教室和班级信息
3. WHERE 教师账号已关联 Teacher 数据记录，THE Auth_System SHALL 在个人中心展示该教师的课程列表及本学期课时统计环形图
4. THE Auth_System SHALL 为教师提供修改个人密码的功能，新密码须符合 PasswordPolicy
5. WHEN 教师提交密码修改时，THE Auth_System SHALL 验证旧密码正确后方可更新，旧密码错误则返回错误提示
6. THE Auth_System SHALL 为教师展示未读 Notification 数量角标，并提供通知列表页面
7. WHEN 教师标记通知为已读时，THE Auth_System SHALL 更新对应 Notification 的已读状态
8. THE Auth_System SHALL 为教师提供查看本人课程的 CourseReview 列表，展示评分均值、评价内容及 WordCloud 词云图

---

### 需求 6：学生端功能

**用户故事：** 作为学生，我希望查看课表、提交选课申请并对课程进行评价，以便参与教学管理流程。

#### 验收标准

1. THE Auth_System SHALL 为学生提供公开课表查看页面，支持按教师、教室、星期筛选
2. THE Auth_System SHALL 为学生提供选课申请入口，学生可对课程提交 CourseApplication
3. WHEN 学生提交 CourseApplication 时，THE Auth_System SHALL 检查该学生对同一课程是否已有待审核或已通过的申请，若存在则返回"已申请"提示
4. WHEN 管理员审批 CourseApplication 后，THE Auth_System SHALL 向对应学生推送审批结果 Notification
5. THE Auth_System SHALL 为学生提供 KanbanBoard 看板，以"待审核"、"已通过"、"已拒绝"三列展示所有 CourseApplication 记录
6. WHEN 学生对状态为"已通过"的 CourseApplication 对应课程提交 CourseReview 时，THE Auth_System SHALL 验证评分在 1 至 5 的整数范围内
7. IF 学生对同一课程已提交过 CourseReview，THEN THE Auth_System SHALL 拒绝重复提交并返回"已评价"提示
8. THE Auth_System SHALL 为学生展示未读 Notification 数量角标，并提供通知列表页面
9. THE Auth_System SHALL 为学生提供 CalendarView 个人课表，展示已通过申请的课程安排

---

### 需求 7：个人中心

**用户故事：** 作为系统用户，我希望在个人中心查看和修改个人信息，以便保持账号信息的准确性。

#### 验收标准

1. THE Auth_System SHALL 为所有角色用户提供统一的个人中心页面入口，位于导航栏右上角
2. THE Auth_System SHALL 在个人中心展示用户名、角色、注册时间和最近登录时间
3. THE Auth_System SHALL 允许用户修改显示名称（昵称），长度限制为 2 至 50 个字符
4. WHEN 用户提交个人信息修改时，THE Auth_System SHALL 在 200ms 内完成保存并返回成功提示
5. THE Auth_System SHALL 为用户提供头像上传功能，支持 JPG 和 PNG 格式，文件大小不超过 2MB
6. WHEN 用户上传头像时，THE Auth_System SHALL 将图片裁剪并缩放至 200×200 像素后存储
7. IF 用户上传的头像文件超过 2MB 或格式不符，THEN THE Auth_System SHALL 返回"文件格式或大小不符合要求"的错误提示
8. THE Auth_System SHALL 在个人中心展示用户最近 10 条登录记录，包含登录时间和 IP 地址

---

### 需求 8：通知与消息中心

**用户故事：** 作为系统用户，我希望接收系统通知和消息，以便及时了解排课结果、申请审批等重要信息。

#### 验收标准

1. THE Auth_System SHALL 为每位用户维护独立的 Notification 收件箱
2. WHEN 管理员发布通知时，THE Auth_System SHALL 为目标角色的每位用户创建独立的 Notification 记录
3. THE Auth_System SHALL 在导航栏以角标形式展示当前用户的未读 Notification 数量
4. WHEN 用户访问通知列表页面时，THE Auth_System SHALL 按发布时间降序展示所有 Notification，并区分已读和未读状态
5. THE Auth_System SHALL 支持用户一键标记全部通知为已读
6. WHEN 用户删除 Notification 时，THE Auth_System SHALL 仅删除该用户的通知副本，不影响其他用户
7. THE Auth_System SHALL 支持系统自动触发通知，包括：排课完成通知（推送给全体教师）、选课申请审批结果通知（推送给对应学生）

---

### 需求 9：密码安全与账号保护

**用户故事：** 作为系统管理员，我希望系统具备完善的密码安全机制，以便保护用户账号不被未授权访问。

#### 验收标准

1. THE PasswordPolicy SHALL 要求密码长度不少于 8 个字符，且同时包含字母和数字
2. WHEN 用户设置或修改密码时，THE Auth_System SHALL 使用 bcrypt 算法对密码进行哈希处理后存储
3. THE Auth_System SHALL 支持管理员为指定用户重置密码，重置后系统生成随机初始密码并通过页面展示给管理员
4. WHEN 管理员重置用户密码时，THE Auth_System SHALL 强制该用户在下次登录时修改密码
5. THE Auth_System SHALL 记录每次密码修改操作至 AuditLog，包含操作人和操作时间，不记录密码内容
6. IF 用户提交的新密码与当前密码相同，THEN THE Auth_System SHALL 返回"新密码不能与当前密码相同"的提示

---

### 需求 10：操作审计日志

**用户故事：** 作为管理员，我希望系统记录关键操作的审计日志，以便追溯异常操作和满足合规要求。

#### 验收标准

1. THE Auth_System SHALL 自动记录以下操作至 AuditLog：用户登录、用户登出、用户创建、用户停用、密码重置、XML 数据导入、排课生成、通知发布
2. EACH AuditLog 记录 SHALL 包含操作人用户名、操作类型、操作时间、客户端 IP 地址和操作结果（成功/失败）
3. THE Auth_System SHALL 为管理员提供 AuditLog 查询界面，支持按操作人、操作类型、时间范围组合筛选
4. THE Auth_System SHALL 支持管理员将筛选后的 AuditLog 导出为 CSV 文件
5. WHILE AuditLog 总记录数超过 10000 条，THE Auth_System SHALL 自动归档 90 天前的日志至独立存储表，不影响主表查询性能

---

### 需求 11：系统配置管理（可扩展）

**用户故事：** 作为管理员，我希望通过界面管理系统配置参数，以便在不修改代码的情况下调整系统行为。

#### 验收标准

1. THE Auth_System SHALL 提供系统配置管理页面，支持管理员通过界面修改 SystemConfig 中的配置项
2. THE Auth_System SHALL 支持配置项的分组展示，包括：排课参数组、会话参数组、安全参数组
3. WHEN 管理员修改配置项时，THE Auth_System SHALL 验证配置值的合法性（如数值范围、格式），非法值返回具体错误提示
4. WHEN 管理员保存配置修改时，THE Auth_System SHALL 记录修改前后的值至 AuditLog
5. THE Auth_System SHALL 支持管理员将配置项恢复为系统默认值

---

### 需求 12：数据统计与报表（可扩展）

**用户故事：** 作为管理员，我希望查看系统使用数据的统计报表，以便了解系统运行状况和教学资源利用情况。

#### 验收标准

1. THE Auth_System SHALL 在管理员仪表盘展示以下统计图表：各角色用户数量分布（饼图）、近 7 天登录次数趋势（折线图）、教室使用率（柱状图）
2. THE Auth_System SHALL 统计每位教师的周课时数，并在教师管理页面以列表形式展示
3. THE Auth_System SHALL 统计每间教室的周使用节次和使用率，并在教室管理页面展示
4. WHEN 管理员请求导出统计报表时，THE Auth_System SHALL 生成包含上述统计数据的 Excel 文件并提供下载
5. THE Auth_System SHALL 支持管理员查看选课申请的统计数据，包括各课程申请人数和审批通过率

---

### 需求 15：排课数据可视化（可扩展）

**用户故事：** 作为管理员，我希望通过多种可视化图表直观了解排课结果的质量与资源分配情况，以便快速发现问题并优化方案。

#### 验收标准

1. THE Auth_System SHALL 提供 GanttChart 页面，以时间轴为横轴、教室为纵轴，展示每间教室在周一至周五各节次的占用状态，空闲时段以灰色标注
2. WHEN 用户在 GanttChart 上悬停某个占用块时，THE Auth_System SHALL 以 Tooltip 形式展示该时段的课程名称、授课教师和班级人数
3. THE Auth_System SHALL 提供 SankeyChart 页面，展示课程→教师→教室三层资源分配流向，节点宽度与课程数量成正比
4. WHEN 排课算法运行完成后，THE Auth_System SHALL 在排课生成页面展示 ConvergenceCurve，以折线图呈现每代迭代的 hard conflicts 数量变化，X 轴为迭代代数，Y 轴为冲突数
5. THE Auth_System SHALL 提供 CapacityChart，以分组柱状图对比每间教室的额定容量与实际使用人数，超出容量的教室以红色高亮标注
6. THE Auth_System SHALL 在排课质量分析报告中新增冲突热力图，以 5×8 网格（5天×8节次）展示各时段的冲突密度，颜色深浅表示冲突严重程度
7. WHEN 管理员切换不同排课历史记录时，THE Auth_System SHALL 动态更新上述所有可视化图表的数据

---

### 需求 16：教师端可视化（可扩展）

**用户故事：** 作为教师，我希望通过可视化图表了解自己的课程安排和学生评价情况，以便更好地规划教学工作。

#### 验收标准

1. THE Auth_System SHALL 为教师提供 CalendarView 个人课表，以类 Google Calendar 的周网格布局展示课程块，每个课程块显示课程名称、教室和时长
2. WHEN 教师点击 CalendarView 中的课程块时，THE Auth_System SHALL 展示该课程的详细信息弹窗，包含班级人数、教室容量和课程描述
3. THE Auth_System SHALL 为教师提供本学期课时统计环形图，展示已排课时与总课时的比例，环形中心显示完成百分比
4. THE Auth_System SHALL 为教师提供 RadarChart，以多边形雷达图展示该教师在周一至周五各天的课程数量分布，帮助教师了解自身工作负荷的时间分布
5. WHEN 教师账号关联的课程存在 CourseReview 数据时，THE Auth_System SHALL 展示 WordCloud，基于评价文本中的高频词汇生成词云，词频越高字体越大
6. THE Auth_System SHALL 为教师提供课程评分趋势折线图，展示每门课程在不同时期的平均评分变化

---

### 需求 17：学生端可视化（可扩展）

**用户故事：** 作为学生，我希望通过可视化界面直观管理选课申请和查看课表，以便高效完成选课流程。

#### 验收标准

1. THE Auth_System SHALL 为学生提供 CalendarView 个人课表，展示已通过申请的课程安排，布局与教师端保持一致
2. THE Auth_System SHALL 为学生提供 KanbanBoard 选课申请看板，以"待审核"、"已通过"、"已拒绝"三列展示所有 CourseApplication 记录，每张卡片显示课程名称、申请时间和教师姓名
3. WHEN 学生在 KanbanBoard 中点击某张申请卡片时，THE Auth_System SHALL 展示该申请的详细信息，包含审批时间和审批意见
4. THE Auth_System SHALL 为学生提供课程评分分布柱状图，展示某门课程历史评分（1-5分）的频次分布，帮助学生参考选课
5. THE Auth_System SHALL 为学生提供已选课程的学习负荷分析图，以每日课时数柱状图展示一周内的课程密度分布

---

### 需求 13：前端界面与用户体验

**用户故事：** 作为系统用户，我希望界面风格统一、操作流畅，以便高效完成日常任务。

#### 验收标准

1. THE Auth_System SHALL 在现有 Bootstrap 5 基础模板上扩展，保持全站视觉风格一致
2. THE Auth_System SHALL 为登录页面提供独立布局，不显示主导航栏
3. THE Auth_System SHALL 根据当前用户角色在导航栏右上角展示用户头像、显示名称和角色标签
4. WHEN 用户在移动端访问时，THE Auth_System SHALL 保持响应式布局，导航栏折叠为汉堡菜单
5. THE Auth_System SHALL 对所有表单提交提供前端即时验证，在用户离开输入框时触发验证并展示内联错误提示
6. WHEN 后端返回操作成功或失败时，THE Auth_System SHALL 以 Toast 通知形式展示结果，持续时间为 3 秒
7. THE Auth_System SHALL 为所有数据表格提供分页功能，每页默认展示 20 条记录，支持用户调整为 10、50 条

---

### 需求 14：API 接口规范（可扩展）

**用户故事：** 作为开发者，我希望系统提供规范的 RESTful API，以便未来对接移动端或第三方系统。

#### 验收标准

1. THE Auth_System SHALL 为认证相关操作提供 JSON API 端点：POST /api/auth/login、POST /api/auth/logout
2. WHEN API 请求缺少必要参数时，THE Auth_System SHALL 返回 400 状态码和包含 `error` 字段的 JSON 响应
3. WHEN API 请求的身份验证失败时，THE Auth_System SHALL 返回 401 状态码
4. WHEN API 请求的权限不足时，THE Auth_System SHALL 返回 403 状态码
5. THE Auth_System SHALL 为通知、选课申请、课程评价提供对应的 RESTful API 端点，遵循统一的响应格式：`{"code": 0, "data": {}, "message": ""}`
6. WHERE 启用 API 访问，THE Auth_System SHALL 支持基于 Token 的无状态认证方式，Token 有效期为 24 小时
