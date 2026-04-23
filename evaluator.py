"""
评估单条路径及完整方案的成本，包含出发时间优化
"""
from scipy.optimize import minimize_scalar
from config import WAIT_COST_PER_HOUR, TARDY_COST_PER_HOUR, VEHICLE_TYPES
from cost_calculator import calculate_trip

def evaluate_route(route_custs, vtype, depart_time, customers, dist):
    """
    评估单条路径（不含始末0点），返回 (total_cost, detail_dict)
    """
    seq = [0] + route_custs + [0]
    t = depart_time
    cost = vtype.start_cost
    energy_cost = 0.0
    carbon_cost = 0.0
    penalty_cost = 0.0

    load = sum(customers[c-1]['demand_weight'] for c in route_custs)

    timeline = []
    for i in range(len(seq)-1):
        cur = seq[i]
        nxt = seq[i+1]
        load_ratio = load / vtype.cap_weight if vtype.cap_weight > 0 else 0
        trip = calculate_trip(cur, nxt, t, vtype, load_ratio, dist)
        energy_cost += trip['energy_cost']
        carbon_cost += trip['carbon_cost']
        t = trip['arrive_time']

        if nxt != 0:
            cust = customers[nxt-1]
            # 在客户节点，获取时间窗时直接使用紧缩时间窗
            if vtype.fuel_type == 'fuel':
                ready, due = cust.get('tw_fuel', (cust['ready_time'], cust['due_time']))
            else:
                ready, due = cust.get('tw_elec', (cust['ready_time'], cust['due_time']))

            # 检查该车型是否彻底不能服务此客户
            if ready < 0 and due < 0:
                return float('inf'), None

            arr = t
            if t < ready:
                wait = ready - t
                penalty_cost += wait * WAIT_COST_PER_HOUR
                t = ready + cust['service_time']
                timeline.append((nxt, arr, ready))
            elif t > due:
                tardiness = t - due
                penalty_cost += tardiness * TARDY_COST_PER_HOUR
                t = t + cust['service_time']
                timeline.append((nxt, arr, t - cust['service_time']))
            else:
                t = t + cust['service_time']
                timeline.append((nxt, arr, t - cust['service_time']))
            load -= cust['demand_weight']
        else:
            timeline.append((0, t, t))

    total = cost + energy_cost + carbon_cost + penalty_cost
    return total, {
        'start_cost': cost,
        'energy_cost': energy_cost,
        'carbon_cost': carbon_cost,
        'penalty_cost': penalty_cost,
        'timeline': timeline,
        'departure_time': depart_time
    }

def optimize_departure_time(route_custs, vtype, customers, dist):
    """ 通过一维搜索寻找最优出发时间，考虑燃油车可能需晚出发 """
    # 根据路径中客户可服务的最晚出发时间动态估算上界
    # 简单且安全：使用 [0, 10] 小时（即8:00-18:00），足够覆盖所有可能
    def f(dep):
        c, _ = evaluate_route(route_custs, vtype, dep, customers, dist)
        return c if c < float('inf') else 1e12

    res = minimize_scalar(f, bounds=(0.0, 10.0), method='bounded')
    best_dep = res.x
    best_cost, details = evaluate_route(route_custs, vtype, best_dep, customers, dist)
    details['departure_time'] = best_dep
    return best_cost, best_dep, details

def evaluate_solution(routes, customers, dist):
    total = 0.0
    route_details = []
    # 统计每种车型使用数量
    type_count = {vtype.id: 0 for vtype in VEHICLE_TYPES}
    for r in routes:
        vtype = r['vtype']
        type_count[vtype.id] += 1
        # 容量检查
        custs = r['customers']
        w = sum(customers[c-1]['demand_weight'] for c in custs)
        v = sum(customers[c-1]['demand_volume'] for c in custs)
        if w > vtype.cap_weight + 1e-6 or v > vtype.cap_volume + 1e-6:
            return float('inf'), None
    # 检查每类车数量上限
    penalty_excess = 0.0
    for vtype in VEHICLE_TYPES:
        if type_count[vtype.id] > vtype.count:
            excess = type_count[vtype.id] - vtype.count
            penalty_excess += excess * 100000.0  # 每超一辆罚10万

    for r in routes:
        vtype = r['vtype']
        custs = r['customers']
        cost, dep, det = optimize_departure_time(custs, vtype, customers, dist)
        total += cost
        det['vtype_name'] = vtype.name
        det['vtype'] = vtype
        det['customers'] = custs
        route_details.append(det)

    total += penalty_excess  # 加上超限罚款
    return total, route_details