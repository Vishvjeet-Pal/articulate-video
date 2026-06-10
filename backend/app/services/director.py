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
        room_lower = str(room or "Other").strip().lower()
        if "pool" in room_lower:
            return "Pool"
        if any(token in room_lower for token in [
            "exterior", "entry", "facade", "front", "outdoor", "outside",
            "yard", "patio", "porch", "driveway", "garage"
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
        for key in ("room_type", "room", "room_name", "scene_type", "classification", "label"):
            value = photo.get(key)
            if value:
                return str(value)
        return "Other"

    def score_and_select_hero_shots(self, photos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique_photos = []
        seen_urls = set()

        for photo in photos:
            img_url = photo.get("image_url")
            if img_url:
                if img_url in seen_urls:
                    continue
                seen_urls.add(img_url)

            raw_room = self.get_room_label(photo)
            norm_room = self.normalize_room_type(raw_room)
            
            normalized_photo = dict(photo)
            normalized_photo["room_type"] = norm_room
            unique_photos.append(normalized_photo)

        MAX_TOTAL_SHOTS = 18 
        
        if len(unique_photos) <= MAX_TOTAL_SHOTS:
            return unique_photos

        room_groups = {}
        for idx, photo in enumerate(unique_photos):
            rt = photo["room_type"]
            if rt not in room_groups:
                room_groups[rt] = []
            room_groups[rt].append((idx, photo))

        budget = MAX_TOTAL_SHOTS
        allocation = {rt: 0 for rt in room_groups}
        room_keys = list(room_groups.keys())
        
        while budget > 0 and sum(allocation.values()) < len(unique_photos):
            for rt in room_keys:
                if allocation[rt] < len(room_groups[rt]) and budget > 0:
                    allocation[rt] += 1
                    budget -= 1

        selected_indices = set()
        for rt, alloc in allocation.items():
            group = room_groups[rt]
            if alloc == 0:
                continue
            if alloc == 1:
                selected_indices.add(group[0][0])
            else:
                for i in range(alloc):
                    idx_in_group = int(i * (len(group) - 1) / (alloc - 1))
                    selected_indices.add(group[idx_in_group][0])

        final_hero_shots = [photo for idx, photo in enumerate(unique_photos) if idx in selected_indices]
        return final_hero_shots

    def sequence_shots(self, hero_shots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return list(hero_shots)

    def allocate_screen_time(self, sequenced_shots: List[Dict[str, Any]], audio: AudioConfig) -> List[ShotNode]:
        room_graph = self.camera_planner.build_room_graph(sequenced_shots)
        shots_with_motion = self.camera_planner.assign_motion_types(sequenced_shots)
        camera_params_list = self.camera_planner.plan_global_trajectory(
            shots_with_motion, room_graph
        )

        # PDF Feature: Extract BPM for Beat Grid Snapping
        bpm = 120
        if audio:
            if hasattr(audio, 'bpm') and audio.bpm:
                bpm = audio.bpm
            elif isinstance(audio, dict) and audio.get('bpm'):
                bpm = float(audio.get('bpm'))
                
        # Calculate milliseconds per half-beat to snap transitions perfectly to the music
        half_beat_ms = (60000.0 / bpm) / 2.0

        # First pass: Calculate default durations with Emotional Arc Logic
        raw_durations = []
        room_seen_counts = {}
        
        for idx, shot in enumerate(shots_with_motion):
            room = shot.get("room_type", "Other")
            
            # Track how many times we've seen this room to apply Emotional Arc
            count = room_seen_counts.get(room, 0)
            room_seen_counts[room] = count + 1
            
            base_multiplier = ROOM_TIME_MULTIPLIERS.get(room, 1.0)
            
            # PDF Feature: Emotional Arc Pacing
            if count == 0:
                # 1. Establishing Shot: Slow, wide shot
                arc_multiplier = 1.3
            else:
                # 2. Detail Shot: Faster cut
                arc_multiplier = 0.7
                
            if idx == len(shots_with_motion) - 1:
                # 3. Final Impression: Very slow
                arc_multiplier = 1.6
                
            raw_durations.append(self.base_duration * base_multiplier * arc_multiplier)

        # Dynamic Time Compression
        total_raw = sum(raw_durations)
        compression_factor = 1.0
        if total_raw > MAX_VIDEO_DURATION_MS:
            compression_factor = MAX_VIDEO_DURATION_MS / total_raw

        nodes = []
        for idx, (shot, cam, raw_dur) in enumerate(zip(shots_with_motion, camera_params_list, raw_durations)):
            room = shot.get("room_type", "Other")
            
            # Apply compression factor
            compressed_duration = raw_dur * compression_factor
            
            # PDF Feature: Snap the duration to the nearest music beat
            snapped_duration = round(compressed_duration / half_beat_ms) * half_beat_ms
            
            # Final safety clamp
            duration = int(max(MIN_SHOT_DURATION_MS, min(snapped_duration, MAX_SHOT_DURATION_MS)))

            crop_16_9 = "1080:1920:420:0"
            crop_9_16 = "1080:1920:420:0"
            crop_1_1  = "1080:1080:420:420"

            nodes.append(ShotNode(
                image_url=shot.get("image_url", ""),
                depth_map_url=shot.get("depth_map_url", None),
                room_type=room,
                duration_ms=duration,
                motion_type=cam.motion_type,
                motion_strength=cam.motion_strength,
                motion_curve=cam.motion_curve,
                depth_parallax_strength=cam.depth_parallax_strength,
                camera_start_target=list(cam.start),
                camera_end_target=list(cam.end),
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
        
        # Pass audio config to the time allocator to sync to the beat
        nodes = self.allocate_screen_time(sequenced, audio)

        total_duration = sum(node.duration_ms for node in nodes)

        return RemotionInputProps(
            tour_type=self.tour_type,       # type: ignore
            pacing_speed=self.pacing_speed, # type: ignore
            audio_config=audio,
            branding=branding,
            timeline=nodes,
            total_duration_ms=total_duration,
        )