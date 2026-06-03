from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Tuple, Dict, Any

class UpstreamPose(BaseModel):
    image_id: str
    camera_pose: List[List[float]]  # 4x4 matrix

class UpstreamDepth(BaseModel):
    image_id: str
    depth_map_url: str

class UpstreamSaliency(BaseModel):
    image_id: str
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    focal_center: Tuple[int, int]    # x, y

class AudioConfig(BaseModel):
    bgm_url: Optional[str] = None
    voiceover_url: Optional[str] = None
    volume_balance: float = Field(default=0.5, ge=0.0, le=1.0)

class BrandingConfig(BaseModel):
    brokerage_overlay_url: Optional[str] = None
    logo_mapping: Literal["CORNER", "LOWER_THIRD"] = "CORNER"
    primary_color_hex: str = "#000000"
    secondary_color_hex: str = "#FFFFFF"

class ProceduralMotionTarget(BaseModel):
    mask_id: str
    type: Literal["FOLIAGE_SWAY", "WATER_DISPLACEMENT", "FABRIC_WARP"]
    intensity: float = Field(default=1.0, ge=0.0, le=5.0)

class ShotNode(BaseModel):
    image_url: str
    depth_map_url: Optional[str] = None
    room_type: str
    duration_ms: int

    # --- Cinematic motion type for this shot ---
    # Controls how the virtual camera moves during this shot.
    motion_type: Literal[
        "PUSH_IN", "PULL_OUT", "DOLLY_FORWARD", "DOLLY_BACK",
        "ORBIT", "REVEAL", "TRACK_LEFT", "TRACK_RIGHT",
        "WALK_FORWARD", "SLOW_DRIFT"
    ] = "WALK_FORWARD"

    # 0.0 = minimal movement, 1.0 = maximum travel for the motion type
    motion_strength: float = Field(default=0.5, ge=0.0, le=1.0)

    # Easing curve applied to the camera interpolation
    motion_curve: Literal["easeInOutCubic", "easeIn", "easeOut", "linear"] = "easeInOutCubic"

    # 0.0 = flat image, 1.0 = full depth-map-driven parallax separation
    depth_parallax_strength: float = Field(default=0.4, ge=0.0, le=1.0)

    # Extended transition type — MOTION_MATCH preserves camera velocity into next shot
    transition_type: Literal["PAN", "FADE", "CUT", "MOTION_MATCH", "CROSS_DISSOLVE"] = "CUT"

    # Path or Parallax parameters depending on upstream data availability
    camera_path: Optional[Dict[str, Any]] = None

    procedural_motion_targets: List[ProceduralMotionTarget] = []

    # Crop parameters pre-calculated for social derivatives (W:H:X:Y)
    saliency_crop_16_9: Optional[str] = None
    saliency_crop_9_16: Optional[str] = None
    saliency_crop_1_1: Optional[str] = None

    # Spatially-aware cinematography coordinates (x, y, z in Three.js world units).
    # These are the GLOBAL trajectory positions — Shot N+1's start == Shot N's end.
    camera_start_target: List[float] = Field(default_factory=lambda: [0.0, 0.0, 1407.5])
    camera_end_target: List[float] = Field(default_factory=lambda: [0.0, 0.0, 1337.1])

class RemotionInputProps(BaseModel):
    tour_type: Literal["PROPERTY_SHOWCASE", "JUST_LISTED", "LIFESTYLE"]
    pacing_speed: Literal["SLOW", "NORMAL", "FAST"]
    audio_config: AudioConfig
    branding: BrandingConfig
    timeline: List[ShotNode]
    total_duration_ms: int
