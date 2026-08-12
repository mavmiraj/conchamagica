from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

from inspect_stl import load_binary_stl
from render_stl_preview import render_panel, rotation


def main() -> None:
    source = Path(sys.argv[1])
    destination = Path(sys.argv[2])
    half = sys.argv[3].lower() if len(sys.argv) > 3 else "front"
    triangles = load_binary_stl(source)
    bounds = triangles.reshape(-1, 3)
    triangles = triangles - (bounds.min(axis=0) + bounds.max(axis=0)) / 2.0

    exterior_x = 90.0 if half == "front" else -90.0
    interior_x = -exterior_x
    panels = [
        render_panel(triangles, rotation(exterior_x, 0, 0), "Exterior", 700),
        render_panel(triangles, rotation(interior_x, 0, 0), "Interior / closure", 700),
        render_panel(triangles, rotation(exterior_x * 0.74, 0, 35), "Exterior isometric", 700),
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
