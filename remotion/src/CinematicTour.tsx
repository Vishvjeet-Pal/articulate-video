/**
 * CinematicTour
 * =============
 * The top-level Remotion composition for the property walkthrough.
 *
 * Architecture:
 *   ┌─ AbsoluteFill ──────────────────────────────────────────────────────┐
 *   │  ┌─ ThreeCanvas (single persistent WebGL context) ────────────────┐ │
 *   │  │  Suspense                                                       │ │
 *   │  │   └─ DepthParallaxScene                                         │ │
 *   │  │       • Dual-layer mesh (foreground + background)               │ │
 *   │  │       • VirtualCamera drives camera per-frame                   │ │
 *   │  │       • Supports WALK_FORWARD sway, PUSH_IN dolly, ORBIT, etc.  │ │
 *   │  │       • Momentum preserved: shot N start == shot N-1 end        │ │
 *   │  └─────────────────────────────────────────────────────────────────┘ │
 *   │  ┌─ Series (overlay layer — no 3D context) ───────────────────────┐  │
 *   │  │  Series.Sequence × N shots                                      │  │
 *   │  │   └─ ShotNode → TransitionOverlay (FADE / CROSS_DISSOLVE)      │  │
 *   │  └─────────────────────────────────────────────────────────────────┘  │
 *   │  ┌─ Branding Overlay ─────────────────────────────────────────────┐  │
 *   │  │  Logo (CORNER or LOWER_THIRD)                                   │  │
 *   │  └─────────────────────────────────────────────────────────────────┘  │
 *   └────────────────────────────────────────────────────────────────────────┘
 *
 * KEY FIX: DepthParallaxScene is NOT remounted between shots.
 *   Previously: `key={active.shotIndex}` caused full WebGL context destruction
 *   and camera teleportation on every cut.
 *   Now: the scene persists for the full video; the camera state streams
 *   continuously from VirtualCamera based on the active shot's parameters.
 */

import React, { useMemo, Suspense } from 'react';
import { AbsoluteFill, Series, useCurrentFrame, useVideoConfig } from 'remotion';
import { ThreeCanvas } from '@remotion/three';
import type { RemotionInputProps, ShotNodeConfig } from './Root';
import { ShotNode } from './components/ShotNode';
import { DepthParallaxScene } from './components/DepthParallaxScene';

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

    // Camera distance: at this Z with 75° FOV the image plane exactly fills the comp.
    const cameraZ = (height / 2) / Math.tan((75 / 2) * Math.PI / 180);

    return (
        <AbsoluteFill style={{ backgroundColor: branding.primary_color_hex }}>

            {/*
              * Single persistent ThreeCanvas — survives across all shots.
              * The DepthParallaxScene inside does NOT use a `key` prop, so the
              * WebGL context (and camera state) are never destroyed mid-video.
              */}
            <ThreeCanvas
                width={width}
                height={height}
                linear
                camera={{ fov: 75, position: [0, 0, cameraZ], near: 0.1, far: 12000.0 }}
            >
                <Suspense fallback={null}>
                    {/*
                      * NO key={active.shotIndex} here — this is the critical fix.
                      * The scene streams new props each frame via relativeFrame /
                      * motionType changes; the WebGL context persists throughout.
                      */}
                    <DepthParallaxScene
                        imageUrl={active.shot.image_url}
                        depthUrl={active.shot.depth_map_url}
                        proceduralTargets={active.shot.procedural_motion_targets}
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
                </Suspense>
            </ThreeCanvas>

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
                    />
                </AbsoluteFill>
            )}
        </AbsoluteFill>
    );
};
