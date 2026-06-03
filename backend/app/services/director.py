import math
from typing import List, Dict, Any
from app.schemas.remotion import (
    RemotionInputProps, ShotNode, AudioConfig, BrandingConfig,
    ProceduralMotionTarget, UpstreamPose, UpstreamDepth, UpstreamSaliency
)
from app.core.config import (
    MIN_VIDEO_DURATION_MS, MAX_VIDEO_DURATION_MS,
    MIN_SHOT_DURATION_MS, MAX_SHOT_DURATION_MS,
    ROOM_IMPORTANCE_HIERARCHY, ROOM_TIME_MULTIPLIERS,
    PACING_BASE_DURATION, SOCIAL_RATIOS,
    PLANE_OVERSCALE_FACTOR, PUSH_IN_START_MULT, PUSH_IN_END_MULT,
    PULL_BACK_START_MULT, PULL_BACK_END_MULT,
    MAX_SHOTS_PER_ROOM,
)
from app.services.camera_path import CameraPathPlanner


class DirectorService:
    def __init__(self, tour_type: str, pacing_speed: str):
        self.tour_type = tour_type
        self.pacing_speed = pacing_speed
        self.base_duration = PACING_BASE_DURATION.get(pacing_speed, 5000)
        self.camera_planner = CameraPathPlanner()

    def normalize_room_type(self, room: str) -> str:
        """
        Robustly normalizes raw room strings to standard types in ROOM_IMPORTANCE_HIERARCHY.
        """
        room_lower = str(room or "Other").strip().lower()
        if any(token in room_lower for token in [
            "exterior", "entry", "facade", "front", "outdoor", "outside",
            "yard", "patio", "porch", "driveway", "garage", "pool"
        ]):
            return "Exterior"
        if any(token in room_lower for token in ["living", "family room", "great room", "lounge"]):
            return "Living Room"
        if "kitchen" in room_lower:
            return "Kitchen"
        if "dining" in room_lower:
            return "Dining Room"
        if "primary bedroom" in room_lower or "master bedroom" in room_lower:
            return "Primary Bedroom"
        if "bedroom" in room_lower:
            return "Other Bedrooms"
        if "primary bathroom" in room_lower or "primary bath" in room_lower or "master bath" in room_lower:
            return "Primary Bathroom"
        if "bathroom" in room_lower or "bath" in room_lower:
            return "Other Bathrooms"
        return "Other"

    def get_room_label(self, photo: Dict[str, Any]) -> str:
        """
        Accepts common upstream detection field names so valid exterior/living
        classifications are not silently collapsed into Other.
        """
        for key in ("room_type", "room", "room_name", "scene_type", "classification", "label"):
            value = photo.get(key)
            if value:
                return str(value)
        return "Other"

    def score_and_select_hero_shots(self, photos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalises room labels and enforces a per-room cap of MAX_SHOTS_PER_ROOM
        to avoid repetitive sequences (e.g. 6 nearly-identical bedroom shots).

        Scoring is currently based on upload order (first photos per room are kept).
        When quality / saliency metadata is available upstream it can be wired in here.
        """
        room_counts: Dict[str, int] = {}
        hero_shots = []

        for photo in photos:
            raw_room = self.get_room_label(photo)
            norm_room = self.normalize_room_type(raw_room)

            count = room_counts.get(norm_room, 0)
            if count >= MAX_SHOTS_PER_ROOM:
                continue  # Drop excess shots for this room

            normalized_photo = dict(photo)
            normalized_photo["room_type"] = norm_room
            hero_shots.append(normalized_photo)
            room_counts[norm_room] = count + 1

        return hero_shots

    def sequence_shots(self, hero_shots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enforces narrative ordering (Exterior → Living → Private → Amenities).
        Within the same room bucket, preserves upload order.
        """
        def get_sort_key(indexed_shot):
            original_index, shot = indexed_shot
            room = shot.get("room_type", "Other")
            try:
                room_rank = ROOM_IMPORTANCE_HIERARCHY.index(room)
            except ValueError:
                room_rank = len(ROOM_IMPORTANCE_HIERARCHY)
            return (room_rank, original_index)

        sequenced = []
        for _, shot in sorted(enumerate(hero_shots), key=get_sort_key):
            sequenced.append(dict(shot))
        return sequenced

    def allocate_screen_time(self, sequenced_shots: List[Dict[str, Any]]) -> List[ShotNode]:
        """
        Assigns durations, camera trajectories, and motion types to every shot.

        The key architectural change vs. the previous version:
          - CameraPathPlanner generates a CONTINUOUS global trajectory so
            each shot starts exactly where the previous one ended.
          - Z-axis movement is now live — the camera dollies forward/back
            based on the assigned motion_type.
          - Motion types, easing curves, and depth parallax strength are
            computed by CameraPathPlanner and stored on every ShotNode.
        """
        # --- Step 1: build room graph for adjacency / transition decisions ---
        room_graph = self.camera_planner.build_room_graph(sequenced_shots)

        # --- Step 2: assign motion types per shot ---
        shots_with_motion = self.camera_planner.assign_motion_types(sequenced_shots)

        # --- Step 3: compute global camera trajectory ---
        camera_params_list = self.camera_planner.plan_global_trajectory(
            shots_with_motion, room_graph
        )

        # --- Step 4: build ShotNode list ---
        nodes = []
        for idx, (shot, cam) in enumerate(zip(shots_with_motion, camera_params_list)):
            room = shot.get("room_type", "Other")
            multiplier = ROOM_TIME_MULTIPLIERS.get(room, 1.0)

            # Emotional arc pacing: first and last shots are 1.2× longer
            if idx == 0 or idx == len(shots_with_motion) - 1:
                multiplier *= 1.2

            duration = int(self.base_duration * multiplier)
            duration = max(MIN_SHOT_DURATION_MS, min(duration, MAX_SHOT_DURATION_MS))

            # Mock saliency crops (placeholder — replace with real saliency data)
            crop_16_9 = "1080:1920:420:0"
            crop_9_16 = "1080:1920:420:0"
            crop_1_1  = "1080:1080:420:420"

            nodes.append(ShotNode(
                image_url=shot.get("image_url", ""),
                depth_map_url=shot.get("depth_map_url", None),
                room_type=room,
                duration_ms=duration,

                # Cinematic motion parameters from CameraPathPlanner
                motion_type=cam.motion_type,
                motion_strength=cam.motion_strength,
                motion_curve=cam.motion_curve,
                depth_parallax_strength=cam.depth_parallax_strength,

                # Globally-continuous camera positions (Shot N end == Shot N+1 start)
                camera_start_target=list(cam.start),
                camera_end_target=list(cam.end),

                # Transition type derived from room adjacency graph
                transition_type=cam.transition_type,

                camera_path={"type": "cinematic", "motion": cam.motion_type},
                procedural_motion_targets=[],
                saliency_crop_16_9=crop_16_9,
                saliency_crop_9_16=crop_9_16,
                saliency_crop_1_1=crop_1_1,
            ))

        return nodes

    def build_director_script(
        self,
        photos: List[Dict[str, Any]],
        audio: AudioConfig,
        branding: BrandingConfig,
    ) -> RemotionInputProps:
        hero_shots = self.score_and_select_hero_shots(photos)
        sequenced  = self.sequence_shots(hero_shots)
        nodes      = self.allocate_screen_time(sequenced)

        total_duration = sum(node.duration_ms for node in nodes)

        return RemotionInputProps(
            tour_type=self.tour_type,       # type: ignore
            pacing_speed=self.pacing_speed, # type: ignore
            audio_config=audio,
            branding=branding,
            timeline=nodes,
            total_duration_ms=total_duration,
        )
