/**
 * ShotNode
 * ========
 * Thin overlay-only component — no 3D rendering here.
 *
 * The 3D WebGL scene is now owned entirely by CinematicTour → ThreeCanvas →
 * DepthParallaxScene (a single persistent canvas that never remounts).
 *
 * ShotNode is responsible only for:
 *   - Transition overlays (delegated to TransitionOverlay)
 *   - Future: per-shot text / caption overlays
 */

import React from 'react';
import { AbsoluteFill } from 'remotion';
import { TransitionOverlay } from './TransitionOverlay';
import type { ShotNodeConfig } from '../Root';

interface ShotNodeProps {
    shotConfig: ShotNodeConfig;
}

export const ShotNode: React.FC<ShotNodeProps> = ({ shotConfig }) => {
    return (
        <AbsoluteFill style={{ pointerEvents: 'none' }}>
            <TransitionOverlay transitionType={shotConfig.transition_type} />
        </AbsoluteFill>
    );
};
