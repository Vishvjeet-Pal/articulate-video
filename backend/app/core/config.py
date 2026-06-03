from typing import Dict, List, Tuple

# Video Duration Constraints (ms)
MIN_VIDEO_DURATION_MS: int = 60000
MAX_VIDEO_DURATION_MS: int = 120000

# Shot Duration Constraints (ms)
MIN_SHOT_DURATION_MS: int = 3000
MAX_SHOT_DURATION_MS: int = 8000

# SOW Narrative Sequencing Hierarchy: Exterior Entry -> Living Spaces -> Private Spaces -> Amenities/Other
ROOM_IMPORTANCE_HIERARCHY: List[str] = [
    "Exterior",
    "Living Room",
    "Kitchen",
    "Dining Room",
    "Primary Bedroom",
    "Other Bedrooms",
    "Primary Bathroom",
    "Other Bathrooms",
    "Other"
]

# Plane over-scale factor inside Remotion components.
# Increased to 1.25 to support wider dolly/Z travel range without edge bleed.
# Keep this value mirrored in remotion/src/components/DepthParallaxScene.tsx.
PLANE_OVERSCALE_FACTOR: float = 1.25

# Z-axis (depth) travel range for cinematic dolly movement.
# Expressed as multipliers of camera_z_base.
#   DOLLY_Z_MIN_MULT  — closest approach (push-in end / pull-out start)
#   DOLLY_Z_MAX_MULT  — farthest position (pull-out end / wide reveal start)
# These are deliberately tight (±8%) to match Collov's barely-perceptible
# forward motion.  Larger values cause visible depth lunges (was ±18%).
DOLLY_Z_MIN_MULT: float = 0.92   # 8% closer than neutral
DOLLY_Z_MAX_MULT: float = 1.08   # 8% farther than neutral

# Camera Z-axis movement relative multipliers (legacy — kept for backwards compat)
PUSH_IN_START_MULT: float = 1.10
PUSH_IN_END_MULT: float = 0.90

PULL_BACK_START_MULT: float = 0.90
PULL_BACK_END_MULT: float = 1.10

# Walking sway amplitude as a fraction of the X pan budget.
# 0.04 = ±4% of x_max — subtle hand-held feel.
WALK_SWAY_AMPLITUDE: float = 0.04

# -------------------------------------------------------------------
# Room adjacency graph — used by CameraPathPlanner to infer
# spatial relationships and select cinematic transition types.
# Each entry: from_room -> [(to_room, transition_hint)]
# -------------------------------------------------------------------
ROOM_ADJACENCY_GRAPH: Dict[str, List[Tuple[str, str]]] = {
    "Exterior":        [("Living Room", "doorway"), ("Other", "doorway")],
    "Living Room":     [("Exterior", "doorway"), ("Kitchen", "open_plan"), ("Dining Room", "open_plan"), ("Primary Bedroom", "hallway")],
    "Kitchen":         [("Living Room", "open_plan"), ("Dining Room", "open_plan")],
    "Dining Room":     [("Kitchen", "open_plan"), ("Living Room", "open_plan")],
    "Primary Bedroom": [("Primary Bathroom", "doorway"), ("Living Room", "hallway")],
    "Other Bedrooms":  [("Other Bathrooms", "doorway"), ("Living Room", "hallway")],
    "Primary Bathroom":[("Primary Bedroom", "doorway")],
    "Other Bathrooms": [("Other Bedrooms", "doorway")],
    "Other":           [("Living Room", "open_plan")],
}

# -------------------------------------------------------------------
# Camera motion presets per room type.
# Each entry: room_type -> [(motion_type, weight)]
# Weights are relative — they are normalised inside CameraPathPlanner.
# -------------------------------------------------------------------
CAMERA_MOTION_PRESETS: Dict[str, List[Tuple[str, float]]] = {
    "Exterior":         [("REVEAL", 0.35), ("PULL_OUT", 0.30), ("WALK_FORWARD", 0.20), ("SLOW_DRIFT", 0.15)],
    "Living Room":      [("WALK_FORWARD", 0.30), ("SLOW_DRIFT", 0.25), ("PUSH_IN", 0.20), ("REVEAL", 0.15), ("TRACK_LEFT", 0.10)],
    "Kitchen":          [("TRACK_LEFT", 0.30), ("TRACK_RIGHT", 0.25), ("PUSH_IN", 0.25), ("WALK_FORWARD", 0.20)],
    "Dining Room":      [("SLOW_DRIFT", 0.35), ("ORBIT", 0.30), ("PUSH_IN", 0.20), ("WALK_FORWARD", 0.15)],
    "Primary Bedroom":  [("SLOW_DRIFT", 0.35), ("ORBIT", 0.25), ("DOLLY_FORWARD", 0.25), ("REVEAL", 0.15)],
    "Other Bedrooms":   [("SLOW_DRIFT", 0.30), ("PUSH_IN", 0.30), ("DOLLY_FORWARD", 0.25), ("TRACK_LEFT", 0.15)],
    "Primary Bathroom": [("PUSH_IN", 0.35), ("SLOW_DRIFT", 0.35), ("REVEAL", 0.30)],
    "Other Bathrooms":  [("PUSH_IN", 0.40), ("SLOW_DRIFT", 0.35), ("REVEAL", 0.25)],
    "Other":            [("WALK_FORWARD", 0.40), ("SLOW_DRIFT", 0.30), ("PUSH_IN", 0.30)],
}

# Default motion strength per motion type (0.0 – 1.0)
MOTION_STRENGTH_DEFAULTS: Dict[str, float] = {
    "PUSH_IN":       0.70,
    "PULL_OUT":      0.65,
    "DOLLY_FORWARD": 0.75,
    "DOLLY_BACK":    0.65,
    "ORBIT":         0.55,
    "REVEAL":        0.80,
    "TRACK_LEFT":    0.60,
    "TRACK_RIGHT":   0.60,
    "WALK_FORWARD":  0.50,
    "SLOW_DRIFT":    0.35,
}

ROOM_TIME_MULTIPLIERS: Dict[str, float] = {
    "Living Room":      2.0,
    "Kitchen":          2.0,
    "Primary Bedroom":  2.0,
    "Exterior":         1.5,
    "Dining Room":      1.3,
    "Primary Bathroom": 1.0,
    "Other Bedrooms":   1.0,
    "Other Bathrooms":  1.0,
    "Other":            1.0,
}

# Pacing Baseline Durations (ms)
PACING_BASE_DURATION: Dict[str, int] = {
    "SLOW":   7000,
    "NORMAL": 5000,
    "FAST":   3500
}

# Hero-shot max per room — prevents 6 nearly-identical bedroom shots
MAX_SHOTS_PER_ROOM: int = 2

# FFmpeg Social Crop Presets (Ratio strings or specific W:H values)
SOCIAL_RATIOS: Dict[str, str] = {
    "IG_REELS": "9:16",
    "FB_FEED":  "1:1"
}

# Celery / Redis config
REDIS_URL: str = "redis://localhost:6379/0"
CELERY_BROKER_URL: str = REDIS_URL
CELERY_RESULT_BACKEND: str = REDIS_URL
