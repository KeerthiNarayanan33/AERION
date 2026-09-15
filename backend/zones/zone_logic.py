import math
from typing import List, Tuple, Optional

Point = Tuple[float, float]
Polygon = List[Point]

def is_point_in_polygon(point: Point, polygon: Polygon) -> bool:
    """
    Determines if a point (x, y) is inside a polygon using the Ray-Casting algorithm.
    Works for both convex and concave non-self-intersecting polygons.
    """
    if len(polygon) < 3:
        return False

    px, py = point
    inside = False
    n = len(polygon)

    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]

        # Check if point is exactly on horizontal segment
        if p1y == p2y == py and min(p1x, p2x) <= px <= max(p1x, p2x):
            return True

        # Ray-casting check: does horizontal ray from (px, py) to (+inf, py) intersect edge?
        if min(p1y, p2y) < py <= max(p1y, p2y):
            if p1y != p2y:
                # X coordinate of the intersection
                x_inters = (py - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                if px <= x_inters:
                    inside = not inside

        p1x, p1y = p2x, p2y

    return inside

def point_to_segment_distance(point: Point, seg_start: Point, seg_end: Point) -> float:
    """Computes the shortest Euclidean distance from a point to a line segment."""
    px, py = point
    x1, y1 = seg_start
    x2, y2 = seg_end

    dx = x2 - x1
    dy = y2 - y1

    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)

    # Projection factor t of point onto line segment [0, 1]
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))

    nearest_x = x1 + t * dx
    nearest_y = y1 + t * dy

    return math.hypot(px - nearest_x, py - nearest_y)

def distance_to_polygon(point: Point, polygon: Polygon) -> float:
    """
    Computes minimum Euclidean distance from a point to the polygon boundary.
    If point is inside the polygon, returns 0.0.
    """
    if len(polygon) < 3:
        return float('inf')

    if is_point_in_polygon(point, polygon):
        return 0.0

    min_dist = float('inf')
    n = len(polygon)
    for i in range(n):
        seg_start = polygon[i]
        seg_end = polygon[(i + 1) % n]
        d = point_to_segment_distance(point, seg_start, seg_end)
        if d < min_dist:
            min_dist = d

    return min_dist

def is_vector_approaching_polygon(
    point: Point,
    velocity: Tuple[float, float],
    polygon: Polygon,
    threshold: float = 0.08
) -> bool:
    """
    Checks if a point outside a polygon is approaching it.
    Condition: point is within `threshold` distance of polygon,
    and velocity vector points toward the polygon interior.
    """
    dist_now = distance_to_polygon(point, polygon)
    if dist_now == 0.0 or dist_now > threshold:
        return False

    vx, vy = velocity
    speed = math.hypot(vx, vy)
    if speed < 1e-4:
        return False

    # Predict position shortly into future (dt = 0.2s or normalized scale)
    step = 0.05 / speed  # Normalized step
    next_pos = (point[0] + vx * step, point[1] + vy * step)
    dist_next = distance_to_polygon(next_pos, polygon)

    return dist_next < dist_now
