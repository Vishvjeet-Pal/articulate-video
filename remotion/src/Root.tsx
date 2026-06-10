import { Composition } from 'remotion';
import { CinematicTour } from './CinematicTour';

// Define the exact TypeScript interface matching the Python Pydantic RemotionInputProps payload
export interface ProceduralMotionTarget {
    mask_id: string;
    type: 'FOLIAGE_SWAY' | 'WATER_DISPLACEMENT' | 'FABRIC_WARP';
    intensity: number;
}

export type MotionType =
    | 'PUSH_IN'
    | 'PULL_OUT'
    | 'DOLLY_FORWARD'
    | 'DOLLY_BACK'
    | 'ORBIT'
    | 'REVEAL'
    | 'TRACK_LEFT'
    | 'TRACK_RIGHT'
    | 'WALK_FORWARD'
    | 'SLOW_DRIFT';

export type MotionCurve = 'easeInOutCubic' | 'easeIn' | 'easeOut' | 'linear';

export type TransitionType = 'PAN' | 'FADE' | 'CUT' | 'MOTION_MATCH' | 'CROSS_DISSOLVE';

export interface ShotNodeConfig {
    image_url: string;
    depth_map_url: string | null;
    room_type: string;
    duration_ms: number;

    // Cinematic motion parameters (new)
    motion_type: MotionType;
    motion_strength: number;           // 0.0–1.0
    motion_curve: MotionCurve;
    depth_parallax_strength: number;   // 0.0–1.0

    transition_type: TransitionType;
    camera_path: any | null;
    procedural_motion_targets: ProceduralMotionTarget[];
    saliency_crop_16_9: string | null;
    saliency_crop_9_16: string | null;
    saliency_crop_1_1: string | null;

    // Global continuous camera positions (x, y, z)
    camera_start_target: [number, number, number];
    camera_end_target: [number, number, number];
}

export interface AudioConfig {
    bgm_url: string | null;
    voiceover_url: string | null;
    volume_balance: number;
    track_url?: string | null;
    bpm?: number | null;
}

export interface BrandingConfig {
    brokerage_overlay_url: string | null;
    logo_mapping: 'CORNER' | 'LOWER_THIRD';
    primary_color_hex: string;
    secondary_color_hex: string;
}

export interface RemotionInputProps extends Record<string, unknown> {
    tour_type: 'PROPERTY_SHOWCASE' | 'JUST_LISTED' | 'LIFESTYLE';
    pacing_speed: 'SLOW' | 'NORMAL' | 'FAST';
    audio_config: AudioConfig;
    branding: BrandingConfig;
    timeline: ShotNodeConfig[];
    total_duration_ms: number;
}

const FPS = 30; // Standard cinematic framerate

// Provide default mock props so the Remotion Studio can still be previewed
const defaultProps: RemotionInputProps = {
    tour_type: 'PROPERTY_SHOWCASE',
    pacing_speed: 'NORMAL',
    audio_config: { bgm_url: null, voiceover_url: null, volume_balance: 0.5 },
    branding: { brokerage_overlay_url: null, logo_mapping: 'CORNER', primary_color_hex: '#000000', secondary_color_hex: '#FFFFFF' },
    timeline: [
        {
            image_url: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="3840" height="2160" viewBox="0 0 3840 2160"><rect width="3840" height="2160" fill="%231E1E2E"/><text x="1920" y="1080" font-family="sans-serif" font-size="120" fill="%23F5C2E7" dominant-baseline="middle" text-anchor="middle">Articulait Video - Property Showcase</text></svg>',
            depth_map_url: null,
            room_type: 'Exterior',
            duration_ms: 6000,
            motion_type: 'REVEAL',
            motion_strength: 0.8,
            motion_curve: 'easeInOutCubic',
            depth_parallax_strength: 0.3,
            transition_type: 'FADE',
            camera_path: null,
            procedural_motion_targets: [],
            saliency_crop_16_9: null, saliency_crop_9_16: null, saliency_crop_1_1: null,
            camera_start_target: [240, 120, 1550],
            camera_end_target: [0, 0, 1407],
        },
        {
            image_url: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="3840" height="2160" viewBox="0 0 3840 2160"><rect width="3840" height="2160" fill="%23181825"/><text x="1920" y="1080" font-family="sans-serif" font-size="100" fill="%23CBA6F7" dominant-baseline="middle" text-anchor="middle">Living Room</text></svg>',
            depth_map_url: null,
            room_type: 'Living Room',
            duration_ms: 7000,
            motion_type: 'WALK_FORWARD',
            motion_strength: 0.5,
            motion_curve: 'easeInOutCubic',
            depth_parallax_strength: 0.3,
            transition_type: 'CROSS_DISSOLVE',
            camera_path: null,
            procedural_motion_targets: [],
            saliency_crop_16_9: null, saliency_crop_9_16: null, saliency_crop_1_1: null,
            camera_start_target: [0, 0, 1407],
            camera_end_target: [-20, -15, 1310],
        },
    ],
    total_duration_ms: 13000,
};

export const RemotionRoot: React.FC = () => {
    const getDurationInFrames = (props: RemotionInputProps) => {
        return Math.ceil((props.total_duration_ms / 1000) * FPS) || 300;
    };

    return (
        <>
            <Composition<any, RemotionInputProps>
                id="CinematicTour"
                component={CinematicTour}
                durationInFrames={getDurationInFrames(defaultProps)}
                fps={FPS}
                width={3840}
                height={2160}
                defaultProps={defaultProps}
                calculateMetadata={({ props }) => {
                    const remotionProps = props as RemotionInputProps;
                    return {
                        durationInFrames: getDurationInFrames(remotionProps),
                        props: remotionProps
                    };
                }}
            />
        </>
    );
};
