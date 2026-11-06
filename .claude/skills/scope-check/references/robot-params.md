# Robot parameters (scope-check reference)

Any UNREQUESTED or UNCLEAR change to a parameter in this file is CRITICAL. These values decide
where the pen goes, how fast it gets there, and whether the robot hits the bottle, the table or itself.

**Setup:** an ABB IRB 120 draws with a sharpie on a fixed, raised bottle or can that does not
rotate. The pen is held at an angle to joint 6, in a rigid or a spring-loaded holder. The work goes
from Grasshopper with Robot Components, to RAPID, to a RobotStudio simulation, to the real robot.
Units are millimetres and degrees.

The names below come from the Robot Components documentation, the team's example files in
`reference/`, and the ABB RAPID technical reference manual (RobotWare 6). GHPython scripts may use
other variable names for the same things; judge by meaning, not only by name.

## 1. Speed: speeddata
- Robot Components: **Speed Data** component (TCP Velocity `vTCP` in mm/s, ORI Velocity `vORI`, `vLEAX`, `vREAX`), or a number on the Speed Data input of **Move**. The Move component's optional Time input (`TI`) overrides the speed.
- RAPID: speed argument of `MoveL` / `MoveJ` / `MoveAbsJ`. Predefined values such as `v100` and `v200` (TCP speed in mm/s) or `vmax`. Custom `speeddata` declarations `[v_tcp, v_ori, v_leax, v_reax]`. The `\T` argument. `VelSet`.
- Risk: a faster pen presses, skips or smears on a curved surface, and a spring holder can bounce.

## 2. Precision: zonedata
- Robot Components: **Zone Data** component (Fine Point `FP`, Path Zone TCP `pzTCP`, `pzORI`, `zORI` and the rest), or a number on the Zone Data input of **Move** (`-1` means fine).
- RAPID: `fine`, `z0`, `z1`, `z10`, and custom `zonedata` (`pzone_tcp` is the zone radius in mm).
- Risk: `fine` stops on the target. A `zN` zone flies past it and cuts the corner inside the zone, so a bigger zone rounds strokes and drags the pen at pen-down and pen-up points.

## 3. Tool: tooldata, TCP, tool plane and pen angle
- Robot Components: **Robot Tool** (Name, Mesh, Attachment Plane `AP`, Tool Plane `TP`, Mass, Center of Gravity), **Override Robot Tool** on Move, and "Add tooldata" custom code in the team files.
- RAPID: `PERS tooldata <name> := [robhold, [[x, y, z], [q1, q2, q3, q4]], <loaddata>]`. `tframe.trans` is the pen tip (TCP) in mm from the flange. `tframe.rot` is its orientation, which holds the pen angle relative to joint 6. Also the tool argument of every move (`tool0` is the bare flange).
- Risk: a wrong TCP or angle shifts every target, so the pen goes into the bottle or misses it. Switching between the rigid and the spring holder changes the TCP.

## 4. Work object, reference plane and bottle position: wobjdata
- Robot Components: **Work Object** (Name, Plane `WP`). **Override Work Object** on Move (default `wobj0`). The Reference Plane input `RP` of **Robot Target** (**Set Reference Plane** in the team files). The Position Plane `PP` of the robot preset (robot base). Any plane, point or transform that places the bottle or can.
- RAPID: `wobjdata` `[robhold, ufprog, ufmec, uframe, oframe]`. `uframe` and `oframe` positions are in mm, with quaternion orientation. The `\WObj` argument of moves.
- Risk: targets live in the work object, so moving it moves the whole drawing. The robot then collides with the bottle or draws in the air.

## 5. Pen heights, offsets and approach
- Grasshopper or GHPython: pen-down depth or press-in, pen-up or retract height, approach and retreat distances, offset along the surface normal, safe or clearance height, spring compression.
- RAPID: `Offs(p, x, y, z)` (offset in the object coordinate system, mm), `RelTool(...)` (offset relative to the tool), approach and retreat moves, z values written directly into `robtarget`s.
- Risk: too low crushes the pen or holder into the surface. Too high draws nothing. A shorter approach removes the clearance around the bottle.

## 6. Motion type: MoveL, MoveJ, MoveAbsJ
- Robot Components: **Move** / **Movement**, input Movement Type `MT`: `0` MoveAbsJ, `1` MoveL, `2` MoveJ.
- RAPID: `MoveL` moves the TCP in a straight line. `MoveJ` interpolates joints, so the TCP path is not straight. `MoveAbsJ` goes to an absolute joint position; its end position ignores the tool, the work object and program displacement.
- Risk: changing MoveL to MoveJ with the pen down drags an arc across the surface, and MoveJ near the bottle can sweep through it.

## 7. Robot model: Robot Preset
- Robot Components: **Robot Preset** (`IRB120-3/0.58` in the team files; "Robot Preset Number" input), plus its Position Plane and Robot Tool inputs and the robot kinematic parameters.
- Risk: another preset means the kinematics, reach and generated RAPID no longer match the real IRB 120.

## 8. Configuration: confdata
- Robot Components: Axis Configuration `AC` (0 to 7) on **Robot Target**, **Configuration Data**, **Set Linear Configuration Control**, **Set Joint Configuration Control**.
- RAPID: `[cf1, cf4, cf6, cfx]` inside `robtarget`s (quadrants of axes 1, 4 and 6; `cfx` picks one of eight configurations). Also `ConfL \On|\Off`, `ConfJ \On|\Off` and `SingArea`.
- Risk: the same point is reached with a different arm posture. With configuration monitoring off, the manual warns of unexpected sweeping movements.

## 9. Home and start positions: Robot Joint Position
- Robot Components: **Robot Joint Position** (`RJ1` to `RJ6`, in degrees), then **Joint Target**, then **Move** with MoveAbsJ ("Define Home Position (Move AbsJ)" in the team files).
- RAPID: `jointtarget` data `[[j1, ..., j6], [external axes, 9E9 = not connected]]`, and `MoveAbsJ` to home.
- Risk: the first and last moves run before anything else is checked. A wrong home angle can hit the bottle or the table.

## 10. Work area limits and units
- Unit conversions (mm and m, degrees and radians, Rhino model units, scale factors), bounding boxes, reach or joint-limit checks, clamps, collision or clearance checks, and world zones (`WZBoxDef`, `WZLimSup`, ...).
- Risk: a silent scale error puts targets 1000 times off. Removing a limit lets unreachable or colliding targets through.

## Sources
- Robot Components documentation: Move, Speed Data, Zone Data, Robot Target, Robot Tool, Work Object, Robot Presets, Robot Joint Position, Joint Target, Set Linear Configuration Control.
- Team files in `reference/` (read only): `BASIC_05_Setup_of_robot_info_IRB120.gh` and `ITAR_Robot_Components_Introduction_1.gh`, for the names Robot Preset, `IRB120-3/0.58`, Set Reference Plane, Override Work Object, Movement and Configuration Data.
- ABB Technical reference manual, RAPID Instructions, Functions and Data types (RobotWare 6), PDF pages: ConfL 159, MoveAbsJ 398, Offs 1386, confdata 1651, speeddata 1763-1764, wobjdata 1815, zonedata 1822-1823.
