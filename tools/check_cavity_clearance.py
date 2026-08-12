from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

import build_prototype_meshes as builder
from inspect_stl import load_binary_stl


def y_intersections(triangles: np.ndarray, x: float, z: float) -> np.ndarray:
    projected = triangles[:, :, (0, 2)]
    low = projected.min(axis=1)
    high = projected.max(axis=1)
    candidates = triangles[
        (low[:, 0] <= x)
        & (high[:, 0] >= x)
        & (low[:, 1] <= z)
        & (high[:, 1] >= z)
    ]
    if not len(candidates):
        return np.empty(0)
    a = candidates[:, 0, (0, 2)]
    b = candidates[:, 1, (0, 2)]
    c = candidates[:, 2, (0, 2)]
    point = np.array([x, z])
    v0 = b - a
    v1 = c - a
    v2 = point - a
    denominator = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    usable = np.abs(denominator) > 1e-10
    u = np.zeros(len(candidates))
    v = np.zeros(len(candidates))
    u[usable] = (v2[:, 0] * v1[usable, 1] - v1[usable, 0] * v2[:, 1]) / denominator[usable]
    v[usable] = (v0[usable, 0] * v2[:, 1] - v2[:, 0] * v0[usable, 1]) / denominator[usable]
    inside = usable & (u >= -1e-8) & (v >= -1e-8) & (u + v <= 1.0 + 1e-8)
    if not np.any(inside):
        return np.empty(0)
    selected = candidates[inside]
    weights_u = u[inside]
    weights_v = v[inside]
    return (
        selected[:, 0, 1]
        + weights_u * (selected[:, 1, 1] - selected[:, 0, 1])
        + weights_v * (selected[:, 2, 1] - selected[:, 0, 1])
    )


def main() -> None:
    source = Path(sys.argv[1])
    triangles = builder.largest_component(load_binary_stl(source))
    vertices = triangles.reshape(-1, 3)
    center = (vertices.min(axis=0) + vertices.max(axis=0)) / 2.0
    scale = builder.TARGET_LENGTH_MM / float(np.ptp(vertices, axis=0)[0])
    triangles = (triangles - center) * scale

    for front in (True, False):
        plane = builder.SEAM_HALF_GAP_MM if front else -builder.SEAM_HALF_GAP_MM
        cavity, _ = builder.cavity_surface(plane, front, triangles)
        points = np.unique(np.round(cavity.reshape(-1, 3), 7), axis=0)
        clearances = []
        failures = []
        for point in points:
            intersections = y_intersections(triangles, float(point[0]), float(point[2]))
            if not len(intersections):
                failures.append(point)
                continue
            clearance = float(intersections.max() - point[1]) if front else float(point[1] - intersections.min())
            clearances.append(clearance)
            if clearance < -1e-5:
                failures.append(point)
        print(
            f"{'front' if front else 'back'}: points={len(points)} "
            f"min_clearance_mm={min(clearances):.4f} outside_points={len(failures)}"
        )
        if failures:
            print(f"  sample_outside={failures[:5]}")


if __name__ == "__main__":
    main()
