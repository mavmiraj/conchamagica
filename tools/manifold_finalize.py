from __future__ import annotations

import struct
import sys
from pathlib import Path

import manifold3d
import numpy as np


def load_binary_stl(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with path.open("rb") as handle:
        handle.read(80)
        count = struct.unpack("<I", handle.read(4))[0]
        records = np.fromfile(
            handle,
            dtype=np.dtype(
                [("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")]
            ),
            count=count,
        )
    vertices = records["vertices"].reshape(-1, 3)
    unique_vertices, inverse = np.unique(vertices, axis=0, return_inverse=True)
    return unique_vertices.astype(np.float32), inverse.reshape(-1, 3).astype(np.uint32)


def to_manifold(path: Path) -> manifold3d.Manifold:
    vertices, faces = load_binary_stl(path)
    result = manifold3d.Manifold(manifold3d.Mesh(vertices, faces))
    if result.status() != manifold3d.Error.NoError:
        raise ValueError(f"Manifold rejected {path}: {result.status()}")
    return result


def y_cylinder(radius_x: float, radius_z: float, x: float, z: float) -> manifold3d.Manifold:
    return (
        manifold3d.Manifold.cylinder(100.0, 1.0, 1.0, 96, center=True)
        .scale((radius_x, radius_z, 1.0))
        .rotate((90.0, 0.0, 0.0))
        .translate((x, 0.0, z))
    )


def write_binary_stl(path: Path, solid: manifold3d.Manifold, label: str) -> None:
    if solid.status() != manifold3d.Error.NoError or solid.is_empty():
        raise ValueError(f"Invalid result for {path}: {solid.status()}")
    mesh = solid.to_mesh()
    vertices = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
    faces = np.asarray(mesh.tri_verts, dtype=np.int64)
    triangles = vertices[faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-12
    normals[valid] /= lengths[valid, None]
    with path.open("wb") as handle:
        handle.write(label.encode("ascii", errors="replace")[:80].ljust(80, b" "))
        handle.write(struct.pack("<I", len(triangles)))
        for normal, triangle in zip(normals, triangles):
            handle.write(struct.pack("<12fH", *normal.astype(np.float32), *triangle.astype(np.float32).ravel(), 0))
    print(
        f"{path.name}: triangles={len(triangles)} volume_mm3={solid.volume():.3f} "
        f"genus={solid.genus()} status={solid.status()}"
    )


def main() -> None:
    directory = Path(sys.argv[1])
    front = to_manifold(directory / "magic_conch_front_prototype.stl")
    back = to_manifold(directory / "magic_conch_back_prototype.stl")

    closure = y_cylinder(1.7, 1.7, -53.0, 0.0) + y_cylinder(1.7, 1.7, 45.0, 0.0)
    speaker = y_cylinder(24.0, 14.0, -7.0, -2.0)
    string_passage = y_cylinder(3.25, 3.25, 0.0, 27.0)

    front = front - closure - speaker - string_passage
    back = back - closure

    write_binary_stl(directory / "MagicConch_FrontHousing_print.stl", front, "Magic Conch front print-ready")
    write_binary_stl(directory / "MagicConch_BackHousing_print.stl", back, "Magic Conch back print-ready")


if __name__ == "__main__":
    main()
