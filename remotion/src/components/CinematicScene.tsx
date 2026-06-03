/**
 * CinematicScene
 * ==============
 * CSS-transform-based rendering that replaces the WebGL camera approach.
 *
 * WHY CSS INSTEAD OF WebGL CAMERA:
 *   Remotion renders frames independently (not as a live animation loop).
 *   WebGL's `useFrame` hook is NOT guaranteed to fire at the correct time for
 *   each exported frame, so camera.position.set() via useFrame produces
 *   incorrect positions in the rendered MP4.
 *
 *   CSS `transform` driven by Remotion's `interpolate()` IS frame-accurate —
 *   it is computed synchronously at render time. This guarantees the correct
 *   position on every frame.
 *
 * MOTION MODEL:
 *   We simulate walking through space using:
 *     scale(s)       — Z dolly: scale > 1 = camera moved closer = zoomed in
 *     translateX(tx) — camera pan left/right
 *     translateY(ty) — camera pan up/down
 *
 *   The scale relationship to camera Z:
 *     scale = camera_z_base / camera_z
 *     At camera_z = camera_z_base → scale = 1.0 (image fills frame)
 *     At camera_z = 0.70 * camera_z_base → scale = 1.43 (43% zoom-in = strong forward motion)
 *
 *   The image is rendered at (overscale * 100)% size to give room for panning.
 *
 * DEPTH PARALLAX:
 *   When a depth map is available, a second slightly-scaled layer is composited
 *   behind the main image, creating foreground/background separation.
 *   No mesh displacement — just two independently-moving CSS layers.
 */

import React, { useMemo } from 'react';
import { AbsoluteFill, interpolate } from 'remotion';
import { applyMotionCurve, cinematicBreathing } from '../hooks/useCinematicEasing';
import type { MotionType, MotionCurve, ProceduralMotionTarget } from '../Root';

// Must mirror backend PLANE_OVERSCALE_FACTOR and camera_z_base formula.
// The image is rendered this many times larger than the composition,
// so the camera has room to pan and zoom without revealing black edges.
const PLANE_OVERSCALE_FACTOR = 1.5;   // 50% oversize = plenty of travel room

// camera_z_base = (height/2) / tan(FOV/2) — mirrors Python formula
// At 4K with 75° FOV: camera_z_base ≈ 1407
const CAMERA_Z_BASE_4K = 1407.5;

const FPS = 30;
const BREATH_AMPLITUDE = 0.001;  // 0.1% of frame height — barely perceptible, prevents frozen feel
const BREATH_PERIOD_S  = 6.0;

interface CinematicSceneProps {
    imageUrl: string;
    depthUrl: string | null;
    durationInFrames: number;
    relativeFrame: number;
    motionType: MotionType;
    motionStrength: number;
    motionCurve: MotionCurve;
    depthParallaxStrength: number;
    cameraStart: [number, number, number];  // [x, y, z] in world units
    cameraEnd:   [number, number, number];
    width: number;
    height: number;
}

/**
 * Converts a camera [x, y, z] world-space position into CSS transform values.
 *
 * @param cx   Camera X (right = positive)
 * @param cy   Camera Y (up = positive)
 * @param cz   Camera Z (smaller = closer to plane = more zoom)
 * @param w    Composition width
 * @param h    Composition height
 * @returns    { scale, translateX, translateY } for CSS transform
 */
function cameraToCSS(
    cx: number,
    cy: number,
    cz: number,
    w: number,
    h: number,
): { scale: number; tx: string; ty: string } {
    // Z → scale: scale = z_base / z_current
    // At z_base → 1.0 (fills frame). At 0.70 * z_base → 1.43 (43% zoom in).
    const zBase = (h / 2) / Math.tan((75 / 2) * Math.PI / 180);
    const scale = zBase / Math.max(cz, zBase * 0.30);  // clamp to prevent extreme zoom

    // X/Y panning: camera moving right → content moves left
    // The pan in pixels is: camera_x / camera_z * focal_length * (1/scale)
    // In CSS %, relative to the (overscaled) image width
    // Simplified: pan_percent = -(camera_x / (w * PLANE_OVERSCALE_FACTOR)) * 100
    const txPct = -(cx / (w * PLANE_OVERSCALE_FACTOR)) * 100 * 1.2;  // 1.2x boosts apparent motion
    const tyPct =  (cy / (h * PLANE_OVERSCALE_FACTOR)) * 100 * 1.2;

    return {
        scale,
        tx: `${txPct.toFixed(3)}%`,
        ty: `${tyPct.toFixed(3)}%`,
    };
}

export const CinematicScene: React.FC<CinematicSceneProps> = ({
    imageUrl,
    depthUrl,
    durationInFrames,
    relativeFrame,
    motionType,
    motionStrength,
    motionCurve,
    depthParallaxStrength,
    cameraStart,
    cameraEnd,
    width,
    height,
}) => {
    // Normalised progress [0, 1]
    const rawT = durationInFrames > 1
        ? Math.min(relativeFrame / (durationInFrames - 1), 1)
        : 0;

    const t = applyMotionCurve(motionCurve, rawT);

    const [sx, sy, sz] = cameraStart;
    const [ex, ey, ez] = cameraEnd;

    const lerp = (a: number, b: number, f: number) => a + (b - a) * f;

    // Ultra-subtle Y breathing — prevents the camera from feeling frozen
    const breath = cinematicBreathing(relativeFrame, FPS, BREATH_AMPLITUDE, BREATH_PERIOD_S);

    // Compute current camera position
    let cx: number, cy: number, cz: number;

    if (motionType === 'REVEAL') {
        // easeOut for reveal — fast sweep, deliberate land
        const revealT = applyMotionCurve('easeOut', rawT);
        cx = lerp(sx, ex, revealT);
        cy = lerp(sy, ey, revealT);
        cz = lerp(sz, ez, revealT);
    } else if (motionType === 'ORBIT') {
        // Parametric arc — X follows sine curve for natural swing
        const angle = t * Math.PI * 0.45;
        const dx = ex - sx;
        cx = sx + Math.sin(angle) * Math.abs(dx) * Math.sign(dx || 1);
        cy = lerp(sy, ey, t);
        cz = sz + (1 - Math.cos(angle)) * (ez - sz);
    } else {
        cx = lerp(sx, ex, t);
        cy = lerp(sy, ey, t) + breath * height;
        cz = lerp(sz, ez, t);
    }

    const { scale, tx, ty } = cameraToCSS(cx, cy, cz, width, height);

    // For depth parallax: background layer moves at (1 - strength) of the foreground rate.
    // Foreground moves faster (closer to camera) = stronger parallax separation.
    const bgParallaxFactor = depthUrl ? (1 - depthParallaxStrength * 0.35) : 1.0;
    const bgScale = scale * bgParallaxFactor + (1 - bgParallaxFactor);  // blend toward 1.0

    // BG tx/ty: slightly less translation = appears farther away
    const txNum = parseFloat(tx);
    const tyNum = parseFloat(ty);
    const bgTx = (txNum * bgParallaxFactor).toFixed(3) + '%';
    const bgTy = (tyNum * bgParallaxFactor).toFixed(3) + '%';

    const overscalePct = PLANE_OVERSCALE_FACTOR * 100;

    return (
        <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: '#000' }}>

            {/* Background layer — moves slightly slower than foreground (parallax) */}
            {depthUrl && (
                <AbsoluteFill
                    style={{
                        overflow: 'visible',
                        willChange: 'transform',
                        transform: `scale(${bgScale.toFixed(4)}) translate(${bgTx}, ${bgTy})`,
                        transformOrigin: 'center center',
                    }}
                >
                    <img
                        src={imageUrl}
                        style={{
                            width:  `${overscalePct}%`,
                            height: `${overscalePct}%`,
                            objectFit: 'cover',
                            position: 'absolute',
                            top:  `${-(overscalePct - 100) / 2}%`,
                            left: `${-(overscalePct - 100) / 2}%`,
                            filter: 'blur(1.5px)',  // BG is slightly soft — appears farther away
                        }}
                        alt=""
                    />
                </AbsoluteFill>
            )}

            {/* Foreground (primary) layer — full sharpness, full parallax movement */}
            <AbsoluteFill
                style={{
                    overflow: 'visible',
                    willChange: 'transform',
                    transform: `scale(${scale.toFixed(4)}) translate(${tx}, ${ty})`,
                    transformOrigin: 'center center',
                }}
            >
                <img
                    src={imageUrl}
                    style={{
                        width:  `${overscalePct}%`,
                        height: `${overscalePct}%`,
                        objectFit: 'cover',
                        position: 'absolute',
                        top:  `${-(overscalePct - 100) / 2}%`,
                        left: `${-(overscalePct - 100) / 2}%`,
                    }}
                    alt=""
                />
            </AbsoluteFill>

        </AbsoluteFill>
    );
};
