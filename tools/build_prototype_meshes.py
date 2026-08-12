from __future__ import annotations

import collections
import math
import struct
import sys
from pathlib import Path

import numpy as np

from inspect_stl import load_binary_stl


TARGET_LENGTH_MM = 150.0
SEAM_HALF_GAP_MM = 0.20
CAVITY_CENTER_X_MM = -7.0
CAVITY_CENTER_Z_MM = -2.0
CAVITY_RADIUS_X_MM = 40.0
CAVITY_RADIUS_Z_MM = 21.0
WALL_THICKNESS_MM = 3.0


def largest_component(triangles: np.ndarray) -> np.ndarray:
    vertices = triangles.reshape(-1, 3)
    scale = max(float(np.ptp(vertices, axis=0).max()), 1.0)
    quantized = np.round(vertices / (scale * 1e-7)).astype(np.int64)
    _, inverse = np.unique(quantized, axis=0, return_inverse=True)
    faces = inverse.reshape(-1, 3)
    vertex_faces: dict[int, list[int]] = collections.defaultdict(list)
    for face_index, face in enumerate(faces):
        for vertex_index in face:
            vertex_faces[int(vertex_index)].append(face_index)

    parent = list(range(len(faces)))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for linked in vertex_faces.values():
        for other in linked[1:]:
            union(linked[0], other)

    groups: dict[int, list[int]] = collections.defaultdict(list)
    for face_index in range(len(faces)):
        groups[find(face_index)].append(face_index)
    selected = max(groups.values(), key=len)
    return triangles[np.asarray(selected)]


def interpolate_to_plane(a: np.ndarray, b: np.ndarray, axis: int, plane: float) -> np.ndarray:
    amount = (plane - a[axis]) / (b[axis] - a[axis])
    point = a + amount * (b - a)
    point[axis] = plane
    return point


def clip_half(
    triangles: np.ndarray, axis: int, plane: float, keep_positive: bool
) -> tuple[np.ndarray, list[tuple[np.ndarray, np.ndarray]]]:
    output: list[np.ndarray] = []
    segments: list[tuple[np.ndarray, np.ndarray]] = []
    epsilon = 1e-9

    def inside(point: np.ndarray) -> bool:
        signed = point[axis] - plane
        return signed >= -epsilon if keep_positive else signed <= epsilon

    for triangle in triangles:
        polygon = [point.copy() for point in triangle]
        clipped: list[np.ndarray] = []
        intersections: list[np.ndarray] = []
        for index, current in enumerate(polygon):
            previous = polygon[index - 1]
            current_inside = inside(current)
            previous_inside = inside(previous)
            if current_inside != previous_inside:
                intersection = interpolate_to_plane(previous, current, axis, plane)
                clipped.append(intersection)
                intersections.append(intersection)
            if current_inside:
                clipped.append(current)
        if len(clipped) >= 3:
            for index in range(1, len(clipped) - 1):
                output.append(np.array([clipped[0], clipped[index], clipped[index + 1]]))
        if len(intersections) == 2 and not np.allclose(intersections[0], intersections[1]):
            segments.append((intersections[0], intersections[1]))
    return np.asarray(output), segments


def ordered_loops(segments: list[tuple[np.ndarray, np.ndarray]], tolerance: float = 1e-5) -> list[np.ndarray]:
    points: dict[tuple[int, int, int], np.ndarray] = {}
    adjacency: dict[tuple[int, int, int], list[tuple[int, int, int]]] = collections.defaultdict(list)

    def key(point: np.ndarray) -> tuple[int, int, int]:
        return tuple(np.round(point / tolerance).astype(np.int64).tolist())

    for left, right in segments:
        a, b = key(left), key(right)
        if a == b:
            continue
        points.setdefault(a, left)
        points.setdefault(b, right)
        if b not in adjacency[a]:
            adjacency[a].append(b)
        if a not in adjacency[b]:
            adjacency[b].append(a)

    unused = {tuple(sorted((a, b))) for a, neighbors in adjacency.items() for b in neighbors}
    loops: list[np.ndarray] = []
    while unused:
        edge = next(iter(unused))
        start, current = edge
        previous = start
        path = [start, current]
        unused.discard(tuple(sorted((start, current))))
        while current != start:
            candidates = [node for node in adjacency[current] if node != previous]
            if not candidates:
                raise ValueError("Open contour encountered while splitting mesh")
            following = next(
                (node for node in candidates if tuple(sorted((current, node))) in unused),
                candidates[0],
            )
            previous, current = current, following
            if current != start:
                path.append(current)
            unused.discard(tuple(sorted((previous, current))))
            if len(path) > len(points) + 2:
                raise ValueError("Contour traversal did not close")
        loops.append(np.asarray([points[node] for node in path]))
    return loops


def signed_area_xz(loop: np.ndarray) -> float:
    x = loop[:, 0]
    z = loop[:, 2]
    return 0.5 * float(np.sum(x * np.roll(z, -1) - np.roll(x, -1) * z))


def rotate_start(loop: np.ndarray) -> np.ndarray:
    # Match the outer contour and cavity ring at their right-most points.
    index = int(np.argmax(loop[:, 0] - 1e-4 * np.abs(loop[:, 2] - CAVITY_CENTER_Z_MM)))
    return np.roll(loop, -index, axis=0)


def normalized_perimeter(loop: np.ndarray) -> np.ndarray:
    closed = np.vstack([loop, loop[0]])
    lengths = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    total = float(lengths.sum())
    return np.concatenate([[0.0], np.cumsum(lengths)[:-1]]) / total


def orient_triangle(triangle: np.ndarray, desired_y: float) -> np.ndarray:
    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    if normal[1] * desired_y < 0:
        return triangle[[0, 2, 1]]
    return triangle


def annulus_triangles(outer: np.ndarray, inner: np.ndarray, desired_y: float) -> np.ndarray:
    if signed_area_xz(outer) < 0:
        outer = outer[::-1]
    if signed_area_xz(inner) < 0:
        inner = inner[::-1]
    outer = rotate_start(outer)
    inner = rotate_start(inner)
    outer_t = normalized_perimeter(outer)
    inner_t = normalized_perimeter(inner)
    triangles: list[np.ndarray] = []
    i = j = 0
    outer_count, inner_count = len(outer), len(inner)
    while i < outer_count or j < inner_count:
        outer_next = (outer_t[(i + 1) % outer_count] if i + 1 < outer_count else 1.0)
        inner_next = (inner_t[(j + 1) % inner_count] if j + 1 < inner_count else 1.0)
        oi = outer[i % outer_count]
        ij = inner[j % inner_count]
        if i < outer_count and (j >= inner_count or outer_next <= inner_next):
            triangle = np.array([oi, outer[(i + 1) % outer_count], ij])
            i += 1
        else:
            triangle = np.array([oi, inner[(j + 1) % inner_count], ij])
            j += 1
        triangles.append(orient_triangle(triangle, desired_y))
    return np.asarray(triangles)


def fan_cap(loop: np.ndarray, desired_y: float) -> np.ndarray:
    center = loop.mean(axis=0)
    triangles = []
    for index in range(len(loop)):
        triangle = np.array([loop[index], loop[(index + 1) % len(loop)], center])
        triangles.append(orient_triangle(triangle, desired_y))
    return np.asarray(triangles)


def surface_y_limits(triangles: np.ndarray, x: float, z: float) -> tuple[float, float]:
    projected = triangles[:, :, (0, 2)]
    low = projected.min(axis=1)
    high = projected.max(axis=1)
    mask = (
        (low[:, 0] <= x)
        & (high[:, 0] >= x)
        & (low[:, 1] <= z)
        & (high[:, 1] >= z)
    )
    candidates = triangles[mask]
    if not len(candidates):
        raise ValueError(f"Cavity point ({x:.3f}, {z:.3f}) is outside shell projection")
    a = candidates[:, 0, (0, 2)]
    b = candidates[:, 1, (0, 2)]
    c = candidates[:, 2, (0, 2)]
    point = np.array([x, z])
    v0, v1, v2 = b - a, c - a, point - a
    denominator = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    usable = np.abs(denominator) > 1e-10
    u = np.zeros(len(candidates))
    v = np.zeros(len(candidates))
    u[usable] = (v2[:, 0] * v1[usable, 1] - v1[usable, 0] * v2[:, 1]) / denominator[usable]
    v[usable] = (v0[usable, 0] * v2[:, 1] - v2[:, 0] * v0[usable, 1]) / denominator[usable]
    inside = usable & (u >= -1e-8) & (v >= -1e-8) & (u + v <= 1.0 + 1e-8)
    selected = candidates[inside]
    if not len(selected):
        raise ValueError(f"No shell intersections at cavity point ({x:.3f}, {z:.3f})")
    ys = (
        selected[:, 0, 1]
        + u[inside] * (selected[:, 1, 1] - selected[:, 0, 1])
        + v[inside] * (selected[:, 2, 1] - selected[:, 0, 1])
    )
    return float(ys.min()), float(ys.max())


def cavity_surface(
    plane: float,
    front: bool,
    shell_triangles: np.ndarray,
    rings: int = 24,
    sides: int = 128,
) -> tuple[np.ndarray, np.ndarray]:
    sign = 1.0 if front else -1.0
    phis = np.linspace(0.0, 2.0 * math.pi, sides, endpoint=False)
    ring_list: list[np.ndarray] = []
    # Omit the pole from rings and close it separately.
    for theta in np.linspace(0.0, math.pi / 2.0, rings, endpoint=False):
        radial = math.cos(theta)
        x_values = CAVITY_CENTER_X_MM + CAVITY_RADIUS_X_MM * radial * np.cos(phis)
        z_values = CAVITY_CENTER_Z_MM + CAVITY_RADIUS_Z_MM * radial * np.sin(phis)
        blend = math.sin(theta)
        y_values = []
        for x_value, z_value in zip(x_values, z_values):
            minimum_y, maximum_y = surface_y_limits(shell_triangles, float(x_value), float(z_value))
            if front:
                target = max(plane + 0.5, maximum_y - WALL_THICKNESS_MM)
            else:
                target = min(plane - 0.5, minimum_y + WALL_THICKNESS_MM)
            y_values.append(plane + blend * (target - plane))
        ring_list.append(np.column_stack([x_values, np.asarray(y_values), z_values]))
    triangles: list[np.ndarray] = []
    for ring_index in range(len(ring_list) - 1):
        lower, upper = ring_list[ring_index], ring_list[ring_index + 1]
        for side in range(sides):
            next_side = (side + 1) % sides
            triangles.append(np.array([lower[side], lower[next_side], upper[next_side]]))
            triangles.append(np.array([lower[side], upper[next_side], upper[side]]))
    minimum_y, maximum_y = surface_y_limits(shell_triangles, CAVITY_CENTER_X_MM, CAVITY_CENTER_Z_MM)
    pole = np.array(
        [
            CAVITY_CENTER_X_MM,
            max(plane + 0.5, maximum_y - WALL_THICKNESS_MM)
            if front
            else min(plane - 0.5, minimum_y + WALL_THICKNESS_MM),
            CAVITY_CENTER_Z_MM,
        ]
    )
    last = ring_list[-1]
    for side in range(sides):
        triangles.append(np.array([last[side], last[(side + 1) % sides], pole]))

    oriented: list[np.ndarray] = []
    center = np.array([CAVITY_CENTER_X_MM, plane, CAVITY_CENTER_Z_MM])
    for triangle in triangles:
        normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
        sample = triangle.mean(axis=0)
        # The enclosure's inner-wall normal points into the cavity.
        if float(np.dot(normal, center - sample)) < 0:
            triangle = triangle[[0, 2, 1]]
        oriented.append(triangle)
    return np.asarray(oriented), ring_list[0]


def signed_volume(triangles: np.ndarray) -> float:
    return float(
        np.einsum("ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])).sum()
        / 6.0
    )


def orient_consistently(triangles: np.ndarray) -> np.ndarray:
    vertices = triangles.reshape(-1, 3)
    scale = max(float(np.ptp(vertices, axis=0).max()), 1.0)
    quantized = np.round(vertices / (scale * 1e-7)).astype(np.int64)
    _, inverse = np.unique(quantized, axis=0, return_inverse=True)
    faces = inverse.reshape(-1, 3)
    edge_faces: dict[tuple[int, int], list[tuple[int, int]]] = collections.defaultdict(list)
    for face_index, face in enumerate(faces):
        for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            a, b = int(start), int(end)
            key = (min(a, b), max(a, b))
            direction = 1 if a < b else -1
            edge_faces[key].append((face_index, direction))

    adjacency: dict[int, list[tuple[int, bool]]] = collections.defaultdict(list)
    for linked in edge_faces.values():
        if len(linked) != 2:
            continue
        (left, left_direction), (right, right_direction) = linked
        same_flip = left_direction != right_direction
        adjacency[left].append((right, same_flip))
        adjacency[right].append((left, same_flip))

    flips: list[bool | None] = [None] * len(triangles)
    for seed in range(len(triangles)):
        if flips[seed] is not None:
            continue
        flips[seed] = False
        queue = collections.deque([seed])
        while queue:
            current = queue.popleft()
            for neighbor, same_flip in adjacency[current]:
                expected = flips[current] if same_flip else not flips[current]
                if flips[neighbor] is None:
                    flips[neighbor] = expected
                    queue.append(neighbor)
    result = triangles.copy()
    mask = np.asarray(flips, dtype=bool)
    result[mask] = result[mask][:, [0, 2, 1]]
    if signed_volume(result) < 0:
        result = result[:, [0, 2, 1]]
    return result


def write_binary_stl(path: Path, triangles: np.ndarray, label: str) -> None:
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-12
    normals[valid] /= lengths[valid, None]
    header = label.encode("ascii", errors="replace")[:80].ljust(80, b" ")
    with path.open("wb") as handle:
        handle.write(header)
        handle.write(struct.pack("<I", len(triangles)))
        for normal, triangle in zip(normals, triangles):
            handle.write(struct.pack("<12fH", *(normal.astype(np.float32)), *(triangle.astype(np.float32).ravel()), 0))


def build_half(triangles: np.ndarray, front: bool) -> tuple[np.ndarray, int]:
    plane = SEAM_HALF_GAP_MM if front else -SEAM_HALF_GAP_MM
    outer, segments = clip_half(triangles, axis=1, plane=plane, keep_positive=front)
    loops = ordered_loops(segments)
    if not loops:
        raise ValueError("No split contour found")
    outer_loop = max(loops, key=lambda loop: np.linalg.norm(np.diff(np.vstack([loop, loop[0]]), axis=0), axis=1).sum())
    cavity, inner_ring = cavity_surface(plane, front, triangles)
    desired_y = -1.0 if front else 1.0
    annulus = annulus_triangles(outer_loop, inner_ring, desired_y=desired_y)
    minor_caps = [fan_cap(loop, desired_y) for loop in loops if loop is not outer_loop]
    result = np.concatenate([outer, cavity, annulus, *minor_caps], axis=0)
    result = orient_consistently(result)
    return result, len(loops)


def main() -> None:
    source = Path(sys.argv[1])
    output_directory = Path(sys.argv[2])
    output_directory.mkdir(parents=True, exist_ok=True)
    original = load_binary_stl(source)
    main_shell = largest_component(original)
    bounds_min = main_shell.reshape(-1, 3).min(axis=0)
    bounds_max = main_shell.reshape(-1, 3).max(axis=0)
    center = (bounds_min + bounds_max) / 2.0
    scale = TARGET_LENGTH_MM / float(bounds_max[0] - bounds_min[0])
    scaled = (main_shell - center) * scale

    front, front_loops = build_half(scaled, front=True)
    back, back_loops = build_half(scaled, front=False)
    front_path = output_directory / "magic_conch_front_prototype.stl"
    back_path = output_directory / "magic_conch_back_prototype.stl"
    write_binary_stl(front_path, front, "Magic Conch front hollow prototype")
    write_binary_stl(back_path, back, "Magic Conch back hollow prototype")
    print(f"scale={scale:.9f}")
    print(f"scaled_dimensions_mm={np.ptp(scaled.reshape(-1, 3), axis=0).tolist()}")
    print(f"front_triangles={len(front)} front_split_loops={front_loops} volume_mm3={signed_volume(front):.3f}")
    print(f"back_triangles={len(back)} back_split_loops={back_loops} volume_mm3={signed_volume(back):.3f}")
    print(front_path.resolve())
    print(back_path.resolve())


if __name__ == "__main__":
    main()
