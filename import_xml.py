"""
import_xml.py
============
将 ITC-2007 格式的 XML 排课数据集解析并写入 7 张表数据库（参考 pythonProject1/text.py）。

用法：
    python import_xml.py data/pu-fal07-cs.xml
    python import_xml.py data/pu-fal07-cs.xml --clear   # 先清空再导入

写入的数据集（7 张表）：
    rooms              - 教室资源（含可用性掩码）
    instructors        - 教师/讲师
    classes            - 教学班（合并 Offering/Subpart ID）
    students           - 学生主表
    student_requests   - 学生选课需求（CLASS / OFFERING 合并）
    preferences        - 软偏好（教师/教室偏好评分）
    constraints        - 分布约束（全局硬/软规则）
"""

import sys
import os
import argparse
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import (db, Room, Instructor, ClassRecord, StudentRecord,
                    StudentRequest, Preference, ScheduleConstraint, SystemConfig)


def parse_xml(xml_path: str) -> dict:
    """解析 XML，返回结构化字典（与 pythonProject1/text.py 对齐）"""
    if not os.path.exists(xml_path):
        raise FileNotFoundError(f"找不到文件：{xml_path}")

    print(f"正在解析 {xml_path} ...")
    tree = ET.parse(xml_path)
    root = tree.getroot()

    result = {
        'slots_per_day': int(root.get('slotsPerDay', 288)),
        'rooms': [],
        'classes': [],
        'constraints': [],
        'students': []
    }

    # ── 1. 教室（含 sharing/pattern 可用性掩码）────────────────
    for room in root.findall('./rooms/room'):
        r_id = room.get('id')
        cap = room.get('capacity')
        if not r_id or not cap:
            continue
        loc = room.get('location', '0,0').split(',')
        x = float(loc[0]) if loc[0] else 0.0
        y = float(loc[1]) if len(loc) > 1 and loc[1] else 0.0

        pattern_str = None
        unit_val = None
        sharing = room.find('sharing')
        if sharing is not None:
            pat_el = sharing.find('pattern')
            if pat_el is not None:
                pattern_str = pat_el.text
                unit_val = int(pat_el.get('unit', 1))

        result['rooms'].append({
            'room_id': r_id,
            'capacity': int(cap),
            'loc_x': x,
            'loc_y': y,
            'availability_pattern': pattern_str,
            'availability_unit': unit_val
        })

    # ── 2. 教学班 + 教师 + 偏好 ───────────────────────────────
    for cls in root.findall('./classes/class'):
        c_id = cls.get('id')
        if not c_id:
            continue
        offering_id = cls.get('offering')
        subpart_id = cls.get('subpart')
        limit = int(cls.get('classLimit', 0))

        inst_elem = cls.find('instructor')
        inst_id = inst_elem.get('id') if inst_elem is not None else None

        # 偏好：教室偏好
        room_prefs = []
        for rp in cls.findall('room'):
            room_prefs.append({
                'pref_type': 'ROOM',
                'target_val': rp.get('id'),
                'pref_score': float(rp.get('pref', 0))
            })

        # 偏好：时间偏好
        time_prefs = []
        for tp in cls.findall('time'):
            t_val = f"{tp.get('days')}_{tp.get('start')}_{tp.get('length')}"
            time_prefs.append({
                'pref_type': 'TIME',
                'target_val': t_val,
                'pref_score': float(tp.get('pref', 0))
            })

        result['classes'].append({
            'class_id': c_id,
            'subpart_id': subpart_id,
            'offering_id': offering_id,
            'class_limit': limit,
            'instructor_id': inst_id,
            'prefs': room_prefs + time_prefs
        })

    # ── 3. 分布约束 ───────────────────────────────────────────
    for con in root.findall('./groupConstraints/constraint'):
        con_id = con.get('id')
        if not con_id:
            continue
        c_type = con.get('type', '')
        pref = con.get('pref', '')
        for sub_cls in con.findall('class'):
            result['constraints'].append({
                'constraint_id': con_id,
                'const_type': c_type,
                'pref': pref,
                'class_id': sub_cls.get('id')
            })

    # ── 4. 学生选课 ───────────────────────────────────────────
    for student in root.findall('./students/student'):
        s_id = student.get('id')
        if not s_id:
            continue
        requests = []
        for req_cls in student.findall('class'):
            requests.append({'target_id': req_cls.get('id'), 'request_type': 'CLASS'})
        for req_off in student.findall('offering'):
            requests.append({'target_id': req_off.get('id'), 'request_type': 'OFFERING'})
        result['students'].append({'student_id': s_id, 'requests': requests})

    print(f"解析完成：{len(result['rooms'])} 间教室，{len(result['classes'])} 门课，"
          f"{len(result['constraints'])} 条约束，{len(result['students'])} 名学生")
    return result


def import_to_db(data: dict, clear: bool = False):
    """将解析结果写入 7 张表"""
    with app.app_context():
        db.create_all()

        if clear:
            print("清空旧排课数据...")
            StudentRequest.query.delete()
            StudentRecord.query.delete()
            Preference.query.delete()
            ScheduleConstraint.query.delete()
            ClassRecord.query.delete()
            Instructor.query.delete()
            Room.query.delete()
            db.session.commit()
            print("清空完成")

        # ── 1. 写入教室 ──────────────────────────────────────
        room_count = 0
        for r in data['rooms']:
            if Room.query.get(r['room_id']):
                continue
            db.session.add(Room(**r))
            room_count += 1
        db.session.commit()
        print(f"写入教室：{room_count} 间")

        # ── 2. 写入教学班 + 教师 + 偏好 ─────────────────────
        inst_count = 0
        class_count = 0
        pref_count = 0
        for c in data['classes']:
            inst_id = c['instructor_id']
            if inst_id and not Instructor.query.get(inst_id):
                db.session.add(Instructor(instructor_id=inst_id))
                inst_count += 1

            if not ClassRecord.query.get(c['class_id']):
                db.session.add(ClassRecord(
                    class_id=c['class_id'],
                    subpart_id=c['subpart_id'],
                    offering_id=c['offering_id'],
                    class_limit=c['class_limit'],
                    instructor_id=inst_id
                ))
                class_count += 1

            for p in c['prefs']:
                db.session.add(Preference(class_id=c['class_id'], **p))
                pref_count += 1

            if class_count % 500 == 0 and class_count > 0:
                db.session.commit()

        db.session.commit()
        print(f"写入教师：{inst_count} 位，教学班：{class_count} 门，偏好：{pref_count} 条")

        # ── 3. 写入约束 ──────────────────────────────────────
        con_count = 0
        for con in data['constraints']:
            db.session.add(ScheduleConstraint(**con))
            con_count += 1
        db.session.commit()
        print(f"写入约束：{con_count} 条")

        # ── 4. 写入学生 + 选课需求 ───────────────────────────
        stu_count = 0
        req_count = 0
        for s in data['students']:
            if not StudentRecord.query.get(s['student_id']):
                db.session.add(StudentRecord(student_id=s['student_id']))
                stu_count += 1
            for req in s['requests']:
                db.session.add(StudentRequest(student_id=s['student_id'], **req))
                req_count += 1
            if (stu_count + req_count) % 2000 == 0:
                db.session.commit()
        db.session.commit()
        print(f"写入学生：{stu_count} 名，选课需求：{req_count} 条")

        # ── 5. 写入全局参数 ──────────────────────────────────
        conf = SystemConfig.query.get('slotsPerDay')
        if not conf:
            conf = SystemConfig(key='slotsPerDay')
        conf.value = str(data['slots_per_day'])
        db.session.add(conf)
        db.session.commit()

        print("\n========== 导入完成 ==========")
        print(f"  rooms            : {Room.query.count()}")
        print(f"  instructors      : {Instructor.query.count()}")
        print(f"  classes          : {ClassRecord.query.count()}")
        print(f"  students         : {StudentRecord.query.count()}")
        print(f"  student_requests : {StudentRequest.query.count()}")
        print(f"  preferences      : {Preference.query.count()}")
        print(f"  constraints      : {ScheduleConstraint.query.count()}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='将 ITC-2007 XML 数据集导入 7 表数据库')
    parser.add_argument('xml_file', help='XML 文件路径，如 data/pu-fal07-cs.xml')
    parser.add_argument('--clear', action='store_true', help='导入前清空旧排课数据')
    args = parser.parse_args()

    data = parse_xml(args.xml_file)
    import_to_db(data, clear=args.clear)
