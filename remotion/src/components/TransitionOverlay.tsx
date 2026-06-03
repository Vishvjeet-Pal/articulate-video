/**
 * TransitionOverlay
 * =================
 * Composites transition effects on top of the 3D scene.
 *
 * Supported types:
 *   FADE          — black fade-in at shot start
 *   CROSS_DISSOLVE — opacity blend from previous → current (used at room transitions)
 *   MOTION_MATCH  — no overlay; camera velocity continuity handles the cut
 *   CUT           — no overlay
 *   PAN           — no overlay (legacy; treated as CUT)
 *
 * The overlay renders at pointer-events:none so it never blocks input.
 */

import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import type { TransitionType } from '../Root';

interface TransitionOverlayProps {
    transitionType: TransitionType;
}

// Duration of fade/dissolve transitions in frames
const FADE_IN_FRAMES  = 20; // ~0.67s at 30fps
const FADE_OUT_FRAMES = 15; // ~0.5s at 30fps — camera should already be moving

export const TransitionOverlay: React.FC<TransitionOverlayProps> = ({ transitionType }) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    if (transitionType === 'FADE') {
        // Fade from black at start, fade to black before end
        const fadeInOpacity = interpolate(
            frame,
            [0, FADE_IN_FRAMES],
            [1, 0],
            { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
        );

        const fadeOutStart = durationInFrames - FADE_OUT_FRAMES;
        const fadeOutOpacity = interpolate(
            frame,
            [fadeOutStart, durationInFrames],
            [0, 1],
            { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
        );

        const opacity = Math.max(fadeInOpacity, fadeOutOpacity);

        return (
            <AbsoluteFill
                style={{
                    backgroundColor: 'black',
                    opacity,
                    pointerEvents: 'none',
                }}
            />
        );
    }

    if (transitionType === 'CROSS_DISSOLVE') {
        // Gentle fade-in only (cross-dissolve dissolves in from the previous shot).
        // The previous shot's fade-out happens in the *previous* Sequence.
        const opacity = interpolate(
            frame,
            [0, FADE_IN_FRAMES],
            [0.6, 0],
            { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
        );

        return (
            <AbsoluteFill
                style={{
                    backgroundColor: 'black',
                    opacity,
                    pointerEvents: 'none',
                }}
            />
        );
    }

    // MOTION_MATCH, CUT, PAN → no overlay, camera continuity handles the transition
    return null;
};
