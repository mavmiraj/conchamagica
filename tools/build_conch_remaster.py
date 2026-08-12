from __future__ import annotations

import math
import sys
from pathlib import Path

import manifold3d
import numpy as np

import build_prototype_meshes as base
from build_video_reference_v2 import (
    leaf_points,
    snap_post,
    snap_socket,
    y_cylinder_segment,
    y_prism,
)
from manifold_finalize import to_manifold, write_binary_stl


# All centers and their 3.25 mm root pads remain inside the original projected
# outline. They sit in the seam annulus, outside the electronics cavity.
SNAP_POSITIONS_XZ = ((-39.0, 16.5), (-39.0, -18.5), (26.0, 14.5), (28.0, -15.5))


def preserve_original_surface(source: Path, destination: Path) -> None:
    """Refine the scan facets without applying silhouette-changing smoothing."""
    triangles = base.largest_component(base.load_binary_stl(source))
    raw_vertices = triangles.reshape(-1, 3)
    vertices, inverse = np.unique(raw_vertices, axis=0, return_inverse=True)
    faces = inverse.reshape(-1, 3)
    original_min = vertices.min(axis=0)
    original_max = vertices.max(axis=0)
    original_center = (original_min + original_max) / 2.0
    original_extent = original_max - original_min

    solid = manifold3d.Manifold(
        manifold3d.Mesh(vertices.astype(np.float32), faces.astype(np.uint32))
    )
    # Tangent interpolation smooths the triangle transitions. Unlike V2, this
    # remaster applies no Laplacian/Taubin vertex displacement to the source.
    refined = solid.smooth_out(100.0, 0.35).refine(2)
    mesh = refined.to_mesh()
    refined_vertices = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
    refined_faces = np.asarray(mesh.tri_verts, dtype=np.uint32)

    # Lock the refined mesh back to the original source envelope on every axis.
    refined_min = refined_vertices.min(axis=0)
    refined_max = refined_vertices.max(axis=0)
    refined_vertices -= (refined_min + refined_max) / 2.0
    refined_vertices *= original_extent / (refined_max - refined_min)
    refined_vertices += original_center
    locked = manifold3d.Manifold(
        manifold3d.Mesh(refined_vertices.astype(np.float32), refined_faces)
    )
    write_binary_stl(destination, locked, "Magic Conch remaster locked exterior")


def validate_snap_locations(scaled_shell: np.ndarray) -> None:
    for center_x, center_z in SNAP_POSITIONS_XZ:
        cavity_distance = math.sqrt(
            ((center_x - base.CAVITY_CENTER_X_MM) / base.CAVITY_RADIUS_X_MM) ** 2
            + ((center_z - base.CAVITY_CENTER_Z_MM) / base.CAVITY_RADIUS_Z_MM) ** 2
        )
        if cavity_distance <= 1.04:
            raise ValueError(f"Snap at {(center_x, center_z)} intrudes into the cavity")
        # Sample the entire root pad, not just its center, against the original
        # XZ projection so no snap circle can protrude beyond the shell outline.
        for angle in np.linspace(0.0, 2.0 * math.pi, 24, endpoint=False):
            x = center_x + 3.3 * math.cos(angle)
            z = center_z + 3.3 * math.sin(angle)
            base.surface_y_limits(scaled_shell, x, z)


def back_mesh_seat(opening_cs: manifold3d.CrossSection) -> manifold3d.Manifold:
    """Low, peg-free ledge behind the spiral-side grille opening."""
    outer = opening_cs.offset(2.8, manifold3d.JoinType.Round, 2.0, 32)
    inner = opening_cs.offset(0.30, manifold3d.JoinType.Round, 2.0, 32)
    return y_prism(outer - inner, 2.0, -19.0)


def build(source: Path, output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    preserved_source = output_directory / "magicconch_original_surface_locked.stl"
    preserve_original_surface(source, preserved_source)

    base.CAVITY_CENTER_X_MM = -7.0
    base.CAVITY_CENTER_Z_MM = -2.0
    base.CAVITY_RADIUS_X_MM = 41.0
    base.CAVITY_RADIUS_Z_MM = 20.5
    base.WALL_THICKNESS_MM = 3.0

    main_shell = base.largest_component(base.load_binary_stl(preserved_source))
    bounds_min = main_shell.reshape(-1, 3).min(axis=0)
    bounds_max = main_shell.reshape(-1, 3).max(axis=0)
    center = (bounds_min + bounds_max) / 2.0
    scale = base.TARGET_LENGTH_MM / float(bounds_max[0] - bounds_min[0])
    scaled = (main_shell - center) * scale
    validate_snap_locations(scaled)

    front_triangles, _ = base.build_half(scaled, front=True)
    back_triangles, _ = base.build_half(scaled, front=False)
    front_base = output_directory / "MagicConch_FrontHousing_Remaster_base.stl"
    back_base = output_directory / "MagicConch_BackHousing_Remaster_base.stl"
    base.write_binary_stl(front_base, front_triangles, "Magic Conch remaster front base")
    base.write_binary_stl(back_base, back_triangles, "Magic Conch remaster back base")
    front = to_manifold(front_base)
    back = to_manifold(back_base)

    opening_cs = manifold3d.CrossSection([leaf_points(0.94).tolist()])
    # The plain/front half remains visually closed. The grille belongs on the
    # spiral/back half, as marked in the user's SolidWorks screenshots.
    back = back - y_prism(opening_cs, 100.0, 0.0)
    back = back + back_mesh_seat(opening_cs)
    front = front - y_cylinder_segment(3.25, 100.0, 0.0, 0.0, 27.0)

    for x, z in SNAP_POSITIONS_XZ:
        front = front + snap_post(x, z)
        back = back - snap_socket(x, z)

    # Reinforce only the inside of the real pull-string opening.
    collar = y_cylinder_segment(5.0, 2.0, 0.0, 18.0, 27.0)
    collar_hole = y_cylinder_segment(3.25, 4.0, 0.0, 18.0, 27.0)
    front = front + (collar - collar_hole)

    write_binary_stl(
        output_directory / "MagicConch_FrontHousing_Remaster_print.stl",
        front,
        "Magic Conch remaster front: closed exterior and internal perimeter snaps",
    )
    write_binary_stl(
        output_directory / "MagicConch_BackHousing_Remaster_print.stl",
        back,
        "Magic Conch remaster back: spiral-side grille, flat cavity and snap sockets",
    )


def main() -> None:
    default_source = Path("reference/magicconch_smoothed_original.stl")
    if not default_source.exists():
        default_source = Path("magicconch_smoothed_original.stl")
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else default_source
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("prototype/remaster")
    build(source, output)


if __name__ == "__main__":
    main()
