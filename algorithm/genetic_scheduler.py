"""
algorithm/genetic_scheduler.py
================================
基于 DEAP 的 NSGA-II 多目标排课算法（参考 pythonProject1/NSGA.py）。

三个优化目标（全部最小化）：
  f1 = 硬约束违规数（教室容量超限 + 教室可用性掩码 + 教师分身 + 教室时间冲突）
  f2 = 教师/教室偏好惩罚分
  f3 = 学生选课冲突数
"""

import random
import threading
import time
import numpy as np
from deap import base, creator, tools, algorithms


# ── DEAP 全局类型（只注册一次）────────────────────────────────
if not hasattr(creator, 'FitnessMulti'):
    creator.create('FitnessMulti', base.Fitness, weights=(-1.0, -1.0, -1.0))
if not hasattr(creator, 'Individual'):
    creator.create('Individual', list, fitness=creator.FitnessMulti)


# ---------------------------------------------------------------------------
# 核心调度器
# ---------------------------------------------------------------------------

class XMLBasedScheduler:
    """从数据库加载数据 + DEAP NSGA-II 多目标排课算法"""

    def __init__(self, data_dict=None, progress_callback=None, stop_event=None, **kwargs):
        self.progress_callback = progress_callback
        self.stop_event = stop_event

        # GA 参数
        self.population_size = int(kwargs.get('population_size', 100))
        self.generations     = int(kwargs.get('generations', 100))
        self.crossover_rate  = float(kwargs.get('crossover_rate', 0.7))
        self.mutation_rate   = float(kwargs.get('mutation_rate', 0.2))

        # 数据
        self.classes     = []   # [(class_id, class_limit, instructor_id, offering_id), ...]
        self.rooms_dict  = {}   # {room_id: {'cap': int, 'pattern': str}}
        self.room_ids    = []
        self.time_slots  = list(range(1, 101))
        self.prefs       = {}   # {class_id: [(target_val, pref_score), ...]}
        self.student_reqs = {}  # {student_id: [class_id, ...]}

        if data_dict:
            self._load_from_dict(data_dict)

    # ------------------------------------------------------------------
    # 数据加载（从 7 表结构字典）
    # ------------------------------------------------------------------

    def _load_from_dict(self, d):
        """从字典加载（字典由 app.py 从数据库查询后构建）"""
        self.classes = d.get('classes', [])
        rooms = d.get('rooms', [])
        self.rooms_dict = {r['room_id']: {'cap': r['capacity'], 'pattern': r.get('availability_pattern')}
                           for r in rooms}
        self.room_ids = list(self.rooms_dict.keys())
        self.prefs = d.get('prefs', {})
        self.student_reqs = d.get('student_reqs', {})

    # ------------------------------------------------------------------
    # DEAP 工具箱配置
    # ------------------------------------------------------------------

    def _build_toolbox(self):
        toolbox = base.Toolbox()

        classes = self.classes
        room_ids = self.room_ids
        time_slots = self.time_slots

        def create_gene():
            return {'time': random.choice(time_slots), 'room': random.choice(room_ids)}

        toolbox.register('individual', tools.initRepeat,
                         creator.Individual, create_gene, n=len(classes))
        toolbox.register('population', tools.initRepeat, list, toolbox.individual)
        toolbox.register('evaluate', self._evaluate)
        toolbox.register('mate', tools.cxTwoPoint)
        toolbox.register('mutate', self._mutate)
        toolbox.register('select', tools.selNSGA2)
        return toolbox

    # ------------------------------------------------------------------
    # 评估函数（对应 pythonProject1/NSGA.py evaluate()）
    # ------------------------------------------------------------------

    def _evaluate(self, individual):
        hard_violations = 0
        pref_penalty = 0.0
        student_conflicts = 0
        inst_time_map = {}
        room_time_map = {}
        class_schedule = {}

        for i, gene in enumerate(individual):
            c_id, c_limit, inst_id, o_id = self.classes[i]
            t = gene['time']
            r = gene['room']
            class_schedule[c_id] = t

            # A. 硬约束
            # 1. 教室容量
            if c_limit > self.rooms_dict[r]['cap']:
                hard_violations += 1

            # 2. 教室可用性掩码
            pattern = self.rooms_dict[r]['pattern']
            if pattern and t <= len(pattern):
                if pattern[t - 1] == 'X':
                    hard_violations += 1

            # 3. 教师分身冲突
            if inst_id:
                if (inst_id, t) in inst_time_map:
                    hard_violations += 1
                inst_time_map[(inst_id, t)] = True

            # 4. 教室时间冲突
            if (r, t) in room_time_map:
                hard_violations += 1
            room_time_map[(r, t)] = True

            # B. 软偏好惩罚
            if c_id in self.prefs:
                for target, score in self.prefs[c_id]:
                    if str(r) != str(target) and str(t) != str(target):
                        pref_penalty += score

        # C. 学生选课冲突
        for s_id, req_classes in self.student_reqs.items():
            times = [class_schedule[cid] for cid in req_classes if cid in class_schedule]
            student_conflicts += len(times) - len(set(times))

        # 硬约束不满足时，软目标加大惩罚
        if hard_violations > 0:
            pref_penalty += 10000
            student_conflicts += 10000

        return hard_violations, pref_penalty, student_conflicts

    # ------------------------------------------------------------------
    # 变异算子
    # ------------------------------------------------------------------

    def _mutate(self, individual):
        idx = random.randrange(len(individual))
        individual[idx] = {
            'time': random.choice(self.time_slots),
            'room': random.choice(self.room_ids)
        }
        return (individual,)

    # ------------------------------------------------------------------
    # 主进化循环
    # ------------------------------------------------------------------

    def run(self):
        if not self.classes or not self.room_ids:
            return None

        toolbox = self._build_toolbox()
        random.seed(42)

        pop = toolbox.population(n=self.population_size)
        history = {'gen': [], 'min_hard': [], 'avg_hard': [], 'min_pref': [], 'min_student': []}

        # 评估初始种群
        fitnesses = list(map(toolbox.evaluate, pop))
        for ind, fit in zip(pop, fitnesses):
            ind.fitness.values = fit

        best_individual = None
        best_f1 = float('inf')

        for gen in range(self.generations):
            if self.stop_event and self.stop_event.is_set():
                break

            offspring = algorithms.varAnd(pop, toolbox,
                                          cxpb=self.crossover_rate,
                                          mutpb=self.mutation_rate)
            invalid = [ind for ind in offspring if not ind.fitness.valid]
            fits = list(map(toolbox.evaluate, invalid))
            for ind, fit in zip(invalid, fits):
                ind.fitness.values = fit

            pop = toolbox.select(pop + offspring, k=self.population_size)

            all_fits = np.array([ind.fitness.values for ind in pop])
            min_hard = float(np.min(all_fits[:, 0]))
            avg_hard = float(np.mean(all_fits[:, 0]))

            valid_fits = all_fits[all_fits[:, 0] == 0]
            min_pref    = float(np.min(valid_fits[:, 1])) if len(valid_fits) > 0 else float(np.min(all_fits[:, 1]))
            min_student = float(np.min(valid_fits[:, 2])) if len(valid_fits) > 0 else float(np.min(all_fits[:, 2]))

            history['gen'].append(gen)
            history['min_hard'].append(min_hard)
            history['avg_hard'].append(avg_hard)
            history['min_pref'].append(min_pref)
            history['min_student'].append(min_student)

            # 追踪最优个体
            for ind in pop:
                f = ind.fitness.values
                if f[0] < best_f1 or (f[0] == best_f1 and best_individual is None):
                    best_f1 = f[0]
                    best_individual = list(ind)

            # 进度回调
            if self.progress_callback:
                best_fit = min(all_fits, key=lambda x: (x[0], x[1] + x[2]))
                self.progress_callback({
                    'generation':       gen + 1,
                    'hard_conflicts':   int(best_fit[0]),
                    'soft_score':       round(-(best_fit[1] + best_fit[2]), 2),
                    'f1':               best_fit[0],
                    'f2':               round(float(best_fit[1]), 4),
                    'f3':               round(float(best_fit[2]), 4),
                    'status':           'RUNNING',
                    'progress_percent': int((gen / self.generations) * 100),
                    'pareto_front':     []
                })

            time.sleep(0.001)

        return best_individual, self.classes


# ---------------------------------------------------------------------------
# Flask 服务包装层
# ---------------------------------------------------------------------------

class GeneticScheduler:
    def __init__(self):
        self.data         = {'tasks': [], 'classes': [], 'teachers': [], 'courses': []}
        self.result       = []
        self.progress     = {
            'status': 'IDLE', 'generation': 0,
            'hard_conflicts': 0, 'soft_score': 0,
            'f1': 0, 'f2': 0, 'f3': 0,
            'progress_percent': 0, 'history': [],
            'pareto_history': []
        }
        self.stop_event   = threading.Event()
        self._data_dict   = None   # 保存最近一次加载的数据字典
        self.algorithm    = None

    def load_from_memory(self, data_dict):
        """从字典加载（字典由 app.py 从数据库构建）"""
        self._data_dict = data_dict
        self.algorithm  = XMLBasedScheduler(data_dict=data_dict)
        self._update_stats()

    def _update_stats(self):
        algo = self.algorithm
        tasks = [{'classId': c[0], 'courseName': c[0],
                  'teacher': c[2] or '', 'students': c[1]}
                 for c in algo.classes]
        self.data = {
            'tasks':    tasks,
            'classes':  [c[0] for c in algo.classes],
            'teachers': list({c[2] for c in algo.classes if c[2]}),
            'courses':  [c[0] for c in algo.classes]
        }

    def get_data(self):     return self.data
    def get_result(self):   return self.result
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

        self.algorithm = XMLBasedScheduler(
            data_dict=self._data_dict,
            progress_callback=on_progress,
            stop_event=self.stop_event,
            **params
        )

        result = self.algorithm.run()

        if not self.stop_event.is_set():
            self.progress['status']           = 'COMPLETED'
            self.progress['progress_percent'] = 100

        # 转换结果格式（兼容前端展示）
        self.result = []
        if result:
            best_individual, classes = result
            # 时间槽 1-100 映射到 5 天 × 5 节次（每 20 个槽为一天）
            for i, gene in enumerate(best_individual):
                c_id, c_limit, inst_id, o_id = classes[i]
                t = gene['time']
                day_idx = (t - 1) // 20          # 0~4 对应周一~周五
                sec     = ((t - 1) % 20) // 4 + 1  # 1~5 节
                days_map = ['0100000', '0010000', '0001000', '0000100', '0000010']
                day_str  = days_map[min(day_idx, 4)]
                self.result.append({
                    'day':         day_str,
                    'section':     sec,
                    'course_name': c_id,
                    'teacher':     inst_id or '',
                    'room':        gene['room'],
                    'type':        'primary'
                })
