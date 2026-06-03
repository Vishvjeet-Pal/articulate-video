"""
CameraPathPlanner
=================
Generates camera start/end positions for every shot in the property tour.

Motion model:
  The camera simulates a person walking through the house holding a stabilized
  camera.  The CSS renderer (CinematicScene.tsx) converts camera [x, y, z] into
  CSS scale + translate, where:

    scale = camera_z_base / camera_z
    translate = -camera_x / (comp_width * OVERSCALE) * 100%

  Key behaviours:
    1. WALK_FORWARD toward next room: camera pans in the world-space direction of
       the next room (e.g. Kitchen is to the right → camera pans right) AND zooms
       in (Z decreases) simulating walking forward.
    2. DOLLY_FORWARD entering a room: strong Z zoom-in sweep as camera "enters"
       the new space and settles toward the center.
    3. Z RESET at room transitions: the black-dip transition (CROSS_DISSOLVE/FADE)
       covers any Z discontinuity, so each room can start fresh from a natural
       position.  XY partially carries over to maintain directional feel.
    4. Strong Z travel per shot: 20-30% per shot → 28-43% apparent zoom = clearly
       visible forward motion.
"""

import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import (
    CAMERA_MOTION_PRESETS,
    DOLLY_Z_MAX_MULT,
    DOLLY_Z_MIN_MULT,
    MOTION_STRENGTH_DEFAULTS,
    PLANE_OVERSCALE_FACTOR,
    ROOM_ADJACENCY_GRAPH,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RoomNode:
    room_type: str
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class RoomEdge:
    from_room: str
    to_room: str
    transition_hint: str = "doorway"


@dataclass
class ShotCameraParams:
    """Camera parameters for a single shot. Positions in world-space units."""
    start: Tuple[float, float, float]
    end: Tuple[float, float, float]
    motion_type: str
    motion_strength: float
    motion_curve: str
    depth_parallax_strength: float
    transition_type: str


# ---------------------------------------------------------------------------
# Room world-space positions (X = left-/right+, Y = down-/up+, Z = near/far)
# These define the spatial layout for the directional walk logic.
# Kitchen to the right of Living Room → WALK_FORWARD pans +X toward Kitchen.
# ---------------------------------------------------------------------------
_ROOM_WORLD_POSITIONS: Dict[str, Tuple[float, float, float]] = {
    "Exterior":         (0.0,   0.0,   0.0),
    "Living Room":      (0.0,   0.0,   5.0),
    "Kitchen":          (8.0,   0.0,   5.0),   # right of Living Room
    "Dining Room":      (4.0,   0.0,   3.0),
    "Primary Bedroom":  (-5.0,  0.0,  12.0),   # up the hallway, left
    "Other Bedrooms":   (5.0,   0.0,  12.0),
    "Primary Bathroom": (-5.0, -1.0,  15.0),
    "Other Bathrooms":  (5.0,  -1.0,  15.0),
    "Other":            (0.0,   0.0,   8.0),
}


class CameraPathPlanner:

    def __init__(self, comp_width: float = 3840.0, comp_height: float = 2160.0,
                 camera_fov: float = 75.0, rng_seed: int = 42):
        self.comp_width  = comp_width
        self.comp_height = comp_height
        self.camera_fov  = camera_fov
        self.rng = random.Random(rng_seed)

        # camera_z_base: distance at which image exactly fills the frame
        self.camera_z_base: float = (comp_height / 2.0) / math.tan(
            math.radians(camera_fov / 2.0)
        )

        # XY pan budget: fraction of the overscale margin
        plane_w = comp_width  * PLANE_OVERSCALE_FACTOR
        plane_h = comp_height * PLANE_OVERSCALE_FACTOR
        full_x_max = max(0.0, (plane_w - comp_width)  / 2.0)
        full_y_max = max(0.0, (plane_h - comp_height) / 2.0)
        self.x_max = full_x_max * 0.80   # 80% of margin = strong visible pan
        self.y_max = full_y_max * 0.60

        # Z bounds
        self.z_near = self.camera_z_base * DOLLY_Z_MIN_MULT  # closest (max zoom-in)
        self.z_far  = self.camera_z_base * DOLLY_Z_MAX_MULT  # farthest (max zoom-out)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_room_graph(self, shots: List[Dict[str, Any]]) -> Dict[str, RoomNode]:
        nodes: Dict[str, RoomNode] = {}
        for shot in shots:
            room = shot.get("room_type", "Other")
            if room not in nodes:
                pos = _ROOM_WORLD_POSITIONS.get(room, (0.0, 0.0, 8.0))
                nodes[room] = RoomNode(room_type=room, position=pos)
        return nodes

    def assign_motion_types(self, shots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Assigns motion_type to each shot based on narrative position.

          Shot 0        → REVEAL
          Last shot     → SLOW_DRIFT
          Just entered new room  → DOLLY_FORWARD (camera sweeps in)
          About to leave room    → WALK_FORWARD  (camera pans toward next room + zooms)
          Mid-room               → per-room weighted preset
        """
        enriched = []
        for idx, shot in enumerate(shots):
            room      = shot.get("room_type", "Other")
            prev_room = shots[idx - 1].get("room_type", "Other") if idx > 0 else None
            next_room = shots[idx + 1].get("room_type", "Other") if idx < len(shots) - 1 else None

            if idx == 0:
                motion_type = "REVEAL"
            elif idx == len(shots) - 1:
                motion_type = "SLOW_DRIFT"
            elif room != prev_room:
                # Just arrived in a new room — sweep inward
                motion_type = "DOLLY_FORWARD"
            elif next_room is not None and next_room != room:
                # About to leave — walk toward next room
                motion_type = "WALK_FORWARD"
            else:
                presets = CAMERA_MOTION_PRESETS.get(room, CAMERA_MOTION_PRESETS["Other"])
                motion_type = self._weighted_choice(presets)

            strength = MOTION_STRENGTH_DEFAULTS.get(motion_type, 0.6)
            strength = max(0.4, min(1.0, strength + self.rng.uniform(-0.10, 0.10)))

            s = dict(shot)
            s["motion_type"]    = motion_type
            s["motion_strength"] = round(strength, 3)
            s["motion_curve"]   = "easeInOutCubic"
            s["next_room"]      = next_room
            enriched.append(s)
        return enriched

    def plan_global_trajectory(
        self,
        shots: List[Dict[str, Any]],
        room_graph: Dict[str, RoomNode],
    ) -> List[ShotCameraParams]:
        params: List[ShotCameraParams] = []

        # First shot starts slightly off-axis (REVEAL sweeps to centre)
        prev_end: Tuple[float, float, float] = (
            self.x_max * 0.45,
            self.y_max * 0.15,
            self.camera_z_base * 1.20,   # start from wide/far for REVEAL
        )

        for idx, shot in enumerate(shots):
            room      = shot.get("room_type", "Other")
            motion    = shot.get("motion_type", "WALK_FORWARD")
            strength  = shot.get("motion_strength", 0.6)
            curve     = shot.get("motion_curve", "easeInOutCubic")
            has_depth = bool(shot.get("depth_map_url"))
            next_room = shot.get("next_room")

            depth_strength = 0.7 if has_depth else 0.4

            # -----------------------------------------------------------------
            # Z RESET at room transitions (CROSS_DISSOLVE / FADE).
            # The black-dip overlay covers the Z discontinuity so the viewer
            # never sees the jump.  This lets each room start from a natural
            # Z position rather than wherever the last room left off.
            # XY is partially carried over to maintain directional momentum.
            # -----------------------------------------------------------------
            if idx > 0:
                prev_room = shots[idx - 1].get("room_type", "Other")
                transition_hint = self._compute_transition(prev_room, room)

                if transition_hint in ("FADE", "CROSS_DISSOLVE"):
                    px, py, _ = prev_end
                    # Carry 40% of XY (direction carry-over), reset Z to entry position
                    entry_z = self.camera_z_base * 1.12   # slightly far = "just stepped in"
                    prev_end = (px * 0.40, py * 0.25, entry_z)

            start, end = self._compute_shot_camera(
                prev_end=prev_end,
                motion_type=motion,
                motion_strength=strength,
                room=room,
                next_room=next_room,
                room_graph=room_graph,
            )

            # Transition type
            if idx == 0:
                transition = "FADE"
            else:
                prev_room = shots[idx - 1].get("room_type", "Other")
                transition = self._compute_transition(prev_room, room)

            params.append(ShotCameraParams(
                start=start,
                end=end,
                motion_type=motion,
                motion_strength=strength,
                motion_curve=curve,
                depth_parallax_strength=depth_strength,
                transition_type=transition,
            ))

            prev_end = end

        return params

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clamp(self, v: float, lo: float, hi: float) -> float:
        return max(lo, min(v, hi))

    def _weighted_choice(self, presets: List[Tuple[str, float]]) -> str:
        types, weights = zip(*presets)
        total = sum(weights)
        r = self.rng.uniform(0, total)
        acc = 0.0
        for t, w in zip(types, weights):
            acc += w
            if r <= acc:
                return t
        return types[-1]

    def _direction_to_next_room(
        self,
        current_room: str,
        next_room: Optional[str],
    ) -> Tuple[float, float]:
        """
        Returns a normalised (dx, dy) direction vector from current_room → next_room.
        Used by WALK_FORWARD to pan the camera toward the next room.
        """
        if next_room is None:
            return (0.0, 0.0)
        cur  = _ROOM_WORLD_POSITIONS.get(current_room, (0.0, 0.0, 0.0))
        nxt  = _ROOM_WORLD_POSITIONS.get(next_room,    (0.0, 0.0, 0.0))
        dx, dy = nxt[0] - cur[0], nxt[1] - cur[1]
        mag = math.sqrt(dx * dx + dy * dy)
        if mag < 0.001:
            return (0.0, 0.0)
        return (dx / mag, dy / mag)

    def _compute_shot_camera(
        self,
        prev_end: Tuple[float, float, float],
        motion_type: str,
        motion_strength: float,
        room: str,
        next_room: Optional[str],
        room_graph: Dict[str, RoomNode],
    ) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        """
        Computes (start, end) camera [x, y, z] for one shot.

        CRITICAL: start is ALWAYS exactly prev_end — never clamped.
        Only end is bounded.  This guarantees shot[N].start == shot[N-1].end
        (within the same room sequence / after the Z reset above).

        Z dolly magnitudes:
          REVEAL       : z_far → z_base           (wide to neutral, 35% scale change)
          WALK_FORWARD : sz → sz - 25% * z_base   (~35% apparent zoom in)
          DOLLY_FORWARD: sz → sz - 28% * z_base   (entering room sweep, ~40% zoom)
          PUSH_IN      : sz → sz - 30% * z_base   (feature zoom)
          PULL_OUT     : sz → sz + 22% * z_base   (context reveal)
          ORBIT        : ±4% gentle breathe
          TRACK_*/SLOW : ±3% barely perceptible
        """
        sx, sy, sz = prev_end
        xm = self.x_max * motion_strength
        ym = self.y_max * motion_strength
        zb = self.camera_z_base

        if motion_type == "REVEAL":
            # First shot: sweep from off-axis/wide to centred/normal
            # sz is already at z_far (1.20*z_base) from the initial prev_end
            end_z = self._clamp(sz - zb * 0.25 * motion_strength, self.z_near, self.z_far)
            end_x = self._clamp(sx * 0.05, -self.x_max, self.x_max)   # settle to center
            end_y = 0.0
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        elif motion_type == "WALK_FORWARD":
            # THE MAIN WALKING MOTION.
            # Camera pans toward the next room AND zooms forward.
            # Combined effect: viewer feels they're physically walking toward the next space.
            dir_x, dir_y = self._direction_to_next_room(room, next_room)
            if abs(dir_x) > 0.05 or abs(dir_y) > 0.05:
                # Strong directional pan (85% of x_max in the room direction)
                end_x = self._clamp(sx + dir_x * xm * 0.85, -self.x_max, self.x_max)
                end_y = self._clamp(sy + dir_y * ym * 0.85, -self.y_max, self.y_max)
            else:
                # No clear direction — gentle drift
                end_x = self._clamp(sx + self.rng.uniform(-xm * 0.15, xm * 0.15), -self.x_max, self.x_max)
                end_y = self._clamp(sy + self.rng.uniform(-ym * 0.08, ym * 0.08), -self.y_max, self.y_max)
            # Strong Z forward (25% of z_base → ~33% apparent scale increase)
            end_z = self._clamp(sz - zb * 0.25 * motion_strength, self.z_near, self.z_far)
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        elif motion_type == "DOLLY_FORWARD":
            # Entering a new room: camera rushes forward + sweeps to center.
            # After Z reset, sz ≈ z_base * 1.12. This produces:
            #   scale_start = 1/1.12 = 0.89 (slightly wide)
            #   scale_end   = 1/(1.12 - 0.30) = 1/0.82 = 1.22 (22% zoom in)
            # The combination of entering-wide and zooming-in feels like stepping into a room.
            end_z = self._clamp(sz - zb * 0.30 * motion_strength, self.z_near, self.z_far)
            end_x = self._clamp(sx * 0.12, -xm, xm)   # sweep toward center
            end_y = self._clamp(sy * 0.12, -ym, ym)
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        elif motion_type == "PUSH_IN":
            # Feature shot: aggressive push toward the subject
            end_z = self._clamp(sz - zb * 0.30 * motion_strength, self.z_near, self.z_far)
            end_x = self._clamp(sx + self.rng.uniform(-xm * 0.12, xm * 0.12), -self.x_max, self.x_max)
            end_y = self._clamp(sy + self.rng.uniform(-ym * 0.08, ym * 0.08), -self.y_max, self.y_max)
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        elif motion_type == "PULL_OUT":
            # Withdraw to reveal context
            end_z = self._clamp(sz + zb * 0.22 * motion_strength, self.z_near, self.z_far)
            end_x = self._clamp(sx + self.rng.uniform(-xm * 0.12, xm * 0.12), -self.x_max, self.x_max)
            end_y = self._clamp(sy + self.rng.uniform(-ym * 0.08, ym * 0.08), -self.y_max, self.y_max)
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        elif motion_type == "DOLLY_BACK":
            end_z = self._clamp(sz + zb * 0.18 * motion_strength, self.z_near, self.z_far)
            end_x = self._clamp(sx * 0.3, -xm, xm)
            end_y = self._clamp(sy * 0.3, -ym, ym)
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        elif motion_type == "ORBIT":
            # Parametric arc around subject — gentle breathe on Z
            orbit_x = xm * 0.75
            end_x = self._clamp(sx - orbit_x, -self.x_max, self.x_max)
            end_z = self._clamp(sz - zb * 0.04 * motion_strength, self.z_near, self.z_far)
            start = (sx, sy, sz)
            end   = (end_x, self._clamp(sy * 0.3, -self.y_max, self.y_max), end_z)

        elif motion_type == "TRACK_LEFT":
            end_x = self._clamp(sx - xm * 0.85, -self.x_max, self.x_max)
            end_z = self._clamp(sz - zb * 0.03 * motion_strength, self.z_near, self.z_far)
            start = (sx, sy, sz)
            end   = (end_x, sy, end_z)

        elif motion_type == "TRACK_RIGHT":
            end_x = self._clamp(sx + xm * 0.85, -self.x_max, self.x_max)
            end_z = self._clamp(sz - zb * 0.03 * motion_strength, self.z_near, self.z_far)
            start = (sx, sy, sz)
            end   = (end_x, sy, end_z)

        elif motion_type == "SLOW_DRIFT":
            # Beauty/rest shot — barely visible movement
            end_x = self._clamp(sx + self.rng.uniform(-xm * 0.08, xm * 0.08), -self.x_max, self.x_max)
            end_y = self._clamp(sy + self.rng.uniform(-ym * 0.06, ym * 0.06), -self.y_max, self.y_max)
            end_z = self._clamp(sz - zb * 0.02 * motion_strength, self.z_near, self.z_far)
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        else:
            # Fallback: gentle push
            end_z = self._clamp(sz - zb * 0.08 * motion_strength, self.z_near, self.z_far)
            start = (sx, sy, sz)
            end   = (sx, sy, end_z)

        return start, end

    def _compute_transition(self, from_room: str, to_room: str) -> str:
        if from_room == to_room:
            return "CUT"
        adjacency = ROOM_ADJACENCY_GRAPH.get(from_room, [])
        for (adj_room, hint) in adjacency:
            if adj_room == to_room:
                return "MOTION_MATCH" if hint == "open_plan" else "CROSS_DISSOLVE"
        return "FADE"
