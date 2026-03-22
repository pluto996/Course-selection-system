"""
假数据初始化脚本
运行方式：python seed_data.py

写入内容：
  - 10 位教师 + 对应教师账号（teacher_id 已绑定，登录后"我的课表"直接有数据）
  - 8 间教室、12 门课程
  - 12 条排课结果（覆盖周一~周五多节次）
  - 3 个学生账号，各有 3 门已通过选课申请
  - 6 条课程评价
  - 假收敛曲线（可视化页面可用）

教师账号与 Teacher 记录的关联规则：
  User.teacher_id = Teacher.id
  即登录后 _get_teacher_record() 直接通过 teacher_id 找到对应教师，
  "我的课表"会显示该教师名下的排课结果。
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import app, scheduler
from models import (db, Teacher, Room, Course, User, CourseApplication,
                    CourseReview, Notification, SystemConfig)

# ── 假数据定义 ────────────────────────────────────────────────

TEACHERS = [
    '张伟', '李娜', '王芳', '刘洋', '陈静',
    '赵磊', '孙丽', '周强', '吴敏', '郑浩',
]

ROOMS = [
    ('A101', 60), ('A102', 60), ('A201', 80), ('A202', 80),
    ('B101', 50), ('B102', 50), ('B201', 100), ('C101', 40),
]

# (course_id, course_name, teacher_name, class_limit)
COURSES = [
    ('CS001', '数据结构',     '张伟', 35),
    ('CS002', '操作系统',     '李娜', 40),
    ('CS003', '计算机网络',   '王芳', 38),
    ('CS004', '数据库原理',   '刘洋', 42),
    ('CS005', '算法设计',     '陈静', 30),
    ('CS006', '软件工程',     '赵磊', 45),
    ('CS007', '编译原理',     '孙丽', 28),
    ('CS008', '人工智能',     '周强', 50),
    ('CS009', '机器学习',     '吴敏', 35),
    ('CS010', '计算机图形学', '郑浩', 25),
    ('CS011', '离散数学',     '张伟', 55),
    ('CS012', '线性代数',     '李娜', 60),
]

# 排课结果：(course_id, day, section, room_id)
# day: 0100000=周一 0010000=周二 0001000=周三 0000100=周四 0000010=周五
SCHEDULE = [
    ('CS001', '0100000', 1, 'A101'),
    ('CS002', '0100000', 2, 'A201'),
    ('CS003', '0010000', 1, 'B101'),
    ('CS004', '0010000', 3, 'A102'),
    ('CS005', '0001000', 2, 'C101'),
    ('CS006', '0001000', 4, 'B201'),
    ('CS007', '0000100', 1, 'A202'),
    ('CS008', '0000100', 3, 'B201'),
    ('CS009', '0000010', 2, 'A201'),
    ('CS010', '0000010', 4, 'C101'),
    ('CS011', '0100000', 4, 'B201'),
    ('CS012', '0010000', 5, 'A201'),
]

# (username, display_name, *approved_course_ids)
STUDENT_USERS = [
    ('student1', '学生甲', 'CS001', 'CS003', 'CS008'),
    ('student2', '学生乙', 'CS002', 'CS004', 'CS009'),
    ('student3', '学生丙', 'CS005', 'CS006', 'CS011'),
]

REVIEWS = [
    ('student1', 'CS001', 5, '讲解清晰 内容充实 收获很大'),
    ('student1', 'CS003', 4, '知识点全面 实验环节有趣'),
    ('student2', 'CS002', 4, '理论扎实 课后作业有挑战性'),
    ('student2', 'CS004', 5, '老师讲得很好 数据库设计思路清晰'),
    ('student3', 'CS005', 3, '算法难度较高 但老师耐心解答'),
    ('student3', 'CS006', 4, '项目实践很有价值 团队协作锻炼充分'),
]


def run():
    with app.app_context():
        db.create_all()

        # ── 1. 清空旧课程相关数据 ────────────────────────────────
        db.session.execute(db.text("DELETE FROM course_teacher"))
        CourseReview.query.delete()
        CourseApplication.query.delete()
        Course.query.delete()
        Room.query.delete()
        Teacher.query.delete()
        db.session.commit()
        print("旧课程数据已清空")

        # ── 2. 写入教室 ──────────────────────────────────────────
        for rid, cap in ROOMS:
            db.session.add(Room(id=rid, capacity=cap))
        db.session.commit()
        print(f"写入 {len(ROOMS)} 个教室")

        # ── 3. 写入教师记录 ──────────────────────────────────────
        teacher_map = {}  # name -> Teacher ORM 对象
        for name in TEACHERS:
            t = Teacher(name=name)
            db.session.add(t)
            db.session.flush()   # 立即获取自增 id
            teacher_map[name] = t
        db.session.commit()
        print(f"写入 {len(TEACHERS)} 位教师")

        # ── 4. 写入课程 ──────────────────────────────────────────
        course_teacher_map = {}  # course_id -> teacher_name（用于构建排课结果）
        for cid, cname, tname, limit in COURSES:
            possible_times = [
                {'days_str': d, 'days_mask': m, 'start': s, 'length': 20, 'pref': 0}
                for d, m, s in [
                    ('0100000', 32, 96), ('0010000', 16, 120),
                    ('0001000', 8,  168), ('0000100', 4, 192), ('0000010', 2, 216)
                ]
            ]
            possible_rooms = [{'id': r[0], 'pref': 0} for r in ROOMS if r[1] >= limit][:3]
            c = Course(
                id=cid,
                class_limit=limit,
                possible_times_json=json.dumps(possible_times),
                possible_rooms_json=json.dumps(possible_rooms)
            )
            t = teacher_map.get(tname)
            if t:
                c.instructors.append(t)
            db.session.add(c)
            course_teacher_map[cid] = tname
        db.session.commit()
        print(f"写入 {len(COURSES)} 门课程")

        # ── 5. 写入教师账号（teacher_id 绑定到 Teacher 记录）────
        #
        # 关联规则：User.teacher_id = Teacher.id
        # 登录后系统通过 current_user.teacher_id 找到 Teacher 记录，
        # 再从排课结果中筛选 teacher == Teacher.name 的条目显示课表。
        #
        print("\n教师账号对应关系：")
        print(f"{'用户名':<20} {'显示名':<8} 关联教师记录")
        print("-" * 45)
        for name in TEACHERS:
            uname = 'teacher_' + name
            existing = User.query.filter_by(username=uname).first()
            if existing:
                # 更新 teacher_id 确保绑定正确
                existing.teacher_id = teacher_map[name].id
                existing.display_name = name
            else:
                u = User(
                    username=uname,
                    display_name=name,
                    role='teacher',
                    teacher_id=teacher_map[name].id   # ← 关键：绑定 teacher_id
                )
                u.set_password('Teacher123')
                db.session.add(u)
            print(f"  {uname:<20} {name:<8} → Teacher.id={teacher_map[name].id}")
        db.session.commit()
        print(f"\n写入 {len(TEACHERS)} 个教师账号（密码均为 Teacher123）")

        # ── 6. 写入学生账号 + 选课申请 ──────────────────────────
        student_map = {}
        for uname, dname, *course_ids in STUDENT_USERS:
            u = User.query.filter_by(username=uname).first()
            if not u:
                u = User(username=uname, display_name=dname, role='student')
                u.set_password('Student123')
                db.session.add(u)
                db.session.flush()
            student_map[uname] = u
            for cid in course_ids:
                existing = CourseApplication.query.filter_by(
                    student_id=u.id, course_id=cid).first()
                if not existing:
                    db.session.add(CourseApplication(
                        student_id=u.id, course_id=cid, status='approved'))
        db.session.commit()
        print(f"写入 {len(STUDENT_USERS)} 个学生账号（密码均为 Student123）")

        # ── 7. 写入课程评价 ──────────────────────────────────────
        for uname, cid, score, content in REVIEWS:
            u = student_map.get(uname)
            if not u:
                continue
            if not CourseReview.query.filter_by(student_id=u.id, course_id=cid).first():
                db.session.add(CourseReview(
                    student_id=u.id, course_id=cid,
                    score=score, content=content))
        db.session.commit()
        print(f"写入 {len(REVIEWS)} 条课程评价")

        # ── 8. 构建假排课结果并持久化 ────────────────────────────
        result = []
        for cid, day, section, room in SCHEDULE:
            tname = course_teacher_map.get(cid, '')
            result.append({
                'day': day,
                'section': section,
                'course_name': cid,
                'teacher': tname,
                'room': room,
                'type': 'primary'
            })

        for key, val in [
            ('schedule_result', json.dumps(result)),
            ('slotsPerDay', '288'),
            ('convergence_data', json.dumps({
                'generations': list(range(1, 51)),
                'conflicts':   [max(0, 20 - i // 3) for i in range(50)],
                'f2':          [round(5.0 - i * 0.08, 2) for i in range(50)],
                'f3':          [round(3.0 - i * 0.05, 2) for i in range(50)],
                'pareto_history': []
            }))
        ]:
            conf = SystemConfig.query.get(key)
            if not conf:
                conf = SystemConfig(key=key)
            conf.value = val
            db.session.add(conf)
        db.session.commit()

        scheduler.result = result
        scheduler.progress.update({
            'status': 'COMPLETED', 'f1': 0,
            'f2': 1.2, 'f3': 0.8, 'generation': 50
        })
        print(f"写入 {len(result)} 条排课结果并加载到内存")

        # ── 汇总 ─────────────────────────────────────────────────
        print("\n========== 初始化完成 ==========")
        print("管理员：       admin          / Admin123")
        print("学生账号：     student1~3     / Student123")
        print("教师账号示例：")
        for name in TEACHERS:
            courses_for_teacher = [c[0] for c in COURSES if c[2] == name]
            sched = [(s[1], s[2]) for s in SCHEDULE if s[0] in courses_for_teacher]
            day_map = {'0100000':'周一','0010000':'周二','0001000':'周三',
                       '0000100':'周四','0000010':'周五'}
            sched_str = ', '.join(f"{day_map[d]}第{sec}节" for d, sec in sched)
            print(f"  teacher_{name:<6} / Teacher123  →  课表：{sched_str or '无'}")


if __name__ == '__main__':
    run()
