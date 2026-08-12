from __future__ import annotations

import sys
from pathlib import Path

import manifold3d
import numpy as np
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon,
    BRepBuilderAPI_MakeSolid,
    BRepBuilderAPI_Sewing,
)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.ShapeFix import ShapeFix_Shape
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt

from manifold_finalize import to_manifold


def manifold_arrays(solid: manifold3d.Manifold) -> tuple[np.ndarray, np.ndarray]:
    mesh = solid.to_mesh()
    vertices = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
    faces = np.asarray(mesh.tri_verts, dtype=np.int64)
    return vertices, faces


def build_brep(vertices: np.ndarray, faces: np.ndarray):
    sewing = BRepBuilderAPI_Sewing(1.0e-5, True, True, True, False)
    for index, triangle in enumerate(faces):
        polygon = BRepBuilderAPI_MakePolygon()
        for vertex_index in triangle:
            point = vertices[int(vertex_index)]
            polygon.Add(gp_Pnt(float(point[0]), float(point[1]), float(point[2])))
        polygon.Close()
        if not polygon.IsDone():
            raise ValueError(f"Wire failed at triangle {index}")
        face_maker = BRepBuilderAPI_MakeFace(polygon.Wire(), True)
        if not face_maker.IsDone():
            raise ValueError(f"Face failed at triangle {index}")
        sewing.Add(face_maker.Face())
    sewing.Perform()
    sewed = sewing.SewedShape()
    shell = TopoDS.Shell_s(sewed)
    solid_maker = BRepBuilderAPI_MakeSolid(shell)
    if not solid_maker.IsDone():
        raise ValueError("Solid construction failed")
    result = solid_maker.Solid()
    if not BRepCheck_Analyzer(result).IsValid():
        raise ValueError("OpenCASCADE reports an invalid solid")
    unifier = ShapeUpgrade_UnifySameDomain(result, True, True, True)
    unifier.Build()
    result = unifier.Shape()
    fixer = ShapeFix_Shape(result)
    fixer.Perform()
    result = fixer.Shape()
    if not BRepCheck_Analyzer(result).IsValid():
        raise ValueError("OpenCASCADE reports an invalid unified solid")
    return result


def write_step(shape, destination: Path) -> None:
    Interface_Static.SetCVal_s("write.step.schema", "AP214")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(str(destination))
    if status != IFSelect_RetDone:
        raise ValueError(f"STEP export failed with status {status}")


def convert(source: Path, destination: Path, tolerance: float) -> None:
    original = to_manifold(source)
    simplified = original.simplify(tolerance)
    vertices, faces = manifold_arrays(simplified)
    print(
        f"{source.name}: {original.num_tri()} -> {len(faces)} triangles "
        f"at {tolerance:.2f} mm tolerance",
        flush=True,
    )
    shape = build_brep(vertices, faces)
    write_step(shape, destination)
    print(f"Wrote {destination.resolve()}", flush=True)


def main() -> None:
    source = Path(sys.argv[1])
    destination = Path(sys.argv[2])
    tolerance = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
    convert(source, destination, tolerance)


if __name__ == "__main__":
    main()
