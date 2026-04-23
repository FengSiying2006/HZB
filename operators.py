"""
ALNS 使用的破坏（removal）与修复（insertion）算子
包含问题2的车型-客户兼容性检查（绿色区限行）
"""
import random
from evaluator import evaluate_route
from config import VEHICLE_TYPES

def random_removal(routes, num_remove):
    """ 随机移除客户 """
    all_custs = []
    for ri, r in enumerate(routes):
        for ci, c in enumerate(r['customers']):
            all_custs.append((ri, ci, c))
    if not all_custs:
        return routes, []
    num = min(num_remove, len(all_custs))
    chosen = random.sample(all_custs, num)
    for ri, ci, _ in sorted(chosen, key=lambda x: (x[0], x[1]), reverse=True):
        del routes[ri]['customers'][ci]
    removed = [c for _, _, c in chosen]
    routes = [r for r in routes if len(r['customers']) > 0]
    return routes, removed

def worst_removal(routes, num_remove, customers, dist):
    """ 移除使得路径成本降低最大的客户（节约原则） """
    savings = []
    for ri, r in enumerate(routes):
        vtype = r['vtype']
        for ci, c in enumerate(r['customers']):
            route_without = r['customers'][:ci] + r['customers'][ci+1:]
            if not route_without:
                cost_with, _ = evaluate_route(r['customers'], vtype, 0.0, customers, dist)
                savings.append((ri, ci, c, cost_with - vtype.start_cost))
            else:
                cost_before, _ = evaluate_route(r['customers'], vtype, 0.0, customers, dist)
                cost_after, _ = evaluate_route(route_without, vtype, 0.0, customers, dist)
                savings.append((ri, ci, c, cost_before - cost_after))
    savings.sort(key=lambda x: x[3], reverse=True)
    remove_set = set()
    removed = []
    for ri, ci, c, _ in savings:
        if len(removed) >= num_remove:
            break
        if c not in remove_set:
            remove_set.add(c)
            removed.append(c)
            del routes[ri]['customers'][ci]
    routes = [r for r in routes if len(r['customers']) > 0]
    return routes, removed

def _can_serve(vtype, cust):
    """ 检查某车型能否服务给定的客户（考虑绿色区） """
    if vtype.fuel_type == 'fuel':
        ready, due = cust.get('tw_fuel', (cust['ready_time'], cust['due_time']))
    else:
        ready, due = cust.get('tw_elec', (cust['ready_time'], cust['due_time']))
    return not (ready < 0 and due < 0)

def greedy_insert(routes, removed_custs, customers, dist):
    """ 贪心插入法，跳过不兼容的车型 """
    # 统计当前各车型使用数量
    type_count = {vtype.id: 0 for vtype in VEHICLE_TYPES}
    for r in routes:
        type_count[r['vtype'].id] += 1

    for c in removed_custs:
        best_delta = float('inf')
        best_dest = None
        for ri, r in enumerate(routes):
            vtype = r['vtype']
            cust = customers[c-1]
            if not _can_serve(vtype, cust):
                continue
            for pos in range(len(r['customers'])+1):
                new_route = r['customers'][:pos] + [c] + r['customers'][pos:]
                w = sum(customers[x-1]['demand_weight'] for x in new_route)
                vol = sum(customers[x-1]['demand_volume'] for x in new_route)
                if w > vtype.cap_weight + 1e-6 or vol > vtype.cap_volume + 1e-6:
                    continue
                cost_before, _ = evaluate_route(r['customers'], vtype, 0.0, customers, dist) if r['customers'] else (0, None)
                cost_after, _ = evaluate_route(new_route, vtype, 0.0, customers, dist)
                delta = cost_after - (cost_before if r['customers'] else vtype.start_cost)
                if delta < best_delta:
                    best_delta = delta
                    best_dest = ('existing', ri, pos)
        # 新建路径
        for tid, vtype in enumerate(VEHICLE_TYPES):
            cust = customers[c-1]
            if not _can_serve(vtype, cust):
                continue
            if type_count.get(vtype.id, 0) >= vtype.count:
                continue
            if cust['demand_weight'] > vtype.cap_weight or cust['demand_volume'] > vtype.cap_volume:
                continue
            new_route = [c]
            cost_new, _ = evaluate_route(new_route, vtype, 0.0, customers, dist)
            if cost_new < best_delta:
                best_delta = cost_new
                best_dest = ('new', tid)
        if best_dest is None:
            # 极端情况：无法插入，强制新建一条允许的车型路径（即使超限也要尝试，会在评估时剔除）
            # 寻找任一可服务的车型（忽略数量限制）
            for tid, vtype in enumerate(VEHICLE_TYPES):
                if _can_serve(vtype, customers[c-1]) and \
                   customers[c-1]['demand_weight'] <= vtype.cap_weight and \
                   customers[c-1]['demand_volume'] <= vtype.cap_volume:
                    best_dest = ('new', tid)
                    break
            if best_dest is None:
                continue   # 放弃该客户
        if best_dest[0] == 'new':
            vtype = VEHICLE_TYPES[best_dest[1]]
            routes.append({'vtype': vtype, 'customers': [c]})
            type_count[vtype.id] += 1
        else:
            ri, pos = best_dest[1], best_dest[2]
            routes[ri]['customers'].insert(pos, c)
    return routes

def regret2_insert(routes, removed_custs, customers, dist):
    """ Regret-2 插入法，考虑兼容性 """
    type_count = {vtype.id: 0 for vtype in VEHICLE_TYPES}
    for r in routes:
        type_count[r['vtype'].id] += 1

    while removed_custs:
        regrets = []
        for c in removed_custs:
            best_vals = []
            # 已有路径
            for ri, r in enumerate(routes):
                vtype = r['vtype']
                cust = customers[c-1]
                if not _can_serve(vtype, cust):
                    continue
                for pos in range(len(r['customers'])+1):
                    new_route = r['customers'][:pos] + [c] + r['customers'][pos:]
                    w = sum(customers[x-1]['demand_weight'] for x in new_route)
                    vol = sum(customers[x-1]['demand_volume'] for x in new_route)
                    if w > vtype.cap_weight + 1e-6 or vol > vtype.cap_volume + 1e-6:
                        continue
                    cost_after, _ = evaluate_route(new_route, vtype, 0.0, customers, dist)
                    base = evaluate_route(r['customers'], vtype, 0.0, customers, dist)[0] if r['customers'] else vtype.start_cost
                    delta = cost_after - base
                    best_vals.append((delta, ('existing', ri, pos)))
            # 新建路径
            for tid, vtype in enumerate(VEHICLE_TYPES):
                cust = customers[c-1]
                if not _can_serve(vtype, cust):
                    continue
                if type_count.get(vtype.id, 0) >= vtype.count:
                    continue
                if cust['demand_weight'] > vtype.cap_weight or cust['demand_volume'] > vtype.cap_volume:
                    continue
                cost_new, _ = evaluate_route([c], vtype, 0.0, customers, dist)
                best_vals.append((cost_new, ('new', tid)))
            best_vals.sort(key=lambda x: x[0])
            if len(best_vals) >= 2:
                regret = best_vals[1][0] - best_vals[0][0]
            else:
                regret = best_vals[0][0] if best_vals else float('inf')
            if best_vals:
                regrets.append((c, best_vals[0][1], regret))
        if not regrets:
            break
        regrets.sort(key=lambda x: x[2], reverse=True)
        c, dest, _ = regrets[0]
        removed_custs.remove(c)
        if dest[0] == 'new':
            vtype = VEHICLE_TYPES[dest[1]]
            routes.append({'vtype': vtype, 'customers': [c]})
            type_count[vtype.id] += 1
        else:
            ri, pos = dest[1], dest[2]
            routes[ri]['customers'].insert(pos, c)
    return routes