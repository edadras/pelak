def point_in_polygon(x, y, poly):
    """Ray casting; poly is a list of (x, y)."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
            inside = not inside
        j = i
    return inside


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter <= 0:
        return 0.0
    area = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / area if area > 0 else 0.0


def side_of_line(p, a, b):
    """Sign of the cross product: which side of segment a->b the point p is on."""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def segments_cross(p1, p2, a, b):
    """True if the movement p1->p2 crosses segment a-b."""
    d1, d2 = side_of_line(p1, a, b), side_of_line(p2, a, b)
    if d1 == 0 or d2 == 0 or (d1 > 0) == (d2 > 0):
        return False
    d3, d4 = side_of_line(a, p1, p2), side_of_line(b, p1, p2)
    return (d3 > 0) != (d4 > 0)
