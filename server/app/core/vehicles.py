"""Vehicle vocabulary shared by the vision pipeline, rules and UI."""

VEHICLE_TYPES = {
    "car": "سواری",
    "suv": "شاسی‌بلند",
    "taxi": "تاکسی",
    "pickup": "وانت",
    "van": "ون",
    "minibus": "مینی‌بوس",
    "bus": "اتوبوس",
    "light_truck": "کامیونت",
    "truck": "کامیون",
    "trailer": "تریلی",
    "motorcycle": "موتورسیکلت",
    "bicycle": "دوچرخه",
    "unknown": "نامشخص",
}
HEAVY_TYPES = {"bus", "minibus", "light_truck", "truck", "trailer"}
CARGO_TYPES = {"pickup", "light_truck", "truck", "trailer"}

COLORS = {
    "white": ("سفید", "#f8fafc"),
    "black": ("مشکی", "#111827"),
    "gray": ("نوک‌مدادی / طوسی", "#6b7280"),
    "silver": ("نقره‌ای", "#cbd5e1"),
    "red": ("قرمز", "#dc2626"),
    "orange": ("نارنجی", "#f97316"),
    "yellow": ("زرد", "#facc15"),
    "green": ("سبز", "#16a34a"),
    "blue": ("آبی", "#2563eb"),
    "brown": ("قهوه‌ای / بژ", "#92400e"),
    "unknown": ("نامشخص", "#94a3b8"),
}

EVENT_KINDS = {
    "passage": "عبور",
    "parking": "پارک حاشیه",
    "double_parking": "پارک دوبل",
    "stopped": "توقف در مسیر",
    "no_parking": "توقف در محل ممنوع",
}

VIOLATION_TYPES = {
    "speeding": "سرعت غیرمجاز",
    "restricted_area": "تردد در محدوده ممنوع",
    "restricted_time": "تردد در ساعت غیرمجاز",
    "no_permit": "ورود بدون مجوز طرح",
    "odd_even": "تخلف طرح زوج و فرد",
    "heavy_vehicle": "تردد خودرو سنگین",
    "loaded_vehicle": "تردد خودرو باردار",
    "double_parking": "پارک دوبل",
    "no_parking": "توقف در محل ممنوع",
    "stopped_in_lane": "توقف در مسیر عبور",
    "bus_lane": "تردد در خط ویژه",
    "watchlist": "خودرو تحت تعقیب",
}

ZONE_TYPES = {
    "curb_parking": "پارک حاشیه‌ای مجاز",
    "no_parking": "توقف ممنوع",
    "traffic_lane": "مسیر عبور (تشخیص دوبل)",
    "bus_lane": "خط ویژه اتوبوس",
    "detection": "ناحیه تشخیص",
}

WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]


def weekday_sat0(dt):
    """Python weekday (Mon=0) -> Iranian week index (Sat=0 .. Fri=6)."""
    return (dt.weekday() + 2) % 7
