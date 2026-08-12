# Magic Conch enclosure prototype

This folder contains a first-pass, 3D-printable electronics enclosure derived from
`magicconch_smoothed_original.stl`. The original source mesh is preserved outside
this folder.

## Design assumptions

- Overall length: approximately 150 mm
- Overall assembled size: approximately 150 x 65 x 68 mm
- Two-piece split: front and back halves across the shell thickness
- Total seam clearance: 0.4 mm
- Nominal wall thickness: 3.0 mm, locally reduced where the original spiral is thin
- Speaker opening: 48 x 28 mm oval on the front half
- String passage: 6.5 mm diameter on the lower front area
- Closure: two 3.4 mm through-holes sized for prototype M3 hardware
- Original modeled string and pull ring: removed

The oval opening leaves an internal bonding surface for speaker cloth or perforated
mesh. Use epoxy, hot-melt adhesive, or a removable retaining frame after confirming
the selected speaker and mesh dimensions.

## Primary files

- `MagicConch_FrontHousing_print.stl` - front printable housing with speaker,
  string, and closure openings
- `MagicConch_BackHousing_print.stl` - back printable housing with closure openings
- `MagicConch_FrontHousing_preview.png` - front housing inspection render
- `MagicConch_BackHousing_preview.png` - back housing inspection render
- `magic_conch_front_prototype.stl` and `magic_conch_back_prototype.stl` - pre-cut
  watertight intermediate shells
- `solidworks_build.log` - SolidWorks automation log

## SolidWorks import

1. Open SolidWorks and choose **File > Open**.
2. Select one of the `*_print.stl` files.
3. Open **Options** in the file dialog.
4. Set units to **millimeters**.
5. Select **Solid body** with **Mesh BREP** enabled. If the standard BREP translator
   is slow, keep Mesh BREP enabled because each housing contains over 11,000 facets.
6. Open the file, then use **Save As** to create the corresponding `.SLDPRT` file.
7. Repeat for the second half.

For an assembly, mate the two planar seam faces parallel and center the two M3
closure holes. The 0.4 mm modeled separation supplies approximately 0.2 mm clearance
per half.

## Prototype warning

Print a low-infill fit-check before a final print. Component bosses and retainers
should be added after measuring the exact speaker, microphone, button, PCB, battery,
and pull-string mechanism.
