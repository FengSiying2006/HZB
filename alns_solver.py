"""
自适应大邻域搜索 (ALNS) 主求解器
"""
import random
import math
from copy import deepcopy
from config import VEHICLE_TYPES
from evaluator import evaluate_route, evaluate_solution
from operators import random_removal, worst_removal, greedy_insert, regret2_insert

OPERATORS_DESTROY = ['random_removal', 'worst_removal']
OPERATORS_REPAIR = ['greedy_insert', 'regret2_insert']
WEIGHTS = {op: 1.0 for op in OPERATORS_DESTROY + OPERATORS_REPAIR}
COUNTS = {op: 0 for op in OPERATORS_DESTROY + OPERATORS_REPAIR}

def select_operator(op_list):
    total = sum(WEIGHTS[op] for op in op_list)
    rnd = random.random() * total
    accum = 0.0
    for op in op_list:
        accum += WEIGHTS[op]
        if rnd <= accum:
            return op
    return op_list[-1]

def update_weights(destroy, repair, improvement):
    delta = 0.1 * improvement
    for op in [destroy, repair]:
        WEIGHTS[op] = max(0.1, WEIGHTS[op] + delta)
        COUNTS[op] += 1
    if sum(COUNTS.values()) % 100 == 0:
        for op in WEIGHTS:
            WEIGHTS[op] *= 0.9

def _can_serve(vtype, cust):
    if vtype.fuel_type == 'fuel':
        ready, due = cust.get('tw_fuel', (cust['ready_time'], cust['due_time']))
    else:
        ready, due = cust.get('tw_elec', (cust['ready_time'], cust['due_time']))
    return not (ready < 0 and due < 0)


def construct_initial_solution(customers, dist):
    """ 带必须新能源客户优先分配和后备的初始解构造 """
    available = {tid: vtype.count for tid, vtype in enumerate(VEHICLE_TYPES)}
    routes = []
    unassigned = set(range(1, len(customers) + 1))

    # 识别必须由新能源服务的客户（绿区，且 tw_fuel 为 (-1,-1)）
    must_electric = []
    for cid in unassigned.copy():
        cust = customers[cid - 1]
        tf = cust.get('tw_fuel')
        if tf and tf[0] < 0 and tf[1] < 0:  # 燃油车不可服务
            must_electric.append(cid)
            unassigned.remove(cid)  # 临时移出，稍后统一分配

    # 用新能源车优先装载 must_electric 客户
    electric_order = [3, 4]  # 电动3000, 电动1250
    for cid in must_electric:
        inserted = False
        for tid in electric_order:
            if available[tid] == 0:
                continue
            vtype = VEHICLE_TYPES[tid]
            if customers[cid - 1]['demand_weight'] <= vtype.cap_weight and \
                    customers[cid - 1]['demand_volume'] <= vtype.cap_volume:
                # 新建一条只含此客户的路径（绿色区客户可能时间窗特殊，单独一车可灵活调整出发时间）
                routes.append({'vtype': vtype, 'customers': [cid]})
                available[tid] -= 1
                inserted = True
                break
        if not inserted:
            # 尝试插入现有新能源车路径
            best_insert = None
            best_cost = float('inf')
            for ri, r in enumerate(routes):
                vtype = r['vtype']
                if vtype.fuel_type != 'electric':
                    continue
                cust = customers[cid - 1]
                w = sum(customers[c - 1]['demand_weight'] for c in r['customers']) + cust['demand_weight']
                v = sum(customers[c - 1]['demand_volume'] for c in r['customers']) + cust['demand_volume']
                if w > vtype.cap_weight or v > vtype.cap_volume:
                    continue
                # 尝试所有插入位置，选最优
                for pos in range(len(r['customers']) + 1):
                    new_route = r['customers'][:pos] + [cid] + r['customers'][pos:]
                    cost, _ = evaluate_route(new_route, vtype, 0.0, customers, dist)
                    if cost < best_cost:
                        best_cost = cost
                        best_insert = (ri, pos)
            if best_insert:
                ri, pos = best_insert
                routes[ri]['customers'].insert(pos, cid)
            else:
                # 无法插入，尝试用非电动车型？不该发生，因为 must_electric 定义就是燃油不可服务
                # 退而求其次，强行用电动3000车型（如果满，忽略数量限制）
                # 只要可用数量总和允许，我们选择一种电动车型新建
                for tid in electric_order:
                    vtype = VEHICLE_TYPES[tid]
                    if customers[cid - 1]['demand_weight'] <= vtype.cap_weight and \
                            customers[cid - 1]['demand_volume'] <= vtype.cap_volume:
                        routes.append({'vtype': vtype, 'customers': [cid]})
                        # 不递减 available，因为我们突破限制，但会由评估罚款处理
                        break
                else:
                    # 彻底失败，强行用燃油3000，将在评估中产生 inf（但 must_electric 的 tw_fuel 是 -1，所以会 inf）
                    routes.append({'vtype': VEHICLE_TYPES[0], 'customers': [cid]})

    # 将之前移出的必须电动客户加回 unassigned 吗？不，它们已分配，unassigned 中应不包含它们
    # unassigned 已经移除了 must_electric，但还需包含未处理的普通客户
    # 注意原循环中我们直接从 unassigned 移除了 must_electric，剩余 unassigned 是普通客户

    # 常规贪心构造剩余客户（与之前相同，但使用原始时间窗评估）
    order = [3, 0, 1, 4, 2]  # 车型顺序
    while unassigned:
        best_route = None
        best_cost = float('inf')
        best_vtype = None
        for tid in order:
            if available[tid] <= 0:  # 注意 available 可能被电动已用，所以改为 <= 0
                continue
            vtype = VEHICLE_TYPES[tid]
            route_custs = []
            remaining = set(unassigned)
            while remaining:
                best_insert = None
                best_insert_cost = float('inf')
                for c in remaining:
                    cust = customers[c - 1]
                    if not _can_serve(vtype, cust):
                        continue
                    w = sum(customers[i - 1]['demand_weight'] for i in route_custs) + cust['demand_weight']
                    vol = sum(customers[i - 1]['demand_volume'] for i in route_custs) + cust['demand_volume']
                    if w > vtype.cap_weight or vol > vtype.cap_volume:
                        continue
                    temp_route = route_custs + [c]
                    cost, _ = evaluate_route(temp_route, vtype, 0.0, customers, dist)
                    if cost < best_insert_cost:
                        best_insert_cost = cost
                        best_insert = c
                if best_insert is not None:
                    route_custs.append(best_insert)
                    remaining.remove(best_insert)
                else:
                    break
            if route_custs:
                cost, _ = evaluate_route(route_custs, vtype, 0.0, customers, dist)
                if cost < best_cost:
                    best_cost = cost
                    best_route = route_custs
                    best_vtype = vtype
        if best_route is None:
            break
        routes.append({'vtype': best_vtype, 'customers': best_route})
        unassigned -= set(best_route)
        available[best_vtype.id] -= 1

    # 如果还剩余普通客户，则采用单客户路径后备
    if unassigned:
        print(f"警告: 贪心构造后有 {len(unassigned)} 个客户未分配，使用单客户路径后备。")
        for c in unassigned:
            assigned = False
            for tid in order:
                vtype = VEHICLE_TYPES[tid]
                if _can_serve(vtype, customers[c - 1]) and \
                        customers[c - 1]['demand_weight'] <= vtype.cap_weight and \
                        customers[c - 1]['demand_volume'] <= vtype.cap_volume:
                    routes.append({'vtype': vtype, 'customers': [c]})
                    assigned = True
                    break
            if not assigned:
                # 实在不行，用电动 3000 新建，可能数量超限，但由评估惩罚处理
                vtype = VEHICLE_TYPES[3] if customers[c - 1]['demand_weight'] <= 3000 and \
                                            customers[c - 1]['demand_volume'] <= 15.0 else VEHICLE_TYPES[0]
                routes.append({'vtype': vtype, 'customers': [c]})
    return routes

def alns_solve(customers, dist, max_iter=500, init_temp=100, cooling_rate=0.9995,
               num_remove_min=1, num_remove_ratio=0.15):
    routes = construct_initial_solution(customers, dist)
    current_cost, _ = evaluate_solution(routes, customers, dist)
    best_routes = deepcopy(routes)
    best_cost = current_cost
    T = init_temp
    num_remove_max = max(1, int(len(customers)*num_remove_ratio))

    print(f"初始解成本: {current_cost:.2f}, 使用车辆: {len(routes)}")
    for it in range(max_iter):
        destroy_op = select_operator(OPERATORS_DESTROY)
        repair_op = select_operator(OPERATORS_REPAIR)
        num = random.randint(num_remove_min, min(num_remove_max, sum(len(r['customers']) for r in routes)))

        if destroy_op == 'random_removal':
            new_routes, removed = random_removal(deepcopy(routes), num)
        else:
            new_routes, removed = worst_removal(deepcopy(routes), num, customers, dist)
        if not removed:
            continue

        if repair_op == 'greedy_insert':
            new_routes = greedy_insert(new_routes, removed, customers, dist)
        else:
            new_routes = regret2_insert(new_routes, removed, customers, dist)

        new_cost, _ = evaluate_solution(new_routes, customers, dist)
        improvement = current_cost - new_cost
        accept = False
        if new_cost < current_cost:
            accept = True
        elif T > 0.01 and random.random() < math.exp(improvement / T):
            accept = True

        if accept:
            routes = new_routes
            current_cost = new_cost
            update_weights(destroy_op, repair_op, max(0, improvement))
            if new_cost < best_cost:
                best_routes = deepcopy(new_routes)
                best_cost = new_cost
        T *= cooling_rate

        if it % 50 == 0:
            print(f"  Iter {it}: curr={current_cost:.2f}, best={best_cost:.2f}, T={T:.3f}")

    return best_routes, best_cost