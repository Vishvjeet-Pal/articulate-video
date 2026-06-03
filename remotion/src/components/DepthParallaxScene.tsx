/**
 * DepthParallaxScene
 * ==================
 * Renders a property photo with Collov-style cinematic camera motion.
 *
 * Design philosophy (matching Collov reference):
 *   - The image fills the frame and moves SLOWLY as one piece
 *   - Depth map creates subtle vertex displacement (not rubber-sheet warping)
 *   - The "depth" feel comes from the camera moving through Z space,
 *     not from aggressive mesh distortion
 *   - No oscillation, no shake — only smooth eased motion
 *
 * Displacement tuning:
 *   - FG_DISPLACEMENT_BASE = 60  (was 280 — that was causing rubber-sheet warping)
 *   - BG_DISPLACEMENT_BASE = 20  (was 80)
 *   - Background layer is fully opaque — semi-transparency caused ghosting
 *
 * The camera is driven by VirtualCamera.computeCameraState() every frame.
 */

import React, { useMemo } from 'react';
import { useLoader, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { computeCameraState } from './VirtualCamera';
import type { MotionType, MotionCurve, ProceduralMotionTarget } from '../Root';

// Must mirror backend/app/core/config.py PLANE_OVERSCALE_FACTOR
// 1.25 gives a 25% margin for camera travel before revealing edges
const PLANE_OVERSCALE_FACTOR = 1.25;

// Displacement scale per layer (world units).
// Keep these LOW — this is subtle depth enhancement, not 3D modelling.
// At 280 it looked like a warped rubber sheet. At 60 it looks cinematic.
const FG_DISPLACEMENT_BASE = 60;
const BG_DISPLACEMENT_BASE = 18;

// Z separation between layers — small enough to avoid frustum clipping issues
const LAYER_Z_SEPARATION = 20;

interface DepthParallaxSceneProps {
    imageUrl: string;
    depthUrl: string | null;
    proceduralTargets: ProceduralMotionTarget[];
    durationInFrames: number;
    relativeFrame: number;
    motionType: MotionType;
    motionStrength: number;
    motionCurve: MotionCurve;
    depthParallaxStrength: number;
    cameraStart: [number, number, number];
    cameraEnd: [number, number, number];
    width: number;
    height: number;
}

// 1×1 mid-grey = neutral depth (all vertices displaced equally = no warping)
const NEUTRAL_DEPTH_URL =
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVQI12NgAAAAAgAB4iG8MwAAAABJRU5ErkJggg==';

export const DepthParallaxScene: React.FC<DepthParallaxSceneProps> = ({
    imageUrl,
    depthUrl,
    proceduralTargets,
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
    const colorMap = useLoader(THREE.TextureLoader, imageUrl);
    const depthMap = useLoader(THREE.TextureLoader, depthUrl ?? NEUTRAL_DEPTH_URL);

    // Only apply depth displacement when a real depth map is provided.
    // The neutral 1×1 grey would cause uniform displacement (no parallax benefit).
    const effectiveDepthStrength = depthUrl ? depthParallaxStrength : 0;

    // Foreground layer — primary image, mild depth displacement
    const fgMaterial = useMemo(() => {
        const mat = new THREE.MeshStandardMaterial({
            map: colorMap,
            displacementMap: depthUrl ? depthMap : undefined,
            displacementScale: FG_DISPLACEMENT_BASE * effectiveDepthStrength,
            roughness: 1.0,
            metalness: 0,
            transparent: false,
        });

        // Procedural foliage sway (only active when a FOLIAGE_SWAY target exists)
        const foliageTarget = proceduralTargets.find(t => t.type === 'FOLIAGE_SWAY');
        if (foliageTarget) {
            mat.onBeforeCompile = (shader) => {
                shader.uniforms.uFrame = { value: 0 };
                shader.vertexShader = `uniform float uFrame;\n${shader.vertexShader}`.replace(
                    `#include <begin_vertex>`,
                    `#include <begin_vertex>
                    // Very gentle foliage sway — amplitude kept small to avoid warping
                    float sway = sin(uFrame * 0.03 + position.x * 0.5) * ${foliageTarget.intensity * 0.02} * max(0.0, position.y);
                    transformed.x += sway;`
                );
                mat.userData.shader = shader;
            };
        }

        return mat;
    }, [colorMap, depthMap, depthUrl, effectiveDepthStrength, proceduralTargets]);

    // Background layer — slightly larger, lower displacement.
    // Fully OPAQUE — previous semi-transparency caused ghosting artifacts.
    const bgMaterial = useMemo(() => {
        return new THREE.MeshStandardMaterial({
            map: colorMap,
            displacementMap: depthUrl ? depthMap : undefined,
            displacementScale: BG_DISPLACEMENT_BASE * effectiveDepthStrength,
            roughness: 1.0,
            metalness: 0,
            transparent: false,
            opacity: 1.0,
        });
    }, [colorMap, depthMap, depthUrl, effectiveDepthStrength]);

    // Drive the camera every frame via VirtualCamera
    useFrame(({ camera }) => {
        // Update foliage uniform
        if (fgMaterial.userData?.shader?.uniforms?.uFrame) {
            fgMaterial.userData.shader.uniforms.uFrame.value = relativeFrame;
        }

        const state = computeCameraState(
            relativeFrame,
            durationInFrames,
            motionType,
            motionStrength,
            motionCurve,
            cameraStart,
            cameraEnd,
        );

        camera.position.set(state.x, state.y, state.z);

        // Always look straight down Z — no rotation.
        // Camera panning in X/Y IS the motion; we never tilt.
        camera.rotation.set(0, 0, 0);
        camera.updateMatrixWorld();
    });

    const planeW = width  * PLANE_OVERSCALE_FACTOR;
    const planeH = height * PLANE_OVERSCALE_FACTOR;

    return (
        <>
            {/* Neutral, even lighting — no dramatic shadows that fight the photo */}
            <ambientLight intensity={1.0} />

            {/*
              * Background layer — fills slightly more than the frame.
              * Positioned slightly behind (negative Z) to create layer separation.
              * Low displacement makes it feel "further away" than the foreground.
              */}
            <mesh position={[0, 0, -LAYER_Z_SEPARATION]}>
                <planeGeometry args={[planeW * 1.06, planeH * 1.06, 64, 64]} />
                <primitive object={bgMaterial} attach="material" />
            </mesh>

            {/*
              * Foreground layer — the primary visible image.
              * Higher displacement creates depth pop at salient features.
              * Uses 128×128 segments for smooth depth contours (256 was overkill
              * and caused vertex jitter at extreme displacement values).
              */}
            <mesh position={[0, 0, 0]}>
                <planeGeometry args={[planeW, planeH, 128, 128]} />
                <primitive object={fgMaterial} attach="material" />
            </mesh>
        </>
    );
};
