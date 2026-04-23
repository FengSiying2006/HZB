"""
全局常数、车辆类型、时段与速度定义
"""
# 问题选择：1 或 2
PROBLEM_ID = 2   # 运行时可被 main.py 覆盖

# 绿色配送区参数（问题2专用）
GREEN_ZONE_CENTER = (0.0, 0.0)    # 市中心
GREEN_ZONE_RADIUS = 10.0          # km
RESTRICTED_START = 0.0            # 8:00 (相对8:00为0)
RESTRICTED_END = 8.0              # 16:00 (相对8:00为8)

SERVICE_TIME = 20 / 60.0          # 小时
START_EARLIEST = 8.0             # 相对8:00为0
WAIT_COST_PER_HOUR = 20
TARDY_COST_PER_HOUR = 50
START_COST = 400
CARBON_PRICE = 0.65
FUEL_PRICE = 7.61
ELEC_PRICE = 1.64
FUEL_CARBON_FACTOR = 2.547    # kg/L
ELEC_CARBON_FACTOR = 0.501    # kg/kWh

# 时段划分 (相对8:00的小时, 速度均值 km/h)
TIME_PERIODS = [
    (0.0, 1.0, 9.8),    # 8:00-9:00 拥堵
    (1.0, 2.0, 55.3),   # 9:00-10:00 顺畅
    (2.0, 3.5, 35.4),   # 10:00-11:30 一般
    (3.5, 5.0, 9.8),    # 11:30-13:00 拥堵
    (5.0, 7.0, 55.3),   # 13:00-15:00 顺畅
    (7.0, 9.0, 35.4)    # 15:00-17:00 一般
]
LATE_PERIOD_SPEED = 35.4   # 17:00后延续一般速度

class VehicleType:
    def __init__(self, type_id, name, cap_weight, cap_volume, fuel_type, count,
                 energy_func, beta_full, start_cost=400):
        self.id = type_id
        self.name = name
        self.cap_weight = cap_weight        # kg
        self.cap_volume = cap_volume        # m³
        self.fuel_type = fuel_type           # 'fuel' or 'electric'
        self.count = count                   # 可用数量
        self.energy_func = energy_func       # 空载百公里能耗函数
        self.beta_full = beta_full           # 满载能耗增加比例
        self.start_cost = start_cost

    def energy_price(self):
        return FUEL_PRICE if self.fuel_type == 'fuel' else ELEC_PRICE

    def carbon_factor(self):
        return FUEL_CARBON_FACTOR if self.fuel_type == 'fuel' else ELEC_CARBON_FACTOR

# 空载百公里能耗函数
def fpk(v):
    return 0.0025*v*v - 0.2554*v + 31.75

def epk(v):
    return 0.0014*v*v - 0.12*v + 36.19

# 五种车型定义
VEHICLE_TYPES = [
    VehicleType(0, "燃油3000", 3000, 13.5, 'fuel', 60, fpk, 0.40),
    VehicleType(1, "燃油1500", 1500, 10.8, 'fuel', 50, fpk, 0.40),
    VehicleType(2, "燃油1250", 1250, 6.5,  'fuel', 50, fpk, 0.40),
    VehicleType(3, "新能源3000", 3000, 15.0, 'electric', 10, epk, 0.35),
    VehicleType(4, "新能源1250", 1250, 8.5,  'electric', 15, epk, 0.35)
]

MAX_WEIGHT = max(v.cap_weight for v in VEHICLE_TYPES)
MAX_VOLUME = max(v.cap_volume for v in VEHICLE_TYPES)