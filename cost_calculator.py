"""
时变速度下的单次行驶成本计算
"""
from config import TIME_PERIODS, LATE_PERIOD_SPEED, CARBON_PRICE

def get_speed_period(t):
    """ 返回 (速度均值 km/h, 本时段结束时间) """
    for start, end, speed in TIME_PERIODS:
        if start <= t < end:
            return speed, end
    return LATE_PERIOD_SPEED, float('inf')

def calculate_trip(start, end, depart_time, vtype, load_ratio, dist_matrix):
    """
    计算一次行驶的成本和到达时刻
    """
    d = dist_matrix[start][end]
    t = depart_time
    d_remain = d
    total_energy = 0.0
    total_carbon = 0.0

    while d_remain > 1e-6:
        speed, period_end = get_speed_period(t)
        dt_max = period_end - t
        if dt_max <= 0:
            continue
        d_possible = speed * dt_max
        if d_possible >= d_remain:
            # 本段内可行驶完，更新 t 和剩余距离
            t += d_remain / speed
            d_used = d_remain
            d_remain = 0
        else:
            d_used = d_possible
            t = period_end
            d_remain -= d_possible

        # 能耗计算
        e100_empty = vtype.energy_func(speed)
        e100_actual = e100_empty * (1 + vtype.beta_full * load_ratio)
        seg_energy = (d_used / 100.0) * e100_actual
        total_energy += seg_energy
        total_carbon += seg_energy * vtype.carbon_factor()

    arrive_time = t
    energy_cost = total_energy * vtype.energy_price()
    carbon_cost = total_carbon * CARBON_PRICE
    return {
        'arrive_time': arrive_time,
        'travel_time': arrive_time - depart_time,
        'energy_consumed': total_energy,
        'carbon_emission': total_carbon,
        'energy_cost': energy_cost,
        'carbon_cost': carbon_cost,
        'total_trip_cost': energy_cost + carbon_cost
    }