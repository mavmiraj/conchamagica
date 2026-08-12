from __future__ import annotations

import collections
import struct
import sys
from pathlib import Path

import numpy as np


def load_binary_stl(path: Path) -> np.ndarray:
    with path.open("rb") as handle:
        handle.read(80)
        count = struct.unpack("<I", handle.read(4))[0]
        records = np.fromfile(
            handle,
            dtype=np.dtype(
                [
                    ("normal", "<f4", 3),
                    ("vertices", "<f4", (3, 3)),
                    ("attribute", "<u2"),
                ]
            ),
            count=count,
        )
    if len(records) != count:
        raise ValueError(f"Expected {count} triangles, read {len(records)}")
    return records["vertices"].astype(np.float64)


def main() -> None:
    path = Path(sys.argv[1])
    triangles = load_binary_stl(path)
    vertices = triangles.reshape(-1, 3)
    minimum = vertices.min(axis=0)
    maximum = vertices.max(axis=0)
    size = maximum - minimum

    # Quantize only for topology inspection, preserving the original mesh file.
    scale = max(float(size.max()), 1.0)
    quantized = np.round(vertices / (scale * 1e-7)).astype(np.int64)
    unique, inverse = np.unique(quantized, axis=0, return_inverse=True)
    faces = inverse.reshape(-1, 3)
    edge_counts: collections.Counter[tuple[int, int]] = collections.Counter()
    vertex_faces: dict[int, list[int]] = collections.defaultdict(list)
    for face_index, face in enumerate(faces):
        for vertex_index in face:
            vertex_faces[int(vertex_index)].append(face_index)
    for face in faces:
        edge_counts.update(
            tuple(sorted((int(face[a]), int(face[b]))))
            for a, b in ((0, 1), (1, 2), (2, 0))
        )
    boundary_edges = sum(count == 1 for count in edge_counts.values())
    nonmanifold_edges = sum(count > 2 for count in edge_counts.values())

    parent = np.arange(len(faces), dtype=np.int64)

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = int(parent[item])
        return item

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for connected_faces in vertex_faces.values():
        first = connected_faces[0]
        for other in connected_faces[1:]:
            union(first, other)

    groups: dict[int, list[int]] = collections.defaultdict(list)
    for face_index in range(len(faces)):
        groups[find(face_index)].append(face_index)
    components = sorted(groups.values(), key=len, reverse=True)

    signed_volume = np.einsum(
        "ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])
    ).sum() / 6.0
    print(f"file={path}")
    print(f"triangles={len(triangles)}")
    print(f"unique_vertices={len(unique)}")
    print(f"bounds_min={minimum.tolist()}")
    print(f"bounds_max={maximum.tolist()}")
    print(f"dimensions={size.tolist()}")
    print(f"signed_volume={signed_volume:.6f}")
    print(f"boundary_edges={boundary_edges}")
    print(f"nonmanifold_edges={nonmanifold_edges}")
    print(f"watertight={boundary_edges == 0 and nonmanifold_edges == 0}")
    print(f"components={len(components)}")
    for index, component in enumerate(components[:10]):
        component_vertices = triangles[np.asarray(component)].reshape(-1, 3)
        component_min = component_vertices.min(axis=0)
        component_max = component_vertices.max(axis=0)
        print(
            f"component_{index}=faces:{len(component)},"
            f"min:{component_min.tolist()},max:{component_max.tolist()}"
        )


if __name__ == "__main__":
    main()
