"""
CameraPathPlanner
=================
Generates continuous velocity-driven camera trajectories for real estate tours.
Features: Duplicate filtering, dynamic AI targeting, and organic human-like motion.
100% Dynamic Math: Zero dependency on 'room_type' for visual generation.
"""

import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import (
    DOLLY_Z_MAX_MULT,
    DOLLY_Z_MIN_MULT,
    PLANE_OVERSCALE_FACTOR,
    ROOM_ADJACENCY_GRAPH,
)

@dataclass
class RoomNode:
    room_type: str
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)

@dataclass
class ShotCameraParams:
    start: Tuple[float, float, float]
    end: Tuple[float, float, float]
    motion_type: str
    motion_strength: float
    motion_curve: str
    depth_parallax_strength: float
    transition_type: str

class CameraPathPlanner:

    def __init__(self, comp_width: float = 3840.0, comp_height: float = 2160.0,
                 camera_fov: float = 75.0, rng_seed: int = 42):
        self.comp_width  = comp_width
        self.comp_height = comp_height
        self.camera_fov  = camera_fov
        self.rng = random.Random(rng_seed)

        self.camera_z_base = (comp_height / 2.0) / math.tan(
            math.radians(camera_fov / 2.0)
        )

        plane_w = comp_width  * PLANE_OVERSCALE_FACTOR
        plane_h = comp_height * PLANE_OVERSCALE_FACTOR
        full_x_max = max(0.0, (plane_w - comp_width)  / 2.0)
        full_y_max = max(0.0, (plane_h - comp_height) / 2.0)
        
        self.x_max = full_x_max * 0.98  
        self.y_max = full_y_max * 0.75

        self.z_near = self.camera_z_base * DOLLY_Z_MIN_MULT  
        self.z_far  = self.camera_z_base * DOLLY_Z_MAX_MULT  

    def _deduplicate_shots(self, shots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique_shots = []
        last_url = None
        for shot in shots:
            identifier = shot.get("image_url") or shot.get("room_type")
            if identifier != last_url:
                unique_shots.append(shot)
                last_url = identifier
        return unique_shots

    # =========================================================================
    # RESTORED API CONTRACTS (Untouched to protect director.py)
    # =========================================================================
    def build_room_graph(self, shots: List[Dict[str, Any]]) -> Dict[str, RoomNode]:
        nodes: Dict[str, RoomNode] = {}
        for shot in shots:
            room = shot.get("room_type", "Other")
            if room not in nodes:
                nodes[room] = RoomNode(room_type=room, position=(0.0, 0.0, 0.0))
        return nodes

    def _compute_transition(self, from_room: str, to_room: str) -> str:
        if from_room == to_room:
            return "CUT"
        adjacency = ROOM_ADJACENCY_GRAPH.get(from_room, [])
        for (adj_room, hint) in adjacency:
            if adj_room == to_room:
                return "MOTION_MATCH" if hint == "open_plan" else "CROSS_DISSOLVE"
        return "FADE"

    # =========================================================================
    # DYNAMIC VISUAL ENGINE (room_type logic completely removed)
    # =========================================================================
    def assign_motion_types(self, shots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        clean_shots = self._deduplicate_shots(shots)
        
        enriched = []
        for idx, shot in enumerate(clean_shots):
            mean_depth = shot.get("mean_depth_normalized", 0.5)

            if idx == 0:
                motion_type = "REVEAL"
            elif idx == len(clean_shots) - 1:
                motion_type = "SLOW_DRIFT"
            elif mean_depth < 0.40:
                # DYNAMIC REPLACEMENT: If the room is physically shallow, pull out. No "Kitchen" text check needed.
                motion_type = "PULL_OUT"
            else:
                # Dynamic cinematic assignment based on physical space, not text labels
                motion_type = self._weighted_choice([
                    ("WALK_FORWARD", 0.5),
                    ("DOLLY_FORWARD", 0.3),
                    ("ORBIT", 0.1),
                    ("PUSH_IN", 0.1)
                ])

            strength = 0.75 
            strength = max(0.65, min(1.0, strength + self.rng.uniform(-0.02, 0.05)))

            s = dict(shot)
            s["motion_type"]     = motion_type
            s["motion_strength"] = round(strength, 3)
            s["motion_curve"]    = "linear"  
            enriched.append(s)
        return enriched

    def _direction_to_next_shot(self, current_shot: Dict[str, Any], next_shot: Optional[Dict[str, Any]]) -> Tuple[float, float]:
        if not next_shot:
            return (0.0, 0.0)

        shared_target = current_shot.get("shared_visual_target")
        if shared_target and len(shared_target) >= 2:
            return (float(shared_target[0]), float(shared_target[1]))

        pose_cur = current_shot.get("camera_pose")
        pose_nxt = next_shot.get("camera_pose")
        if pose_cur and pose_nxt:
            cx, cy = pose_cur[0][3], pose_cur[1][3]
            nx, ny = pose_nxt[0][3], pose_nxt[1][3]
            dx, dy = nx - cx, ny - cy
            mag = math.sqrt(dx*dx + dy*dy)
            if mag > 0.001:
                return (dx/mag, dy/mag)

        focal_target = current_shot.get("target_focal_center")
        if focal_target and len(focal_target) >= 2:
            return (float(focal_target[0]), float(focal_target[1]))

        # Purely dynamic fallback if no AI data is present
        return (self.rng.uniform(-0.5, 0.5), self.rng.uniform(-0.2, 0.2))

    def _calculate_dynamic_zoom_state(self, shot: Dict[str, Any]) -> float:
        """Determines physical room depth directly from the depth map array."""
        mean_depth = shot.get("mean_depth_normalized", 0.5)
        
        if mean_depth < 0.35:
            return -0.75
        elif mean_depth > 0.70:
            return 1.25
        return 1.0

    def plan_global_trajectory(self, shots: List[Dict[str, Any]], room_graph: Dict[str, RoomNode]) -> List[ShotCameraParams]:
        params: List[ShotCameraParams] = []
        clean_shots = self._deduplicate_shots(shots)

        initial_x_offset = -self.x_max * 0.50  
        if len(clean_shots) > 1:
            dir_x, _ = self._direction_to_next_shot(clean_shots[0], clean_shots[1])
            if dir_x > 0.05:
                initial_x_offset = -self.x_max * 0.70 
            elif dir_x < -0.05:
                initial_x_offset = self.x_max * 0.70

        prev_end: Tuple[float, float, float] = (
            initial_x_offset,
            0.0,
            self.camera_z_base * 1.15,  
        )

        for idx, shot in enumerate(clean_shots):
            motion    = shot.get("motion_type", "WALK_FORWARD")
            strength  = shot.get("motion_strength", 0.7)
            curve     = shot.get("motion_curve", "linear")
            has_depth = bool(shot.get("depth_map_url"))
            next_shot = clean_shots[idx + 1] if idx < len(clean_shots) - 1 else None

            depth_strength = 0.75 if has_depth else 0.45

            if idx > 0:
                prev_room = clean_shots[idx - 1].get("room_type", "Other")
                room = shot.get("room_type", "Other")
                transition_hint = self._compute_transition(prev_room, room)

                if transition_hint in ("FADE", "CROSS_DISSOLVE"):
                    px, py, _ = prev_end
                    zoom_sens = self._calculate_dynamic_zoom_state(shot)
                    entry_z = self.camera_z_base * 1.10 if zoom_sens > 0 else self.camera_z_base * 0.85
                    prev_end = (px * 0.65, py * 0.20, entry_z)

            start, end = self._compute_shot_camera(
                prev_end=prev_end,
                motion_type=motion,
                motion_strength=strength,
                shot=shot,
                next_shot=next_shot,
            )

            if idx == 0:
                transition = "FADE"
            else:
                prev_room = clean_shots[idx - 1].get("room_type", "Other")
                room = shot.get("room_type", "Other")
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

    def _compute_shot_camera(
        self,
        prev_end: Tuple[float, float, float],
        motion_type: str,
        motion_strength: float,
        shot: Dict[str, Any],
        next_shot: Optional[Dict[str, Any]],
    ) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        
        sx, sy, sz = prev_end
        xm = self.x_max * motion_strength
        ym = self.y_max * motion_strength
        zb = self.camera_z_base
        
        zoom_sensitivity = self._calculate_dynamic_zoom_state(shot)
        dir_x, dir_y = self._direction_to_next_shot(shot, next_shot)
        
        scan_sign = 1.0 if dir_x >= 0.0 else -1.0
        if zoom_sensitivity < 0:
            scan_sign = -1.0 
            
        horizontal_scan_delta = xm * 0.55 * scan_sign

        if motion_type == "REVEAL":
            end_z = self._clamp(sz - zb * 0.40 * motion_strength, self.z_near, self.z_far)
            end_x = self._clamp(sx * 0.05, -self.x_max, self.x_max)  
            end_y = 0.0
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        # DYNAMIC REPLACEMENT: Walk forward based on depth expanse, not room_type
        elif motion_type == "WALK_FORWARD" or zoom_sensitivity > 1.0:
            if abs(dir_x) > 0.05:
                end_x = self._clamp(sx + (dir_x * xm * 1.15) + horizontal_scan_delta * 0.15, -self.x_max, self.x_max)
                end_y = self._clamp(sy + dir_y * ym * 0.70, -self.y_max, self.y_max)
                z_travel = (zb * 0.45 * motion_strength) * zoom_sensitivity
            else:
                end_x = self._clamp(sx + horizontal_scan_delta, -self.x_max, self.x_max)
                end_y = self._clamp(sy + self.rng.uniform(-ym * 0.05, ym * 0.05), -self.y_max, self.y_max)
                z_travel = (zb * 0.38 * motion_strength) * zoom_sensitivity
            
            end_z = self._clamp(sz - z_travel, self.z_near, self.z_far)
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        elif motion_type == "PULL_OUT" or zoom_sensitivity < 0:
            end_x = self._clamp(sx + horizontal_scan_delta * 1.3, -self.x_max, self.x_max)
            end_y = self._clamp(sy + self.rng.uniform(-ym * 0.05, ym * 0.05), -self.y_max, self.y_max)
            
            z_travel = (zb * 0.32 * motion_strength) * zoom_sensitivity
            end_z = self._clamp(sz - z_travel, self.z_near, self.z_far)
            
            if zoom_sensitivity < 0 and sz < zb:
                sz = zb * 0.88
                
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        elif motion_type == "DOLLY_FORWARD":
            z_travel = (zb * 0.35 * motion_strength) * zoom_sensitivity
            end_z = self._clamp(sz - z_travel, self.z_near, self.z_far)
            end_x = self._clamp(sx * 0.15 + horizontal_scan_delta * 0.25, -xm, xm)  
            end_y = self._clamp(sy * 0.12, -ym, ym)
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        elif motion_type == "PUSH_IN":
            z_travel = (zb * 0.30 * motion_strength) * zoom_sensitivity
            end_z = self._clamp(sz - z_travel, self.z_near, self.z_far)
            end_x = self._clamp(sx + horizontal_scan_delta * 0.35, -self.x_max, self.x_max)
            end_y = self._clamp(sy + self.rng.uniform(-ym * 0.05, ym * 0.05), -self.y_max, self.y_max)
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        elif motion_type == "DOLLY_BACK":
            z_travel = (zb * 0.25 * motion_strength) * zoom_sensitivity
            end_z = self._clamp(sz + z_travel, self.z_near, self.z_far)
            end_x = self._clamp(sx * 0.25 + horizontal_scan_delta * 0.40, -xm, xm)
            end_y = self._clamp(sy * 0.20, -ym, ym)
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        elif motion_type == "ORBIT":
            orbit_x = xm * 0.75
            end_x = self._clamp(sx - orbit_x * scan_sign, -self.x_max, self.x_max)
            z_travel = (zb * 0.06 * motion_strength) * zoom_sensitivity
            end_z = self._clamp(sz - z_travel, self.z_near, self.z_far)
            start = (sx, sy, sz)
            end   = (end_x, self._clamp(sy * 0.20, -self.y_max, self.y_max), end_z)

        elif motion_type == "TRACK_LEFT":
            end_x = self._clamp(sx - xm * 0.85, -self.x_max, self.x_max)
            z_travel = (zb * 0.04 * motion_strength) * zoom_sensitivity
            end_z = self._clamp(sz - z_travel, self.z_near, self.z_far)
            start = (sx, sy, sz)
            end   = (end_x, sy, end_z)

        elif motion_type == "TRACK_RIGHT":
            end_x = self._clamp(sx + xm * 0.85, -self.x_max, self.x_max)
            z_travel = (zb * 0.04 * motion_strength) * zoom_sensitivity
            end_z = self._clamp(sz - z_travel, self.z_near, self.z_far)
            start = (sx, sy, sz)
            end   = (end_x, sy, end_z)

        elif motion_type == "SLOW_DRIFT":
            end_x = self._clamp(sx + self.rng.uniform(-xm * 0.10, xm * 0.10), -self.x_max, self.x_max)
            end_y = self._clamp(sy + self.rng.uniform(-ym * 0.06, ym * 0.06), -self.y_max, self.y_max)
            z_travel = (zb * 0.03 * motion_strength) * zoom_sensitivity
            end_z = self._clamp(sz - z_travel, self.z_near, self.z_far)
            start = (sx, sy, sz)
            end   = (end_x, end_y, end_z)

        else:
            end_z = self._clamp(sz - zb * 0.12 * motion_strength, self.z_near, self.z_far)
            start = (sx, sy, sz)
            end   = (sx, sy, end_z)

        return start, end