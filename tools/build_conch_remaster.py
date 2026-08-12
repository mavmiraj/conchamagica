from __future__ import annotations

import math
import sys
from pathlib import Path

import manifold3d
import numpy as np

import build_prototype_meshes as base
from build_video_reference_v2 import (
    box_centered,
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
SPEAKER_BOSSES_XZ = ((-24.0, 15.0), (10.0, 12.0), (-24.0, -19.0), (10.0, -16.0))
PCB_BOSSES_XZ = ((-26.0, -10.0), (12.0, -10.0), (-26.0, 2.0), (12.0, 2.0))


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


def cavity_wall_y(scaled_shell: np.ndarray, x: float, z: float, front: bool) -> float:
    radial = math.sqrt(
        ((x - base.CAVITY_CENTER_X_MM) / base.CAVITY_RADIUS_X_MM) ** 2
        + ((z - base.CAVITY_CENTER_Z_MM) / base.CAVITY_RADIUS_Z_MM) ** 2
    )
    if radial >= 1.0:
        raise ValueError(f"Mount point {(x, z)} lies outside the cavity")
    blend = math.sqrt(max(0.0, 1.0 - radial * radial))
    minimum_y, maximum_y = base.surface_y_limits(scaled_shell, x, z)
    plane = base.SEAM_HALF_GAP_MM if front else -base.SEAM_HALF_GAP_MM
    target = maximum_y - base.WALL_THICKNESS_MM if front else minimum_y + base.WALL_THICKNESS_MM
    return plane + blend * (target - plane)


def mesh_seat(opening_cs: manifold3d.CrossSection) -> manifold3d.Manifold:
    outer = opening_cs.offset(2.8, manifold3d.JoinType.Round, 2.0, 32)
    inner = opening_cs.offset(0.30, manifold3d.JoinType.Round, 2.0, 32)
    return y_prism(outer - inner, 2.0, 19.0)


def add_speaker_mounts(front: manifold3d.Manifold, opening_cs: manifold3d.CrossSection) -> manifold3d.Manifold:
    # The bosses overlap the mesh-seat perimeter, producing an integrated frame
    # for a roughly 40 mm speaker or a removable printed adapter plate.
    frame = mesh_seat(opening_cs)
    for x, z in SPEAKER_BOSSES_XZ:
        boss = y_cylinder_segment(3.25, 12.0, x, 14.0, z)
        pilot = y_cylinder_segment(1.10, 8.0, x, 10.0, z)
        frame = frame + boss - pilot
    # Compact bridges guarantee that the broad and pointed ends of the mesh seat
    # join the original inner skin without crossing the sound aperture.
    frame = (
        frame
        + box_centered(7.0, 3.0, 4.0, -35.0, 19.0, -2.0)
        + box_centered(7.0, 3.0, 4.0, 27.0, 19.0, -2.0)
    )
    return front + frame


def add_pcb_mounts(back: manifold3d.Manifold, scaled_shell: np.ndarray) -> manifold3d.Manifold:
    # Generic 38 x 18 mm four-point layout. Each boss is grown directly from the
    # locally calculated cavity wall, so none float inside the housing.
    for x, z in PCB_BOSSES_XZ:
        wall_y = cavity_wall_y(scaled_shell, x, z, front=False)
        accessible_top_y = -4.5
        root_y = wall_y - 0.8
        length = accessible_top_y - root_y
        if length < 3.0:
            raise ValueError(f"Insufficient PCB-boss depth at {(x, z)}: {length:.3f} mm")
        boss = y_cylinder_segment(3.0, length, x, (root_y + accessible_top_y) / 2.0, z)
        pilot_depth = min(6.0, length - 1.2)
        pilot_length = pilot_depth + 0.5
        pilot_center = accessible_top_y + 0.25 - pilot_depth / 2.0
        pilot = y_cylinder_segment(1.10, pilot_length, x, pilot_center, z)
        back = back + boss - pilot
    return back


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
    front = front - y_prism(opening_cs, 100.0, 0.0)
    front = front - y_cylinder_segment(3.25, 100.0, 0.0, 0.0, 27.0)
    front = add_speaker_mounts(front, opening_cs)

    for x, z in SNAP_POSITIONS_XZ:
        front = front + snap_post(x, z)
        back = back - snap_socket(x, z)

    # Reinforce only the inside of the real pull-string opening.
    collar = y_cylinder_segment(5.0, 2.0, 0.0, 18.0, 27.0)
    collar_hole = y_cylinder_segment(3.25, 4.0, 0.0, 18.0, 27.0)
    front = front + (collar - collar_hole)
    back = add_pcb_mounts(back, scaled)

    write_binary_stl(
        output_directory / "MagicConch_FrontHousing_Remaster_print.stl",
        front,
        "Magic Conch remaster front: locked exterior, internal snaps and speaker frame",
    )
    write_binary_stl(
        output_directory / "MagicConch_BackHousing_Remaster_print.stl",
        back,
        "Magic Conch remaster back: locked exterior, snap sockets and PCB bosses",
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
