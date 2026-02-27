"use client";

import { Suspense } from "react";
import { Canvas, useFrame, useLoader } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { GLTFLoader } from "three-stdlib";
import { VRMLoaderPlugin, type VRM } from "@pixiv/three-vrm";

// ---------------------------------------------------------------------------
// Keyframe poses — Euler XYZ radians on normalized bone rotations
// ---------------------------------------------------------------------------
type BonePose = Partial<Record<string, [number, number, number]>>;

// World-space Z offset for each phase (model faces +Z, so +Z = stepping forward/into shot)
// midswing is now the follow-through frame (post-contact), so its Z matches contact
const HIP_Z: Record<"backswing" | "midswing" | "contact", number> = {
  backswing: -0.25,  // loaded back, weight on rear foot
  midswing:   0.25,  // follow-through — weight fully on front foot (same as contact)
  contact:    0.25,  // driven through, weight on front foot
};

// ---------------------------------------------------------------------------
// Biomechanics notes — western forehand, high-bounce, right-handed, open stance
//
// VRM local-space conventions (model faces -Z before scene.rotation.y = PI flip):
//   hips/spine/chest  Y+  = turn right (backswing coil)   Y- = turn left (contact drive-through)
//   hips/spine/chest  X+  = forward lean / flexion
//   legs              X+  = hip flexion (thigh forward)    lowerLeg X+ = knee flexion
//   legs              Z+  = abduction (spread outward)
//   upper arms in T-pose extend along ±X; right arm +X direction in local space
//   upper arm         Z-  = arm drops below T-pose (adduction down)
//                     Z+  = arm rises above T-pose (abduction up)
//
// Kinematic sequence for high-bounce western forehand:
//   1. Hips load right (+Y) and transfer/fire left (-Y) first
//   2. Chest/shoulders lag hips by ~20° then explode through
//   3. Right arm follows in low-to-high loop — arm rises steeply to contact above shoulder
//   4. Left arm extends out on backswing for counterbalance, tucks in at contact
//   5. Legs drive upward at contact (ball is high — player extends/rises)
// ---------------------------------------------------------------------------
const POSES: Record<"backswing" | "midswing" | "contact", BonePose> = {
  // ------------------------------------------------------------------
  // BACKSWING — fully coiled, weight loaded on right foot
  //   Hips turned ~40° right, chest wound ~52° right past hips
  //   Racket in low loop, elbow bent, arm dropped and pulled back
  //   Open stance: both feet near parallel to baseline, knees deeply bent
  //   Left arm extended out for counterbalance
  // ------------------------------------------------------------------
  backswing: {
    // Trunk coil — extracted from Nadal video frame 1814
    // hips.Y=0.933 (53° rightward coil), chest.Y=0.672 (38° shoulder-hip separation)
    hips:          [ 0.298,  0.933,  0.00 ],
    spine:         [ 0.15,   0.70,   0.00 ],
    chest:         [ 0.00,   0.672,  0.00 ],
    neck:          [ 0.05,  -0.30,   0.00 ],

    // Right arm: dropped into low loop — arm down (Z-) and pulled behind (X+), elbow bent
    // Z ≈ -1.20 drops arm from T-pose down toward hip; X ≈ 0.25 swings it slightly forward
    rightUpperArm: [ 0.25, -0.35, -1.20 ],
    // Elbow bent ~75° (1.30 rad) — deep bend characteristic of western low loop
    rightLowerArm: [ 1.30,  0.20,  0.30 ],
    // Wrist in slight extension / ulnar deviation for grip prep
    rightHand:     [ 0.00,  0.00, -0.20 ],

    // Left arm extended laterally — counterbalance, arm at ~57° abduction
    leftUpperArm:  [-0.20,  0.10,  1.00 ],
    leftLowerArm:  [ 0.30,  0.00,  0.00 ],

    // Legs — from Nadal video frame 1814 (X/Z kept, Y zeroed to remove axial noise)
    leftUpperLeg:  [ 0.128,  0.00,  -0.218 ],
    leftLowerLeg:  [-0.129,  0.00,   0.00  ],
    leftFoot:      [-0.30,   0.00,  -0.10  ],

    rightUpperLeg: [-0.078,  0.00,   0.086 ],
    rightLowerLeg: [-0.251,  0.00,   0.00  ],
    rightFoot:     [-0.35,   0.00,   0.10  ],
  },

  // ------------------------------------------------------------------
  // MIDSWING — hips leading unwind, arm accelerating upward
  //   Hips ~10° right (still unwinding), shoulders lagging ~25° right
  //   Right arm swinging up from low loop toward contact zone
  //   Weight transferring from right to left, legs beginning to extend
  //   Left arm starting to pull inward as hips rotate through
  // ------------------------------------------------------------------
  midswing: {
    // Trunk unwinding — extracted from Nadal video followthrough frame 3229
    // hips.Y=-0.398 (hips fired through), chest.Y=-0.381 (shoulders following)
    hips:          [ 0.167, -0.398,  0.00 ],
    spine:         [ 0.10,  -0.25,   0.00 ],
    chest:         [ 0.026, -0.381,  0.00 ],
    neck:          [ 0.05,  -0.15,   0.00 ],

    // Arm accelerating upward: Z rising from -1.20 toward +0.90
    rightUpperArm: [-0.20,  0.10, -0.50 ],
    rightLowerArm: [ 0.60,  0.10,  0.25 ],
    rightHand:     [ 0.00,  0.00, -0.10 ],

    // Left arm beginning to pull in
    leftUpperArm:  [-0.10,  0.00,  0.55 ],
    leftLowerArm:  [ 0.20,  0.00,  0.00 ],

    // Legs — interpolated midpoint between backswing and contact video frames
    leftUpperLeg:  [ 0.219,  0.00,  -0.077 ],
    leftLowerLeg:  [-0.448,  0.00,   0.00  ],
    leftFoot:      [-0.20,   0.00,  -0.08  ],

    rightUpperLeg: [-0.198,  0.00,   0.105 ],
    rightLowerLeg: [-0.244,  0.00,   0.00  ],
    rightFoot:     [-0.20,   0.00,   0.08  ],
  },

  // ------------------------------------------------------------------
  // CONTACT — ball met at/above shoulder height, full drive-through
  //   Hips fully rotated through (~37° past square = -0.65 rad)
  //   Chest slightly behind hips (-0.75 rad) — shoulder-hip separation maintained
  //   Right arm elevated steeply: Z ≈ +0.95 (arm above shoulder line)
  //   Elbow partially extended at high contact (less bent than midswing)
  //   Legs fully extended, rising on toes / driving upward for high ball
  //   Left arm tucked across body for rotational counterbalance
  //   Wrist rolling over for topspin (rightHand Z+)
  // ------------------------------------------------------------------
  contact: {
    // Trunk at contact — hips driven through, script contact frame 3214
    hips:          [ 0.273, -0.600,  0.00 ],
    spine:         [-0.05,  -0.42,   0.00 ],
    chest:         [-0.10,  -0.500,  0.00 ],
    neck:          [-0.05,  -0.25,   0.00 ],

    // Right arm fully elevated for shoulder-height+ contact:
    //   X ≈ -0.55: arm swung forward past neutral (internal shoulder rotation at contact)
    //   Z ≈ +0.95: arm abducted upward — above shoulder, reaching up to high ball
    //   Y ≈ +0.40: internal rotation through shoulder joint
    rightUpperArm: [-0.55,  0.40,  0.95 ],
    // Elbow more extended at high contact vs mid-height ball; slight pronation
    rightLowerArm: [-0.25,  0.00,  0.30 ],
    // Wrist snap and roll-over — generates topspin; western grip knuckle rotates over
    rightHand:     [ 0.00,  0.00,  0.35 ],

    // Left arm tucked across body — elbow bent, arm pulled in tight
    leftUpperArm:  [ 0.10, -0.25,  0.30 ],
    leftLowerArm:  [ 0.55,  0.00,  0.00 ],

    // Legs — from Nadal video frame 3214 (X/Z kept, Y zeroed to remove axial noise)
    leftUpperLeg:  [ 0.366,  0.00,  -0.192 ],
    leftLowerLeg:  [-0.839,  0.00,   0.00  ],
    leftFoot:      [-0.10,   0.00,  -0.08  ],

    rightUpperLeg: [-0.357,  0.00,   0.283 ],
    rightLowerLeg: [-0.357,  0.00,   0.00  ],
    rightFoot:     [-0.05,   0.00,   0.08  ],
  },
};

function smoothstep(t: number) {
  return t * t * (3 - 2 * t);
}

// ---------------------------------------------------------------------------
// VRMAnimator — owns useFrame, receives a loaded VRM
// ---------------------------------------------------------------------------
function VRMAnimator({ vrm }: { vrm: VRM }) {
  useFrame(({ clock }, delta) => {
    // 4-second cycle:
    //   0.00–0.35 : hold at backswing (coiled, loaded)
    //   0.35–0.60 : swing directly to contact — one uninterrupted arc (linear)
    //   0.60–0.75 : follow-through to midswing pose (post-contact arm finish)
    //   0.75–1.00 : smooth reset back to backswing
    const elapsed = clock.getElapsedTime() % 4;
    const t = elapsed / 4; // 0..1

    let fromKey: "backswing" | "midswing" | "contact";
    let toKey:   "backswing" | "midswing" | "contact";
    let alpha: number;

    if (t < 0.35) {
      // hold at backswing — player is coiled, ready to swing
      fromKey = "backswing";
      toKey   = "backswing";
      alpha   = 0;
    } else if (t < 0.60) {
      // the swing — backswing straight to contact, no intermediate stop
      // linear so there is no deceleration midway
      fromKey = "backswing";
      toKey   = "contact";
      alpha   = (t - 0.35) / 0.25;
    } else if (t < 0.75) {
      // follow-through: arm continues past contact into finish position
      fromKey = "contact";
      toKey   = "midswing";
      alpha   = (t - 0.60) / 0.15;
    } else {
      // reset smoothly back to backswing
      fromKey = "midswing";
      toKey   = "backswing";
      alpha   = smoothstep((t - 0.75) / 0.25);
    }

    const from = POSES[fromKey];
    const to   = POSES[toKey];

    // Animate bone rotations
    const allBones = new Set([...Object.keys(from), ...Object.keys(to)]);
    for (const boneName of allBones) {
      const node = vrm.humanoid.getNormalizedBoneNode(boneName as Parameters<typeof vrm.humanoid.getNormalizedBoneNode>[0]);
      if (!node) continue;
      const fa = from[boneName] ?? [0, 0, 0];
      const ta = to[boneName]   ?? [0, 0, 0];
      node.rotation.x = fa[0] + (ta[0] - fa[0]) * alpha;
      node.rotation.y = fa[1] + (ta[1] - fa[1]) * alpha;
      node.rotation.z = fa[2] + (ta[2] - fa[2]) * alpha;
    }

    // Animate scene Z position — step back on load, drive forward through contact
    const fromZ = HIP_Z[fromKey];
    const toZ   = HIP_Z[toKey];
    vrm.scene.position.z = fromZ + (toZ - fromZ) * alpha;

    vrm.update(delta);
  });

  return <primitive object={vrm.scene} />;
}

// ---------------------------------------------------------------------------
// VRMLoader — suspends until the GLB/VRM is loaded
// ---------------------------------------------------------------------------
function VRMLoader({ url }: { url: string }) {
  const gltf = useLoader(GLTFLoader, url, (loader: any) => {
    loader.register((parser: any) => new VRMLoaderPlugin(parser));
  });

  const vrm = (gltf as unknown as { userData: { vrm: VRM } }).userData.vrm as VRM;
  vrm.scene.rotation.y = Math.PI; // face the camera

  return <VRMAnimator vrm={vrm} />;
}

// ---------------------------------------------------------------------------
// Court plane
// ---------------------------------------------------------------------------
function Court() {
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
      <planeGeometry args={[4, 3]} />
      <meshStandardMaterial color="#4ade80" roughness={0.8} />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// Scene root (inside Canvas)
// ---------------------------------------------------------------------------
function Scene() {
  return (
    <>
      <ambientLight intensity={0.6} />
      <directionalLight position={[3, 6, 4]} intensity={1.2} castShadow />
      <directionalLight position={[-2, 3, -2]} intensity={0.3} />
      <Court />
      <Suspense fallback={null}>
        <VRMLoader url="/models/tennis-player.vrm" />
      </Suspense>
      <OrbitControls
        target={[0, 1, 0]}
        makeDefault
        enableDamping
        minDistance={2}
        maxDistance={8}
        enablePan={false}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Public export — Canvas wrapper
// ---------------------------------------------------------------------------
export default function HighBounceForehand3D({ caption }: { caption?: string }) {
  return (
    <div>
      <Canvas
        style={{ width: "100%", height: 320 }}
        camera={{ position: [1.8, 1.4, 3.2], fov: 45 }}
        onCreated={({ camera }) => {
          camera.lookAt(0, 1, 0);
        }}
      >
        <Scene />
      </Canvas>
      {caption && (
        <p className="text-xs text-slate-500 text-center mt-1.5 italic">{caption}</p>
      )}
    </div>
  );
}
