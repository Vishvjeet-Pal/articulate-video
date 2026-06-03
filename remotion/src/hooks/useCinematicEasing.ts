/**
 * useCinematicEasing
 * ==================
 * Pure TypeScript easing utilities used by VirtualCamera and DepthParallaxScene.
 *
 * All functions accept a normalised progress value `t` in [0, 1] and return
 * a remapped value also in [0, 1].
 */

/** Classic cubic ease-in-out: slow start, fast middle, slow end. */
export const easeInOutCubic = (t: number): number => {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
};

/** Ease-in: starts slow, ends fast. */
export const easeIn = (t: number): number => {
    return t * t * t;
};

/** Ease-out: starts fast, ends slow. */
export const easeOut = (t: number): number => {
    return 1 - Math.pow(1 - t, 3);
};

/** Linear (no easing). Provided for completeness. */
export const linear = (t: number): number => t;

/**
 * Approximate a cubic Bézier curve with two control points.
 * p1 and p2 are the inner control points (p0=0,0 and p3=1,1 are implicit).
 */
export const bezierEase = (
    t: number,
    p1x: number,
    p1y: number,
    p2x: number,
    p2y: number,
    iterations = 8,
): number => {
    let low = 0;
    let high = 1;
    let mid = t;

    for (let i = 0; i < iterations; i++) {
        const bx = bezierPoint(mid, p1x, p2x);
        if (Math.abs(bx - t) < 0.0001) break;
        if (bx < t) low = mid;
        else high = mid;
        mid = (low + high) / 2;
    }

    return bezierPoint(mid, p1y, p2y);
};

const bezierPoint = (t: number, p1: number, p2: number): number => {
    return 3 * (1 - t) * (1 - t) * t * p1
        + 3 * (1 - t) * t * t * p2
        + t * t * t;
};

/**
 * Dispatch function — maps a curve name string to the appropriate easing fn.
 */
export const applyMotionCurve = (curve: string, t: number): number => {
    switch (curve) {
        case 'easeInOutCubic': return easeInOutCubic(t);
        case 'easeIn':         return easeIn(t);
        case 'easeOut':        return easeOut(t);
        case 'linear':         return linear(t);
        default:               return easeInOutCubic(t);
    }
};

/**
 * Cinematic breathing — an extremely subtle, slow vertical float
 * that gives the camera a "held breath" feeling, not walking shake.
 *
 * This replaces the previous walkingSway which caused aggressive shaking.
 *
 * @param frame      Current frame within the shot (absolute, not relative)
 * @param fps        Frames per second
 * @param amplitude  Maximum offset in world units (keep very small, e.g. 4–8)
 * @param period     Full cycle in seconds (default 6s = very slow breath)
 */
export const cinematicBreathing = (
    frame: number,
    fps: number,
    amplitude: number,
    period = 6.0,
): number => {
    const t = frame / fps;
    // Use a smooth sine with a very long period — nearly imperceptible movement
    // that prevents the camera from feeling completely locked/static.
    return Math.sin((t / period) * Math.PI * 2) * amplitude;
};
