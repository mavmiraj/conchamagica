from __future__ import annotations

import math
import sys
from pathlib import Path

import manifold3d
import numpy as np

import build_prototype_meshes as base
from manifold_finalize import to_manifold, write_binary_stl


SNAP_POSITIONS_XZ = ((-43.0, 24.5), (-43.0, -24.5), (33.0, 20.5), (33.0, -20.5))


def smooth_shell(source: Path, destination: Path) -> None:
    """Remove high-frequency shell ridges while preserving the overall silhouette."""
    triangles = base.largest_component(base.load_binary_stl(source))
    raw_vertices = triangles.reshape(-1, 3)
    unique_vertices, inverse = np.unique(raw_vertices, axis=0, return_inverse=True)
    faces = inverse.reshape(-1, 3)
    vertices = unique_vertices.astype(np.float64)
    original_min = vertices.min(axis=0)
    original_max = vertices.max(axis=0)
    original_center = (original_min + original_max) / 2.0
    original_extent = original_max - original_min

    edges = np.vstack((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    edges = np.vstack((edges, edges[:, ::-1]))
    edges = np.unique(edges, axis=0)
    degree = np.bincount(edges[:, 0], minlength=len(vertices)).astype(np.float64)

    def laplacian_step(amount: float) -> None:
        neighbor_sum = np.zeros_like(vertices)
        np.add.at(neighbor_sum, edges[:, 0], vertices[edges[:, 1]])
        average = neighbor_sum / degree[:, None]
        vertices[:] += amount * (average - vertices)

    # Taubin's alternating positive/negative passes remove bumps without the
    # obvious shrinkage of ordinary Laplacian smoothing.
    for _ in range(80):
        laplacian_step(0.42)
        laplacian_step(-0.43)

    # Restore the exact design envelope after the shrink-resistant smoothing pass.
    smooth_min = vertices.min(axis=0)
    smooth_max = vertices.max(axis=0)
    vertices -= (smooth_min + smooth_max) / 2.0
    vertices *= original_extent / (smooth_max - smooth_min)
    vertices += original_center
    smooth_manifold = manifold3d.Manifold(
        manifold3d.Mesh(vertices.astype(np.float32), faces.astype(np.uint32))
    )
    # Curved interpolation followed by one subdivision pass removes the visible
    # triangular facets while keeping the deliberately smooth spiral silhouette.
    smooth_manifold = smooth_manifold.smooth_out(180.0, 0.85).refine(2)
    write_binary_stl(destination, smooth_manifold, "Smoothed Magic Conch V2 source")


def leaf_points(scale: float = 1.0) -> np.ndarray:
    """Rounded body end flowing into the pointed snout end seen in the reference."""
    p0 = np.array([-32.0, -2.0])
    p1 = np.array([-32.0, 12.5])
    p2 = np.array([-12.0, 16.0])
    p3 = np.array([25.0, -2.0])
    p4 = np.array([-12.0, -20.0])
    p5 = np.array([-32.0, -16.5])

    def bezier(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> list[np.ndarray]:
        values = []
        for t in np.linspace(0.0, 1.0, 49, endpoint=False):
            values.append((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t**2 * c + t**3 * d)
        return values

    points = np.asarray(bezier(p0, p1, p2, p3) + bezier(p3, p4, p5, p0))
    center = np.array([-7.0, -2.0])
    # CrossSection uses positive (counter-clockwise) winding for filled regions.
    return (center + scale * (points - center))[::-1]


def y_prism(cross_section: manifold3d.CrossSection, depth: float, center_y: float) -> manifold3d.Manifold:
    return (
        manifold3d.Manifold.extrude(cross_section, depth)
        .translate((0.0, 0.0, -depth / 2.0))
        .rotate((90.0, 0.0, 0.0))
        .translate((0.0, center_y, 0.0))
    )


def y_cylinder_segment(radius: float, length: float, x: float, center_y: float, z: float) -> manifold3d.Manifold:
    return (
        manifold3d.Manifold.cylinder(length, radius, radius, 64, center=True)
        .rotate((90.0, 0.0, 0.0))
        .translate((x, center_y, z))
    )


def box_centered(size_x: float, size_y: float, size_z: float, x: float, y: float, z: float) -> manifold3d.Manifold:
    return manifold3d.Manifold.cube((size_x, size_y, size_z), center=True).translate((x, y, z))


def snap_post(x: float, z: float) -> manifold3d.Manifold:
    # A forked post can flex inward while its enlarged head passes the socket throat.
    stem = y_cylinder_segment(1.75, 8.2, x, -2.8, z)
    head = manifold3d.Manifold.sphere(2.25, 48).scale((1.0, 0.72, 1.0)).translate((x, -6.25, z))
    root_pad = y_cylinder_segment(3.25, 1.8, x, 0.75, z)
    slot = box_centered(0.75, 7.5, 5.5, x, -5.0, z)
    return (stem + head + root_pad) - slot


def snap_socket(x: float, z: float) -> manifold3d.Manifold:
    throat = y_cylinder_segment(1.98, 8.8, x, -3.75, z)
    detent = manifold3d.Manifold.sphere(2.45, 48).scale((1.0, 0.78, 1.0)).translate((x, -6.3, z))
    lead_in = (
        manifold3d.Manifold.cylinder(1.4, 2.55, 1.98, 64, center=True)
        .rotate((90.0, 0.0, 0.0))
        .translate((x, -0.45, z))
    )
    return throat + detent + lead_in


def add_mesh_frame(front: manifold3d.Manifold, opening_cs: manifold3d.CrossSection) -> manifold3d.Manifold:
    # A 2.5 mm perimeter seat sits behind the skin. Four bridges tie it to the
    # cavity wall so the mesh can be glued or heat-staked without blocking sound.
    outer_cs = opening_cs.offset(2.5, manifold3d.JoinType.Round, 2.0, 24)
    inner_clearance_cs = opening_cs.offset(0.25, manifold3d.JoinType.Round, 2.0, 24)
    ring_cs = outer_cs - inner_clearance_cs
    ring = y_prism(ring_cs, 2.0, 19.0)
    bridges = (
        box_centered(7.0, 3.0, 4.0, -35.0, 19.0, -2.0)
        + box_centered(7.0, 3.0, 4.0, 27.0, 19.0, -2.0)
        + box_centered(4.0, 3.0, 7.0, -10.0, 19.0, 15.5)
        + box_centered(4.0, 3.0, 7.0, -10.0, 19.0, -19.5)
    )
    return front + ring + bridges


def build(source: Path, output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    smoothed_source = output_directory / "magicconch_smoothed_surface_v2.stl"
    smooth_shell(source, smoothed_source)

    # Deepen and widen the usable electronics cavity relative to V1.
    base.CAVITY_CENTER_X_MM = -7.0
    base.CAVITY_CENTER_Z_MM = -2.0
    base.CAVITY_RADIUS_X_MM = 42.0
    base.CAVITY_RADIUS_Z_MM = 20.5
    base.WALL_THICKNESS_MM = 3.0

    original = base.load_binary_stl(smoothed_source)
    main_shell = base.largest_component(original)
    bounds_min = main_shell.reshape(-1, 3).min(axis=0)
    bounds_max = main_shell.reshape(-1, 3).max(axis=0)
    center = (bounds_min + bounds_max) / 2.0
    scale = base.TARGET_LENGTH_MM / float(bounds_max[0] - bounds_min[0])
    scaled = (main_shell - center) * scale

    front_triangles, _ = base.build_half(scaled, front=True)
    back_triangles, _ = base.build_half(scaled, front=False)
    front_intermediate = output_directory / "MagicConch_FrontHousing_V2_base.stl"
    back_intermediate = output_directory / "MagicConch_BackHousing_V2_base.stl"
    base.write_binary_stl(front_intermediate, front_triangles, "Magic Conch V2 smooth front base")
    base.write_binary_stl(back_intermediate, back_triangles, "Magic Conch V2 smooth back base")

    front = to_manifold(front_intermediate)
    back = to_manifold(back_intermediate)
    print("base", front.status(), back.status(), flush=True)

    opening_cs = manifold3d.CrossSection([leaf_points().tolist()])
    opening = y_prism(opening_cs, 100.0, 0.0)
    string_passage = y_cylinder_segment(3.25, 100.0, 0.0, 0.0, 27.0)

    front = front - opening - string_passage
    print("openings", front.status(), flush=True)
    front = add_mesh_frame(front, opening_cs)
    print("mesh frame", front.status(), flush=True)

    for x, z in SNAP_POSITIONS_XZ:
        front = front + snap_post(x, z)
        back = back - snap_socket(x, z)
        print("snap", x, z, front.status(), back.status(), flush=True)

    # Small interior collar reinforces the real pull-string mechanism opening.
    string_outer = y_cylinder_segment(5.0, 2.0, 0.0, 18.0, 27.0)
    string_inner = y_cylinder_segment(3.25, 4.0, 0.0, 18.0, 27.0)
    front = front + (string_outer - string_inner)
    print("string collar", front.status(), flush=True)

    write_binary_stl(
        output_directory / "MagicConch_FrontHousing_V2_print.stl",
        front,
        "Magic Conch V2 front: smooth, leaf grille, split snaps",
    )
    write_binary_stl(
        output_directory / "MagicConch_BackHousing_V2_print.stl",
        back,
        "Magic Conch V2 back: smooth, snap sockets",
    )


def main() -> None:
    default_source = Path("reference/magicconch_smoothed_original.stl")
    if not default_source.exists():
        default_source = Path("magicconch_smoothed_original.stl")
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else default_source
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("prototype/v2")
    build(source, output)


if __name__ == "__main__":
    main()
