/**
 * VirtualCamera
 * =============
 * Pure computation module — no React, no Three.js imports.
 *
 * Collov-style motion model:
 *   The reference (Collov) videos achieve their look through:
 *     1. Very SLOW, SMOOTH camera movement (5–8 seconds per shot)
 *     2. Gentle push-in toward the focal subject (Z dolly, ~8-12% travel)
 *     3. Slight pan toward the strongest saliency point (X/Y drift)
 *     4. NO oscillation, NO walking sway, NO shake
 *     5. Everything driven by a single smooth easeInOutCubic curve
 *     6. The "depth" feel comes from the displacement mesh, not camera rotation
 *
 * The previous WALK_FORWARD sway was causing shake because:
 *   - sin() at 1.8Hz on a 30fps renderer = ~54 visible oscillations/second
 *   - Amplitude of 60 world units ≈ 60px at 4K = clearly visible jitter
 *
 * FIX: All motion types now use smooth monotonic interpolation only.
 * The "alive" feeling comes from easeInOutCubic acceleration, not oscillation.
 * A single ultra-slow Y breathing (6s period, 4 world-unit amplitude) is added
 * to WALK_FORWARD to prevent a completely locked/robotic feel.
 */

import { applyMotionCurve, cinematicBreathing } from '../hooks/useCinematicEasing';
import type { MotionType, MotionCurve } from '../Root';

const FPS = 30;

// Cinematic breathing: Y-axis only, very small amplitude, very long period.
// 4 world units ≈ 0.1% of frame height at 4K — completely imperceptible as shake,
// but prevents the camera from feeling frozen.
const BREATHING_AMPLITUDE = 4;
const BREATHING_PERIOD_S   = 6.0;

export interface CameraState {
    x: number;
    y: number;
    z: number;
}

/**
 * Computes the camera world position for the given frame within a shot.
 *
 * @param relativeFrame   Frame index within the current shot (0 … durationInFrames-1)
 * @param durationInFrames Total frame count of this shot
 * @param motionType       Cinematic motion preset
 * @param motionStrength   0–1 amplitude scale
 * @param motionCurve      Easing curve name
 * @param cameraStart      [x, y, z] at frame 0 of this shot
 * @param cameraEnd        [x, y, z] at final frame of this shot
 */
export const computeCameraState = (
    relativeFrame: number,
    durationInFrames: number,
    motionType: MotionType,
    motionStrength: number,
    motionCurve: MotionCurve,
    cameraStart: [number, number, number],
    cameraEnd: [number, number, number],
): CameraState => {
    // Normalised progress in [0, 1]
    const rawT = durationInFrames > 1
        ? Math.min(relativeFrame / (durationInFrames - 1), 1)
        : 0;

    const t = applyMotionCurve(motionCurve, rawT);

    const [sx, sy, sz] = cameraStart;
    const [ex, ey, ez] = cameraEnd;

    // Smooth linear interpolation — no oscillation ever
    const lerp = (a: number, b: number, f: number) => a + (b - a) * f;

    // Ultra-subtle vertical breathing on Y — 6s period, ~4 world units
    // Used only on WALK_FORWARD and SLOW_DRIFT to keep the camera feeling
    // human without any shake.
    const breath = cinematicBreathing(relativeFrame, FPS, BREATHING_AMPLITUDE, BREATHING_PERIOD_S);

    switch (motionType) {

        case 'WALK_FORWARD': {
            // Collov-style: smooth forward push (Z) + very slight drift toward subject
            // No sway. No oscillation. Just smooth eased motion.
            return {
                x: lerp(sx, ex, t),
                y: lerp(sy, ey, t) + breath,  // breath is ~4px — completely invisible as shake
                z: lerp(sz, ez, t),
            };
        }

        case 'PUSH_IN': {
            // Straight smooth dolly — approach the subject on Z
            return {
                x: lerp(sx, ex, t),
                y: lerp(sy, ey, t),
                z: lerp(sz, ez, t),
            };
        }

        case 'PULL_OUT': {
            return {
                x: lerp(sx, ex, t),
                y: lerp(sy, ey, t),
                z: lerp(sz, ez, t),
            };
        }

        case 'DOLLY_FORWARD': {
            // Lateral sweep + Z approach — entering a room
            return {
                x: lerp(sx, ex, t),
                y: lerp(sy, ey, t),
                z: lerp(sz, ez, t),
            };
        }

        case 'DOLLY_BACK': {
            return {
                x: lerp(sx, ex, t),
                y: lerp(sy, ey, t),
                z: lerp(sz, ez, t),
            };
        }

        case 'ORBIT': {
            // Parametric arc — camera sweeps around the subject.
            // X follows a sine arc for a curved feel, Z closes gently.
            // NOTE: we keep this fully smooth — sin() here is a spatial
            // arc shape, not a time-domain oscillation. It only samples
            // one monotonically increasing angle, so there is no shaking.
            const angle = t * Math.PI * 0.45; // ~80° arc, not a full loop
            const dx = ex - sx;
            const dz = ez - sz;
            return {
                x: sx + Math.sin(angle) * Math.abs(dx) * Math.sign(dx),
                y: lerp(sy, ey, t),
                z: sz + (1 - Math.cos(angle)) * dz,
            };
        }

        case 'REVEAL': {
            // Uses easeOut so the landing is deliberate and smooth
            const revealT = applyMotionCurve('easeOut', rawT);
            return {
                x: lerp(sx, ex, revealT),
                y: lerp(sy, ey, revealT),
                z: lerp(sz, ez, revealT),
            };
        }

        case 'TRACK_LEFT':
        case 'TRACK_RIGHT': {
            // Pure lateral track — X moves, Z barely drifts
            return {
                x: lerp(sx, ex, t),
                y: lerp(sy, ey, t),
                z: lerp(sz, ez, t),
            };
        }

        case 'SLOW_DRIFT': {
            // Minimal movement — beauty / rest shot
            return {
                x: lerp(sx, ex, t),
                y: lerp(sy, ey, t) + breath * 0.5,
                z: lerp(sz, ez, t),
            };
        }

        default:
            return { x: lerp(sx, ex, t), y: lerp(sy, ey, t), z: lerp(sz, ez, t) };
    }
};
