/**
 * TransitionOverlay
 * =================
 * Composites transition effects on top of the 3D scene.
 *
 * Supported types:
 *   FADE          — fade from black at shot start + fade to black before end
 *   CROSS_DISSOLVE — full black dip at the start (simulates walking through
 *                    a doorway into the next room)
 *   MOTION_MATCH  — no overlay; camera velocity handles the cut
 *   CUT           — no overlay
 */

import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';
import type { TransitionType } from '../Root';

interface TransitionOverlayProps {
    transitionType: TransitionType;
}

// Transition timing constants (all in frames @ 30fps)
const FADE_IN_FRAMES       = 18;  // 0.6s — fade from black at shot start
const FADE_OUT_FRAMES      = 18;  // 0.6s — fade to black before shot end
const DISSOLVE_DIP_FRAMES  = 12;  // 0.4s — quick black dip at room-change cut point

export const TransitionOverlay: React.FC<TransitionOverlayProps> = ({ transitionType }) => {
    const frame = useCurrentFrame();
    const { durationInFrames } = useVideoConfig();

    if (transitionType === 'FADE') {
        // Full fade — black at start and black at end.
        // Used for: first shot, shots coming from a distant room.
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
        // Room-change transition.
        // Simulates a person stepping through a doorway:
        //   - Shot starts with a brief black dip (like passing through a door frame)
        //   - Then quickly clears to reveal the new room
        //
        // The PREVIOUS shot's WALK_FORWARD has already panned the camera to the
        // edge of the frame (right/left toward the next room). This dip creates a
        // natural "blink" moment as the camera enters the new space.
        const opacity = interpolate(
            frame,
            [0, DISSOLVE_DIP_FRAMES],
            [1, 0],
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

    if (transitionType === 'MOTION_MATCH') {
        // No overlay — the camera is already moving so the cut is invisible.
        // Used for open-plan rooms (Living Room → Kitchen in an open floor plan).
        return null;
    }

    // CUT, PAN → no overlay
    return null;
};
