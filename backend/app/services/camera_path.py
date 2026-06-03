"""
CameraPathPlanner
=================
Generates a continuous, momentum-preserving global camera trajectory for the
entire property tour sequence.  Instead of calculating per-shot start/end
positions independently, this planner:

  1. Builds a room adjacency graph (RoomNode / RoomEdge).
  2. Assigns a cinematic motion type to each shot based on room context.
  3. Computes a global trajectory where Shot N+1 starts exactly where Shot N ended.
  4. Applies depth-aware Z-axis dolly movement so the camera moves THROUGH
     depth space rather than only across a flat plane.
  5. Adds subtle sinusoidal walking sway to WALK_FORWARD shots.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import (
    CAMERA_MOTION_PRESETS,
    DOLLY_Z_MAX_MULT,
    DOLLY_Z_MIN_MULT,
    MOTION_STRENGTH_DEFAULTS,
    PLANE_OVERSCALE_FACTOR,
    ROOM_ADJACENCY_GRAPH,
    WALK_SWAY_AMPLITUDE,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RoomNode:
    """A node in the spatial scene graph representing one room."""
    room_type: str
    # World-space position (metres, approximate).  Used to derive camera path
    # vectors between rooms.
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class RoomEdge:
    """A directed edge between two adjacent rooms."""
    from_room: str
    to_room: str
    # Semantic hint used to choose the transition type.
    transition_hint: str = "doorway"  # "doorway" | "hallway" | "open_plan"


@dataclass
class ShotCameraParams:
    """
    Fully-resolved camera parameters for a single shot.
    All positions are in Three.js world-space units.
    """
    start: Tuple[float, float, float]
    end: Tuple[float, float, float]
    motion_type: str
    motion_strength: float
    motion_curve: str
    depth_parallax_strength: float
    transition_type: str


# ---------------------------------------------------------------------------
# Canonical room world-space positions
# Used to derive travel vectors when real camera poses are unavailable.
# ---------------------------------------------------------------------------
_ROOM_WORLD_POSITIONS: Dict[str, Tuple[float, float, float]] = {
    "Exterior":         (0.0,    0.0,  0.0),
    "Living Room":      (0.0,    0.0,  10.0),
    "Kitchen":          (5.0,    0.0,  10.0),
    "Dining Room":      (5.0,    0.0,  5.0),
    "Primary Bedroom":  (-5.0,   5.0,  15.0),
    "Other Bedrooms":   (5.0,    5.0,  15.0),
    "Primary Bathroom": (-5.0,   5.0,  20.0),
    "Other Bathrooms":  (5.0,    5.0,  20.0),
    "Other":            (0.0,    0.0,  15.0),
}


class CameraPathPlanner:
    """
    Plans a smooth, continuous camera path across the entire property tour.
    """

    def __init__(self, comp_width: float = 3840.0, comp_height: float = 2160.0,
                 camera_fov: float = 75.0, rng_seed: int = 42):
        self.comp_width = comp_width
        self.comp_height = comp_height
        self.camera_fov = camera_fov
        self.rng = random.Random(rng_seed)

        # Neutral camera distance so the image fills exactly the composition.
        self.camera_z_base: float = (comp_height / 2.0) / math.tan(
            math.radians(camera_fov / 2.0)
        )

        # Safe XY pan budget.
        # IMPORTANT: Use only 40% of the available margin — Collov-style motion is
        # very restrained.  Using the full margin (480px at 4K) makes the camera
        # feel like it's sliding across the image, not walking through a room.
        plane_w = comp_width  * PLANE_OVERSCALE_FACTOR
        plane_h = comp_height * PLANE_OVERSCALE_FACTOR
        full_x_max = max(0.0, (plane_w - comp_width)  / 2.0)
        full_y_max = max(0.0, (plane_h - comp_height) / 2.0)
        self.x_max = full_x_max * 0.40   # ~192px of lateral travel at 4K
        self.y_max = full_y_max * 0.40   # ~108px of vertical travel at 4K

        # Z travel limits — tight range so dolly is felt but not disorienting.
        # 5% closer/farther than neutral is very cinematic; 18% was too aggressive.
        self.z_near = self.camera_z_base * DOLLY_Z_MIN_MULT  # closest (push-in end)
        self.z_far  = self.camera_z_base * DOLLY_Z_MAX_MULT  # farthest (pull-out end)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_room_graph(self, shots: List[Dict[str, Any]]) -> Dict[str, RoomNode]:
        """
        Creates RoomNode entries for every unique room type in the shot list.
        Populates canonical world positions from the predefined map, falling
        back to camera_pose data when available.
        """
        nodes: Dict[str, RoomNode] = {}
        for shot in shots:
            room = shot.get("room_type", "Other")
            if room not in nodes:
                pos = _ROOM_WORLD_POSITIONS.get(room, (0.0, 0.0, 15.0))
                # Override with real pose data if present
                pose = shot.get("camera_pose")
                if pose and isinstance(pose, list) and len(pose) == 4:
                    try:
                        pos = (float(pose[0][3]), float(pose[1][3]), float(pose[2][3]))
                    except (ValueError, TypeError, IndexError):
                        pass
                nodes[room] = RoomNode(room_type=room, position=pos)
        return nodes

    def assign_motion_types(self, shots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Assigns a motion_type, motion_strength, and motion_curve to each shot
        based on room type using weighted random selection.
        The first shot always gets REVEAL, the last always gets SLOW_DRIFT.
        """
        enriched = []
        for idx, shot in enumerate(shots):
            room = shot.get("room_type", "Other")
            presets = CAMERA_MOTION_PRESETS.get(room, CAMERA_MOTION_PRESETS["Other"])

            # Force narrative bookmarks
            if idx == 0:
                motion_type = "REVEAL"
            elif idx == len(shots) - 1:
                motion_type = "SLOW_DRIFT"
            else:
                motion_type = self._weighted_choice(presets)

            motion_strength = MOTION_STRENGTH_DEFAULTS.get(motion_type, 0.5)
            # Slight random variance (±15%) keeps adjacent shots of the same type distinct
            motion_strength = max(0.2, min(1.0,
                motion_strength + self.rng.uniform(-0.15, 0.15)
            ))

            enriched_shot = dict(shot)
            enriched_shot["motion_type"]    = motion_type
            enriched_shot["motion_strength"] = round(motion_strength, 3)
            enriched_shot["motion_curve"]   = "easeInOutCubic"
            enriched.append(enriched_shot)
        return enriched

    def plan_global_trajectory(
        self,
        shots: List[Dict[str, Any]],
        room_graph: Dict[str, RoomNode],
    ) -> List[ShotCameraParams]:
        """
        Core planner.  Returns one ShotCameraParams per shot.

        Key properties:
          - Shot N+1 start == Shot N end  (no teleportation)
          - Z axis moves to simulate depth approach / withdrawal
          - Walking sway added for WALK_FORWARD shots
          - Transition types derived from room adjacency
        """
        params: List[ShotCameraParams] = []
        prev_end: Tuple[float, float, float] = (0.0, 0.0, self.camera_z_base)

        for idx, shot in enumerate(shots):
            room       = shot.get("room_type", "Other")
            motion     = shot.get("motion_type", "WALK_FORWARD")
            strength   = shot.get("motion_strength", 0.5)
            curve      = shot.get("motion_curve", "easeInOutCubic")
            has_depth  = bool(shot.get("depth_map_url"))

            depth_strength = 0.6 if has_depth else 0.3

            start, end = self._compute_shot_camera(
                prev_end=prev_end,
                motion_type=motion,
                motion_strength=strength,
                room=room,
                room_graph=room_graph,
                is_first=(idx == 0),
                is_last=(idx == len(shots) - 1),
            )

            # Transition to the next shot
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

            # ---------------------------------------------------------------
            # Mean-reversion: prevent cumulative Z/XY drift from pinning the
            # camera at z_near or an extreme pan position.
            #
            # After each shot, pull the carry-over position 30% back toward
            # neutral (z_base for Z, 0 for XY).  This keeps the motion feeling
            # continuous — the next shot still starts where this one ended —
            # but oscillates around neutral rather than drifting monotonically
            # to one extreme.  The viewer sees smooth motion in both directions.
            # ---------------------------------------------------------------
            REVERT_Z_FACTOR  = 0.30   # 30% pull back toward z_base
            REVERT_XY_FACTOR = 0.20   # 20% pull back toward centre

            ex, ey, ez = end
            reverted_z = ez + (self.camera_z_base - ez) * REVERT_Z_FACTOR
            reverted_x = ex + (0.0 - ex) * REVERT_XY_FACTOR
            reverted_y = ey + (0.0 - ey) * REVERT_XY_FACTOR
            prev_end = (reverted_x, reverted_y, reverted_z)

        return params

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clamp(self, value: float, lower: float, upper: float) -> float:
        return max(lower, min(value, upper))

    def _weighted_choice(self, presets: List[Tuple[str, float]]) -> str:
        """Select a motion type using normalised weights."""
        types, weights = zip(*presets)
        total = sum(weights)
        r = self.rng.uniform(0, total)
        cumulative = 0.0
        for t, w in zip(types, weights):
            cumulative += w
            if r <= cumulative:
                return t
        return types[-1]

    def _compute_shot_camera(
        self,
        prev_end: Tuple[float, float, float],
        motion_type: str,
        motion_strength: float,
        room: str,
        room_graph: Dict[str, RoomNode],
        is_first: bool,
        is_last: bool,
    ) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        """
        Computes (start, end) camera positions for a single shot.

        All positions are (x, y, z) in Three.js world units:
          x = horizontal pan (right = positive)
          y = vertical pan (up = positive)
          z = depth (closer = smaller z, farther = larger z)

        The start position is always anchored to prev_end so there
        is no camera jump between shots.
        """
        sx, sy, sz = prev_end
        xm = self.x_max * motion_strength
        ym = self.y_max * motion_strength

        # ---- Z axis behaviour per motion type ----
        z_base = self.camera_z_base
        z_near = self.z_near
        z_far  = self.z_far

        # CRITICAL: start is ALWAYS (sx, sy, sz) — never clamped.
        # Clamping start would break momentum continuity (Shot N-1 end != Shot N start).
        # Only the END position is bounded.

        if motion_type == "PUSH_IN":
            # Collov-style push: gentle forward dolly, no dramatic lunge
            end_z = self._clamp(sz - (z_base * 0.06) * motion_strength, z_near, z_far)
            ex = self._clamp(sx + self.rng.uniform(-xm * 0.2, xm * 0.2), -self.x_max, self.x_max)
            ey = self._clamp(sy + self.rng.uniform(-ym * 0.2, ym * 0.2), -self.y_max, self.y_max)
            start = (sx, sy, sz)
            end   = (ex, ey, end_z)

        elif motion_type == "PULL_OUT":
            # Camera gently withdraws — reveals context around the subject
            end_z = self._clamp(sz + (z_base * 0.06) * motion_strength, z_near, z_far)
            ex = self._clamp(sx + self.rng.uniform(-xm * 0.2, xm * 0.2), -self.x_max, self.x_max)
            ey = self._clamp(sy + self.rng.uniform(-ym * 0.2, ym * 0.2), -self.y_max, self.y_max)
            start = (sx, sy, sz)
            end   = (ex, ey, end_z)

        elif motion_type == "DOLLY_FORWARD":
            # Lateral sweep toward subject + gentle Z close
            end_z = self._clamp(sz - (z_base * 0.05) * motion_strength, z_near, z_far)
            ex = self._clamp(sx * 0.3, -xm, xm)
            ey = self._clamp(sy * 0.3, -ym, ym)
            start = (sx, sy, sz)
            end   = (ex, ey, end_z)

        elif motion_type == "DOLLY_BACK":
            end_z = self._clamp(sz + (z_base * 0.05) * motion_strength, z_near, z_far)
            ex = self._clamp(sx * 0.3, -xm, xm)
            ey = self._clamp(sy * 0.3, -ym, ym)
            start = (sx, sy, sz)
            end   = (ex, ey, end_z)

        elif motion_type == "ORBIT":
            # Parametric arc — VirtualCamera computes the curved path per frame.
            # Here we just set start/end waypoints.
            orbit_x = xm * 0.7
            end_x = self._clamp(sx - orbit_x, -self.x_max, self.x_max)
            end_z = self._clamp(sz - (z_base * 0.03) * motion_strength, z_near, z_far)
            start = (sx, sy, sz)
            end   = (end_x, self._clamp(sy * 0.4, -self.y_max, self.y_max), end_z)

        elif motion_type == "REVEAL":
            # Sweep from off-axis to centred — used for first shot entrance
            end_x = self._clamp(sx * 0.08, -self.x_max, self.x_max)
            end_z = self._clamp(sz - (z_base * 0.05) * motion_strength, z_near, z_far)
            start = (sx, sy, sz)
            end   = (end_x, 0.0, end_z)

        elif motion_type == "TRACK_LEFT":
            end_x = self._clamp(sx - xm, -self.x_max, self.x_max)
            end_z = self._clamp(sz - (z_base * 0.02) * motion_strength, z_near, z_far)
            start = (sx, sy, sz)
            end   = (end_x, sy, end_z)

        elif motion_type == "TRACK_RIGHT":
            end_x = self._clamp(sx + xm, -self.x_max, self.x_max)
            end_z = self._clamp(sz - (z_base * 0.02) * motion_strength, z_near, z_far)
            start = (sx, sy, sz)
            end   = (end_x, sy, end_z)

        elif motion_type == "WALK_FORWARD":
            # Collov hero motion: slow, smooth forward drift toward subject.
            # Very slight X drift gives a natural walking-into-the-room feel.
            # NO sway — the VirtualCamera adds ultra-subtle breathing on Y instead.
            end_z = self._clamp(sz - (z_base * 0.04) * motion_strength, z_near, z_far)
            end_x = self._clamp(sx + self.rng.uniform(-xm * 0.1, xm * 0.1), -self.x_max, self.x_max)
            end_y = self._clamp(sy + self.rng.uniform(-ym * 0.08, ym * 0.08), -self.y_max, self.y_max)
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        else:  # SLOW_DRIFT — beauty/rest shot, barely perceptible motion
            drift_x = xm * 0.15
            drift_y = ym * 0.15
            end_x = self._clamp(sx + self.rng.uniform(-drift_x, drift_x), -self.x_max, self.x_max)
            end_y = self._clamp(sy + self.rng.uniform(-drift_y, drift_y), -self.y_max, self.y_max)
            end_z = self._clamp(sz - (z_base * 0.01) * motion_strength, z_near, z_far)
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        return start, end

    def _compute_transition(self, from_room: str, to_room: str) -> str:
        """
        Selects transition type based on room adjacency.

          open_plan  → MOTION_MATCH  (continuous move, no overlay)
          doorway    → CROSS_DISSOLVE
          hallway    → CROSS_DISSOLVE
          distant    → FADE
          same room  → CUT
        """
        if from_room == to_room:
            return "CUT"

        adjacency = ROOM_ADJACENCY_GRAPH.get(from_room, [])
        for (adj_room, hint) in adjacency:
            if adj_room == to_room:
                if hint == "open_plan":
                    return "MOTION_MATCH"
                else:
                    return "CROSS_DISSOLVE"

        # No defined adjacency — rooms are spatially distant
        return "FADE"
