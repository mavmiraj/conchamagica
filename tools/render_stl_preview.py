from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from inspect_stl import load_binary_stl


def rotation(x_degrees: float, y_degrees: float, z_degrees: float) -> np.ndarray:
    x, y, z = np.radians([x_degrees, y_degrees, z_degrees])
    rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rz = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return rz @ ry @ rx


def render_panel(triangles: np.ndarray, matrix: np.ndarray, title: str, size: int = 800) -> Image.Image:
    transformed = triangles @ matrix.T
    xy = transformed[:, :, :2]
    extent = np.ptp(xy.reshape(-1, 2), axis=0)
    scale = (size * 0.82) / max(float(extent.max()), 1e-9)
    center = xy.reshape(-1, 2).mean(axis=0)
    screen = (xy - center) * scale
    screen[:, :, 0] += size / 2
    screen[:, :, 1] = size / 2 - screen[:, :, 1]

    normals = np.cross(transformed[:, 1] - transformed[:, 0], transformed[:, 2] - transformed[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-12
    normals[valid] /= lengths[valid, None]
    light = np.array([-0.35, 0.45, 0.82])
    light /= np.linalg.norm(light)
    shade = np.clip(normals @ light, -0.15, 1.0)
    depth = transformed[:, :, 2].mean(axis=1)
    order = np.argsort(depth)

    image = Image.new("RGB", (size, size), (247, 248, 250))
    draw = ImageDraw.Draw(image)
    for face_index in order:
        intensity = int(135 + 95 * max(float(shade[face_index]), 0.0))
        color = (intensity, int(intensity * 0.72), int(intensity * 0.80))
        points = [tuple(map(float, point)) for point in screen[face_index]]
        draw.polygon(points, fill=color)
    draw.text((24, 22), title, fill=(30, 30, 35), stroke_width=1, stroke_fill=(255, 255, 255))
    return image


def main() -> None:
    source = Path(sys.argv[1])
    destination = Path(sys.argv[2])
    triangles = load_binary_stl(source)
    center = (triangles.reshape(-1, 3).min(axis=0) + triangles.reshape(-1, 3).max(axis=0)) / 2
    triangles = triangles - center
    panels = [
        render_panel(triangles, rotation(90, 0, 0), "Front (looking along Y)"),
        render_panel(triangles, rotation(68, 0, 35), "Isometric"),
        render_panel(triangles, rotation(0, 90, 0), "Side (looking along X)"),
    ]
    canvas = Image.new("RGB", (sum(panel.width for panel in panels), panels[0].height), "white")
    x_offset = 0
    for panel in panels:
        canvas.paste(panel, (x_offset, 0))
        x_offset += panel.width
    canvas.save(destination)
    print(destination.resolve())


if __name__ == "__main__":
    main()
