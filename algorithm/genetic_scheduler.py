import random
import copy
import threading
import time
import os
import xml.etree.ElementTree as ET
from collections import defaultdict
import math


# ---------------------------------------------------------------------------
# 核心数据解析
# ---------------------------------------------------------------------------

class XMLBasedScheduler:
    """数据加载 + NSGA-II 多目标进化排课算法"""

    def __init__(self, xml_file_path=None, data_dict=None,
                 progress_callback=None, stop_event=None, **kwargs):
        self.progress_callback = progress_callback
        self.stop_event = stop_event

        # GA 参数
        self.population_size = int(kwargs.get('population_size', 50))
        self.generations     = int(kwargs.get('generations', 1000))
        self.crossover_rate  = float(kwargs.get('crossover_rate', 0.8))
        self.mutation_rate   = float(kwargs.get('mutation_rate', 0.2))
        self.elite_size      = int(kwargs.get('elite_size', 2))
        self.init_strategy   = kwargs.get('init_strategy', 'greedy')

        self.slots_per_day = 288
        self.classrooms    = []
        self.courses       = []
        self.course_map    = {}

        if data_dict:
            self.load_from_dict(data_dict)
        elif xml_file_path:
            self.xml_file_path = xml_file_path.replace('\\', '/')
            self.initialize_data()

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------

    @staticmethod
    def parse_xml_to_dict(xml_file_path):
        if not os.path.exists(xml_file_path):
            raise FileNotFoundError(f"File not found: {xml_file_path}")

        tree = ET.parse(xml_file_path)
        root = tree.getroot()

        data = {'slots_per_day': int(root.get('slotsPerDay', 288))}

        classrooms = []
        for room in root.findall('.//rooms/room'):
            classrooms.append({'id': room.get('id'),
                                'capacity': int(room.get('capacity', 0))})
        data['classrooms'] = classrooms

        courses = []
        for cls in root.findall('.//classes/class'):
            c_id = cls.get('id')
            limit = int(cls.get('classLimit', 0))
            instructors = [i.get('id') for i in cls.findall('instructor')]
            if not instructors and cls.get('instructor'):
                instructors.append(cls.get('instructor'))

            possible_times = []
            for t in cls.findall('time'):
                days_str = t.get('days')
                days_mask = int(days_str, 2) if days_str else 0
                possible_times.append({
                    'days_str':  days_str,
                    'days_mask': days_mask,
                    'start':     int(t.get('start')),
                    'length':    int(t.get('length')),
                    'pref':      float(t.get('pref', 0.0))
                })

            possible_rooms = []
            for r in cls.findall('room'):
                possible_rooms.append({'id': r.get('id'),
                                       'pref': float(r.get('pref', 0.0))})

            courses.append({'id': c_id, 'limit': limit,
                            'instructors': instructors,
                            'possible_times': possible_times,
                            'possible_rooms': possible_rooms})
        data['courses'] = courses
        return data

    def load_from_dict(self, data):
        self.slots_per_day = data.get('slots_per_day', 288)
        self.classrooms    = data.get('classrooms', [])
        self.courses       = data.get('courses', [])
        self.course_map    = {c['id']: c for c in self.courses}

    def initialize_data(self):
        data = self.parse_xml_to_dict(self.xml_file_path)
        self.load_from_dict(data)

    # ------------------------------------------------------------------
    # 时间槽工具
    # ------------------------------------------------------------------

    def get_valid_times(self, course):
        standard_starts = [96, 120, 168, 192, 216]
        length = 20
        days_config = [
            ('0100000', 32), ('0010000', 16), ('0001000', 8),
            ('0000100', 4),  ('0000010', 2)
        ]

        def generate_slots(target_masks=None):
            slots = []
            for d_str, d_mask in days_config:
                if target_masks and d_mask not in target_masks:
                    continue
                for s in standard_starts:
                    slots.append({'days_str': d_str, 'days_mask': d_mask,
                                  'start': s, 'length': length, 'pref': 0})
            return slots

        valid_times = copy.deepcopy(course['possible_times']) if course['possible_times'] else []
        if not valid_times:
            return generate_slots()

        has_friday = any(t['days_mask'] & 2 for t in valid_times)
        if not has_friday:
            for f in generate_slots(target_masks=[2]):
                f['pref'] = -0.1
                valid_times.append(f)
        return valid_times

    def check_overlap(self, t1, t2):
        if not (t1['days_mask'] & t2['days_mask']):
            return False
        s1, e1 = t1['start'], t1['start'] + t1['length']
        s2, e2 = t2['start'], t2['start'] + t2['length']
        return s1 < e2 and s2 < e1

    # ------------------------------------------------------------------
    # 个体生成
    # ------------------------------------------------------------------

    def _pick_room(self, course):
        valid = [r for r in self.classrooms if r['capacity'] >= course['limit']]
        if course['possible_rooms']:
            req = {x['id'] for x in course['possible_rooms']}
            filtered = [r for r in valid if r['id'] in req]
            if filtered:
                valid = filtered
        return random.choice(valid) if valid else random.choice(self.classrooms)

    def create_random_individual(self):
        schedule = []
        for idx, course in enumerate(self.courses):
            r = self._pick_room(course)
            t = random.choice(self.get_valid_times(course))
            schedule.append({'course_idx': idx, 'course_id': course['id'],
                              'room_id': r['id'], 'time': t})
        return schedule

    def create_greedy_individual(self):
        schedule = []
        room_usage  = defaultdict(list)
        instr_usage = defaultdict(list)
        indices = list(range(len(self.courses)))
        random.shuffle(indices)

        for idx in indices:
            course = self.courses[idx]
            valid_rooms  = [r for r in self.classrooms if r['capacity'] >= course['limit']]
            if course['possible_rooms']:
                req = {x['id'] for x in course['possible_rooms']}
                filtered = [r for r in valid_rooms if r['id'] in req]
                if filtered:
                    valid_rooms = filtered
            if not valid_rooms:
                valid_rooms = self.classrooms

            valid_times = sorted(self.get_valid_times(course),
                                 key=lambda x: x['pref'], reverse=True)
            random.shuffle(valid_rooms)
            assigned = False

            for t in valid_times:
                for room in valid_rooms:
                    if any(self.check_overlap(t, u) for u in room_usage[room['id']]):
                        continue
                    if any(self.check_overlap(t, u)
                           for instr in course['instructors']
                           for u in instr_usage[instr]):
                        continue
                    schedule.append({'course_idx': idx, 'course_id': course['id'],
                                     'room_id': room['id'], 'time': t})
                    room_usage[room['id']].append(t)
                    for instr in course['instructors']:
                        instr_usage[instr].append(t)
                    assigned = True
                    break
                if assigned:
                    break

            if not assigned:
                r = random.choice(valid_rooms)
                t = random.choice(self.get_valid_times(course))
                schedule.append({'course_idx': idx, 'course_id': course['id'],
                                 'room_id': r['id'], 'time': t})

        schedule.sort(key=lambda x: x['course_idx'])
        return schedule

    # ------------------------------------------------------------------
    # 多目标适应度：三个目标全部最小化
    #   f1 = 硬约束冲突数（教室冲突 + 教师冲突）
    #   f2 = 教师授课负载方差
    #   f3 = 每日课程数量分布方差
    # ------------------------------------------------------------------

    def evaluate(self, individual):
        room_usage  = defaultdict(list)
        instr_usage = defaultdict(list)
        instr_load  = defaultdict(int)
        day_load    = defaultdict(int)

        f1 = 0  # 硬冲突
        for gene in individual:
            course = self.courses[gene['course_idx']]
            r_id   = gene['room_id']
            t      = gene['time']

            # 教室冲突
            for used in room_usage[r_id]:
                if self.check_overlap(t, used):
                    f1 += 1
            room_usage[r_id].append(t)

            # 教师冲突
            for instr in course['instructors']:
                for used in instr_usage[instr]:
                    if self.check_overlap(t, used):
                        f1 += 1
                instr_usage[instr].append(t)
                instr_load[instr] += 1

            day_load[t['days_mask']] += 1

        # f2：教师负载方差（忽略"待定"类教师）
        ignored = {'unknown', '待定', 'none', 'null', 'nan', ''}
        loads = [v for k, v in instr_load.items()
                 if k and k.strip().lower() not in ignored]
        if len(loads) > 1:
            avg = sum(loads) / len(loads)
            f2 = sum((x - avg) ** 2 for x in loads) / len(loads)
        else:
            f2 = 0.0

        # f3：每日课程分布方差（周一~周五）
        target_masks = [32, 16, 8, 4, 2]
        counts = [day_load[m] for m in target_masks]
        avg3 = sum(counts) / len(counts)
        f3 = sum((x - avg3) ** 2 for x in counts) / len(counts)

        return (f1, f2, f3)

    # ------------------------------------------------------------------
    # NSGA-II 核心：非支配排序 + 拥挤距离
    # ------------------------------------------------------------------

    @staticmethod
    def dominates(a, b):
        """a 支配 b：a 在所有目标上不劣于 b，且至少一个目标严格更优（全部最小化）"""
        return all(ai <= bi for ai, bi in zip(a, b)) and any(ai < bi for ai, bi in zip(a, b))

    def fast_non_dominated_sort(self, fitnesses):
        """返回分层列表 fronts[0] = Pareto 前沿索引列表"""
        n = len(fitnesses)
        domination_count = [0] * n      # 被多少个体支配
        dominated_set    = [[] for _ in range(n)]  # 该个体支配哪些
        fronts = [[]]

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                if self.dominates(fitnesses[i], fitnesses[j]):
                    dominated_set[i].append(j)
                elif self.dominates(fitnesses[j], fitnesses[i]):
                    domination_count[i] += 1
            if domination_count[i] == 0:
                fronts[0].append(i)

        current = 0
        while fronts[current]:
            next_front = []
            for i in fronts[current]:
                for j in dominated_set[i]:
                    domination_count[j] -= 1
                    if domination_count[j] == 0:
                        next_front.append(j)
            current += 1
            fronts.append(next_front)

        return [f for f in fronts if f]  # 去掉空层

    @staticmethod
    def crowding_distance(front_indices, fitnesses):
        """计算同一前沿内各个体的拥挤距离"""
        n = len(front_indices)
        if n <= 2:
            return {i: float('inf') for i in front_indices}

        distances = {i: 0.0 for i in front_indices}
        num_obj = len(fitnesses[0])

        for m in range(num_obj):
            sorted_idx = sorted(front_indices, key=lambda i: fitnesses[i][m])
            f_min = fitnesses[sorted_idx[0]][m]
            f_max = fitnesses[sorted_idx[-1]][m]
            span  = f_max - f_min if f_max != f_min else 1e-9

            distances[sorted_idx[0]]  = float('inf')
            distances[sorted_idx[-1]] = float('inf')

            for k in range(1, n - 1):
                distances[sorted_idx[k]] += (
                    fitnesses[sorted_idx[k + 1]][m] -
                    fitnesses[sorted_idx[k - 1]][m]
                ) / span

        return distances

    def nsga2_select(self, population, fitnesses, size):
        """NSGA-II 选择：按前沿层级 + 拥挤距离填充下一代"""
        fronts    = self.fast_non_dominated_sort(fitnesses)
        selected  = []
        crowd_map = {}

        for front in fronts:
            if len(selected) + len(front) <= size:
                selected.extend(front)
            else:
                # 当前前沿放不下，按拥挤距离降序填满
                cd = self.crowding_distance(front, fitnesses)
                crowd_map.update(cd)
                remaining = size - len(selected)
                sorted_front = sorted(front, key=lambda i: cd[i], reverse=True)
                selected.extend(sorted_front[:remaining])
                break

        return [population[i] for i in selected]

    # ------------------------------------------------------------------
    # 遗传算子
    # ------------------------------------------------------------------

    def crossover(self, p1, p2):
        return [copy.deepcopy(p1[i]) if random.random() < 0.5
                else copy.deepcopy(p2[i])
                for i in range(len(p1))]

    def mutate(self, individual):
        ind  = copy.deepcopy(individual)
        idx  = random.randrange(len(ind))
        gene = ind[idx]
        course = self.courses[gene['course_idx']]

        valid_rooms = [r for r in self.classrooms if r['capacity'] >= course['limit']]
        if not valid_rooms:
            valid_rooms = self.classrooms

        if random.random() < 0.5:
            gene['room_id'] = random.choice(valid_rooms)['id']
        else:
            gene['time'] = random.choice(self.get_valid_times(course))

        ind[idx] = gene
        return ind

    # ------------------------------------------------------------------
    # 主循环：NSGA-II
    # ------------------------------------------------------------------

    def run(self, initial_solution=None):
        # 初始化种群
        if initial_solution:
            population = [copy.deepcopy(initial_solution)]
            for _ in range(self.population_size - 1):
                population.append(self.mutate(initial_solution))
        elif self.init_strategy == 'random':
            population = [self.create_random_individual()
                          for _ in range(self.population_size)]
        else:
            population = [self.create_greedy_individual()
                          for _ in range(self.population_size)]

        best_solution = None
        best_f1 = float('inf')

        for gen in range(self.generations):
            if self.stop_event and self.stop_event.is_set():
                break

            # 评估
            fitnesses = [self.evaluate(ind) for ind in population]

            # 记录当前 Pareto 前沿（第一层）
            fronts   = self.fast_non_dominated_sort(fitnesses)
            pf_idx   = fronts[0]
            pf_fits  = [fitnesses[i] for i in pf_idx]

            # 追踪最优（以 f1 最小为主，f1 相同时取 f2+f3 最小）
            for i, fit in enumerate(fitnesses):
                if (fit[0] < best_f1 or
                        (fit[0] == best_f1 and best_solution is None)):
                    best_f1       = fit[0]
                    best_solution = copy.deepcopy(population[i])

            # 进度回调
            if self.progress_callback:
                # 软得分用 -(f2+f3) 兼容前端显示（越大越好）
                best_fit = min(fitnesses, key=lambda x: (x[0], x[1] + x[2]))
                self.progress_callback({
                    'generation':      gen + 1,
                    'hard_conflicts':  int(best_fit[0]),
                    'soft_score':      round(-(best_fit[1] + best_fit[2]), 2),
                    'f1':              best_fit[0],
                    'f2':              round(best_fit[1], 4),
                    'f3':              round(best_fit[2], 4),
                    'status':          'RUNNING',
                    'progress_percent': int((gen / self.generations) * 100),
                    'pareto_front':    [{'f1': f[0], 'f2': round(f[1], 3),
                                         'f3': round(f[2], 3)} for f in pf_fits]
                })

            # NSGA-II 选择 → 生成子代
            parents = self.nsga2_select(population, fitnesses,
                                        self.population_size)

            offspring = []
            # 精英保留：直接保留 Pareto 前沿前 elite_size 个
            elite_inds = [population[i] for i in pf_idx[:self.elite_size]]
            offspring.extend(copy.deepcopy(e) for e in elite_inds)

            while len(offspring) < self.population_size:
                p1 = random.choice(parents)
                p2 = random.choice(parents)
                child = self.crossover(p1, p2)
                if random.random() < self.mutation_rate:
                    child = self.mutate(child)
                offspring.append(child)

            population = offspring
            time.sleep(0.001)

        return best_solution


# ---------------------------------------------------------------------------
# Flask 服务包装层（接口不变）
# ---------------------------------------------------------------------------

class GeneticScheduler:
    def __init__(self):
        self.data        = {'tasks': [], 'classes': [], 'teachers': [], 'courses': []}
        self.result      = []
        self.progress    = {
            'status': 'IDLE', 'generation': 0,
            'hard_conflicts': 0, 'soft_score': 0,
            'f1': 0, 'f2': 0, 'f3': 0,
            'progress_percent': 0, 'history': [],
            'pareto_history': []
        }
        self.stop_event   = threading.Event()
        self.xml_path     = None
        self.best_solution = None
        self.algorithm    = None

    def load_from_memory(self, data_dict):
        self.xml_path  = None
        self.algorithm = XMLBasedScheduler(data_dict=data_dict)
        self._update_stats_from_algo()

    def load_xml_data(self, filepath):
        self.xml_path  = filepath
        self.algorithm = XMLBasedScheduler(xml_file_path=filepath)
        self._update_stats_from_algo()

    def _update_stats_from_algo(self):
        temp  = self.algorithm
        tasks = [{'classId': c['id'], 'courseName': c['id'],
                  'teacher': ','.join(c['instructors']),
                  'students': c['limit']}
                 for c in temp.courses]
        self.data = {
            'tasks':   tasks,
            'classes': [c['id'] for c in temp.courses],
            'teachers': list({t for c in temp.courses for t in c['instructors']}),
            'courses': [c['id'] for c in temp.courses]
        }

    def get_data(self):    return self.data
    def get_result(self):  return self.result
    def get_progress(self): return self.progress

    def stop(self):
        self.stop_event.set()
        self.progress['status'] = 'STOPPED'

    def run_optimization(self, params):
        if not self.algorithm:
            return

        self.stop_event.clear()
        self.progress = {
            'status': 'RUNNING', 'generation': 0,
            'hard_conflicts': 0, 'soft_score': 0,
            'f1': 0, 'f2': 0, 'f3': 0,
            'progress_percent': 0, 'history': [],
            'pareto_history': []
        }

        def on_progress(p):
            self.progress.update(p)
            self.progress['history'].append({
                'gen':  p['generation'],
                'hard': p['hard_conflicts'],
                'soft': p['soft_score'],
                'f2':   p.get('f2', 0),
                'f3':   p.get('f3', 0)
            })
            # 每 20 代记录一次 Pareto 前沿快照
            if p['generation'] % 20 == 0:
                self.progress['pareto_history'].append({
                    'gen':   p['generation'],
                    'front': p.get('pareto_front', [])
                })

        current_data = {
            'slots_per_day': self.algorithm.slots_per_day,
            'classrooms':    self.algorithm.classrooms,
            'courses':       self.algorithm.courses
        }
        self.algorithm = XMLBasedScheduler(
            data_dict=current_data,
            progress_callback=on_progress,
            stop_event=self.stop_event,
            **params
        )

        init_sol = self.best_solution if params.get('continue_optimization') else None
        best     = self.algorithm.run(initial_solution=init_sol)
        self.best_solution = best

        if not self.stop_event.is_set():
            self.progress['status']           = 'COMPLETED'
            self.progress['progress_percent'] = 100

        # 转换结果格式（与原接口完全兼容）
        self.result = []
        if best:
            for item in best:
                course = self.algorithm.course_map[item['course_id']]
                t      = item['time']
                start  = t['start']
                sec = (1 if start < 120 else
                       2 if start < 168 else
                       3 if start < 192 else
                       4 if start < 216 else 5)
                self.result.append({
                    'day':         t['days_str'],
                    'section':     sec,
                    'course_name': item['course_id'],
                    'teacher':     ','.join(course['instructors']),
                    'room':        item['room_id'],
                    'type':        'primary'
                })
