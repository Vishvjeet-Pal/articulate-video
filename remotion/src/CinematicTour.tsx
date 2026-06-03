/**
 * CinematicTour
 * =============
 * The top-level Remotion composition for the property walkthrough.
 *
 * Architecture:
 *   ┌─ AbsoluteFill ─────────────────────────────────────────────────────────┐
 *   │  ┌─ CinematicScene (CSS transforms — frame-accurate) ────────────────┐ │
 *   │  │  • scale(z_base/camera_z) — forward/backward dolly                │ │
 *   │  │  • translate(x%, y%) — lateral pan toward next room               │ │
 *   │  │  • Optional BG layer at reduced rate for depth parallax            │ │
 *   │  │  • VirtualCamera math runs inside CinematicScene via interpolate   │ │
 *   │  └──────────────────────────────────────────────────────────────────── ┘ │
 *   │  ┌─ Series (overlay layer) ────────────────────────────────────────────┐ │
 *   │  │  Series.Sequence × N shots                                          │ │
 *   │  │   └─ ShotNode → TransitionOverlay (FADE / CROSS_DISSOLVE / etc.)   │ │
 *   │  └──────────────────────────────────────────────────────────────────── ┘ │
 *   │  ┌─ Branding Overlay ──────────────────────────────────────────────────┐ │
 *   │  │  Logo (CORNER or LOWER_THIRD)                                       │ │
 *   │  └──────────────────────────────────────────────────────────────────── ┘ │
 *   └────────────────────────────────────────────────────────────────────────── ┘
 *
 * WHY CSS NOT WebGL:
 *   Remotion renders each frame independently. WebGL useFrame() is NOT called
 *   at the right time for each frame during export, causing wrong camera positions.
 *   CSS interpolate() is synchronous and frame-accurate.
 */

import React, { useMemo, Suspense } from 'react';
import { AbsoluteFill, Series, useCurrentFrame, useVideoConfig } from 'remotion';
import type { RemotionInputProps, ShotNodeConfig } from './Root';
import { ShotNode } from './components/ShotNode';
import { CinematicScene } from './components/CinematicScene';

const FPS = 30;

interface ActiveShot {
    shot: ShotNodeConfig;
    shotIndex: number;
    relativeFrame: number;
    durationInFrames: number;
}

const getActiveShot = (frame: number, timeline: ShotNodeConfig[]): ActiveShot => {
    let elapsedFrames = 0;
    for (let i = 0; i < timeline.length; i++) {
        const shot = timeline[i];
        const durationInFrames = Math.ceil((shot.duration_ms / 1000) * FPS);
        if (frame >= elapsedFrames && frame < elapsedFrames + durationInFrames) {
            return {
                shot,
                shotIndex: i,
                relativeFrame: frame - elapsedFrames,
                durationInFrames,
            };
        }
        elapsedFrames += durationInFrames;
    }
    // Fallback: hold last frame of last shot
    const lastShot = timeline[timeline.length - 1];
    const lastDuration = Math.ceil((lastShot.duration_ms / 1000) * FPS);
    return {
        shot: lastShot,
        shotIndex: timeline.length - 1,
        relativeFrame: lastDuration - 1,
        durationInFrames: lastDuration,
    };
};

export const CinematicTour: React.FC<RemotionInputProps> = (props) => {
    const { timeline, branding } = props;
    const frame = useCurrentFrame();
    const { width, height } = useVideoConfig();

    const active = useMemo(() => getActiveShot(frame, timeline), [frame, timeline]);

    return (
        <AbsoluteFill style={{ backgroundColor: branding.primary_color_hex }}>

            {/*
              * CinematicScene — pure CSS transforms, frame-accurate.
              * No WebGL, no useFrame race conditions.
              * The image is rendered at 150% size; scale + translate drive the motion.
              */}
            <CinematicScene
                imageUrl={active.shot.image_url}
                depthUrl={active.shot.depth_map_url}
                durationInFrames={active.durationInFrames}
                relativeFrame={active.relativeFrame}
                motionType={active.shot.motion_type}
                motionStrength={active.shot.motion_strength}
                motionCurve={active.shot.motion_curve}
                depthParallaxStrength={active.shot.depth_parallax_strength}
                cameraStart={active.shot.camera_start_target}
                cameraEnd={active.shot.camera_end_target}
                width={width}
                height={height}
            />

            {/* Overlay layer: transition effects + per-shot decorators */}
            <Series>
                {timeline.map((shot, index) => {
                    const durationInFrames = Math.ceil((shot.duration_ms / 1000) * FPS);
                    return (
                        <Series.Sequence
                            key={`shot-overlay-${index}`}
                            durationInFrames={durationInFrames}
                        >
                            <ShotNode shotConfig={shot} />
                        </Series.Sequence>
                    );
                })}
            </Series>

            {/* Global Branding Overlay */}
            {branding.brokerage_overlay_url && (
                <AbsoluteFill style={{ pointerEvents: 'none' }}>
                    <img
                        src={branding.brokerage_overlay_url}
                        style={{
                            position: 'absolute',
                            bottom: branding.logo_mapping === 'CORNER' ? '40px' : '0px',
                            right:  branding.logo_mapping === 'CORNER' ? '40px' : 'auto',
                            width:  branding.logo_mapping === 'LOWER_THIRD' ? '100%' : '300px',
                            objectFit: 'contain',
                        }}
                        alt=""
                    />
                </AbsoluteFill>
            )}
        </AbsoluteFill>
    );
};
