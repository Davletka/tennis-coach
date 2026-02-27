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

// No vertical offset — bone rotations handle the visual squat depth naturally

// ---------------------------------------------------------------------------
// Biomechanics notes — barbell back squat, high-bar, shoulder-width stance
//
// VRM local-space conventions:
//   hips/spine/chest  X+  = forward flexion (lean forward into the squat)
//   upperLeg          X+  = hip flexion (thigh swings forward relative to pelvis)
//   lowerLeg          X-  = knee flexion (shin bends BACKWARD — anatomically correct)
//   upperLeg          Z-  = left leg abduction (knees push out over toes)
//   upperLeg          Z+  = right leg abduction
//   foot              X-  = dorsiflexion (ankle flexed, heels stay down)
//   foot              X+  = plantarflexion (toes pointed)
//
// Squat kinematic sequence:
//   1. Hips push BACK and DOWN simultaneously — not just down (hip hinge)
//   2. Knees track OUT over toes — external rotation, slight Z abduction
//   3. Torso leans forward to keep barbell over mid-foot (balance)
//   4. Head stays neutral — chin slightly tucked, eyes on horizon
//   5. Arms hold bar on upper traps: elbows pulled down, wrists straight
//   6. Ankles dorsiflex to allow depth — heels remain flat on floor
// ---------------------------------------------------------------------------
const POSES: Record<"top" | "bottom", BonePose> = {
  // ------------------------------------------------------------------
  // TOP — standing upright, bar on upper traps, core braced
  // ------------------------------------------------------------------
  top: {
    hips:          [ 0.05,  0.00,  0.00 ],
    spine:         [ 0.05,  0.00,  0.00 ],
    chest:         [ 0.00,  0.00,  0.00 ],
    neck:          [ 0.00,  0.00,  0.00 ],

    // High-bar grip: upper arms adducted DOWN from T-pose (Z-/Z+),
    // elbows point backward-down; forearms heavily flexed upward to reach bar
    rightUpperArm: [-0.20,  0.15, -0.95 ],
    rightLowerArm: [ 1.80,  0.00,  0.10 ],
    rightHand:     [ 0.00, -0.20,  0.00 ],

    leftUpperArm:  [-0.20, -0.15,  0.95 ],
    leftLowerArm:  [ 1.80,  0.00, -0.10 ],
    leftHand:      [ 0.00,  0.20,  0.00 ],

    // Shoulder-width stance, toes turned out ~15°
    leftUpperLeg:  [ 0.00,  0.00, -0.22 ],
    leftLowerLeg:  [-0.05,  0.00,  0.00 ],
    leftFoot:      [ 0.05,  0.00, -0.08 ],

    rightUpperLeg: [ 0.00,  0.00,  0.22 ],
    rightLowerLeg: [-0.05,  0.00,  0.00 ],
    rightFoot:     [ 0.05,  0.00,  0.08 ],
  },

  // ------------------------------------------------------------------
  // BOTTOM — thighs at/below parallel, deep knee bend
  //   Key: torso stays RELATIVELY UPRIGHT — lean is ~20–25° from vertical,
  //   NOT 45–90°. The depth comes from the LEGS bending, not the torso folding.
  //   hips/spine/chest X values stay small — stacking them causes the
  //   "going to sleep" look. The thigh flexion (upperLeg X) does the work.
  // ------------------------------------------------------------------
  bottom: {
    // Moderate forward lean — bar stays over mid-foot but torso is NOT horizontal
    hips:          [ 0.22,  0.00,  0.00 ],
    spine:         [ 0.08,  0.00,  0.00 ],
    chest:         [ 0.03,  0.00,  0.00 ],
    neck:          [-0.12,  0.00,  0.00 ],  // head up — eyes on horizon

    // Arms unchanged — bar stays on traps
    rightUpperArm: [-0.20,  0.15, -0.95 ],
    rightLowerArm: [ 1.80,  0.00,  0.10 ],
    rightHand:     [ 0.00, -0.20,  0.00 ],

    leftUpperArm:  [-0.20, -0.15,  0.95 ],
    leftLowerArm:  [ 1.80,  0.00, -0.10 ],
    leftHand:      [ 0.00,  0.20,  0.00 ],

    // Deep hip flexion + knees pushed out over toes
    leftUpperLeg:  [ 1.15,  0.00, -0.38 ],
    leftLowerLeg:  [-1.50,  0.00,  0.00 ],
    leftFoot:      [-0.25,  0.00, -0.08 ],  // dorsiflexion — heels stay down

    rightUpperLeg: [ 1.15,  0.00,  0.38 ],
    rightLowerLeg: [-1.50,  0.00,  0.00 ],
    rightFoot:     [-0.25,  0.00,  0.08 ],
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
    // 5-second rep cycle matching real squat tempo:
    //   0.00–0.50 (2.5 s): controlled descent  — top → bottom
    //   0.50–0.56 (0.3 s): pause at bottom     — hold (stretch reflex before drive)
    //   0.56–0.86 (1.5 s): drive up            — bottom → top
    //   0.86–1.00 (0.7 s): rest at top         — breathe before next rep
    const elapsed = clock.getElapsedTime() % 5;
    const t = elapsed / 5; // 0..1

    let fromKey: "top" | "bottom";
    let toKey:   "top" | "bottom";
    let alpha: number;

    if (t < 0.50) {
      // Descent — smooth eccentric
      fromKey = "top";
      toKey   = "bottom";
      alpha   = smoothstep(t / 0.50);
    } else if (t < 0.56) {
      // Hold at bottom
      fromKey = "bottom";
      toKey   = "bottom";
      alpha   = 0;
    } else if (t < 0.86) {
      // Ascent — drive up concentric
      fromKey = "bottom";
      toKey   = "top";
      alpha   = smoothstep((t - 0.56) / 0.30);
    } else {
      // Rest at top
      fromKey = "top";
      toKey   = "top";
      alpha   = 0;
    }

    const from = POSES[fromKey];
    const to   = POSES[toKey];

    // Animate bone rotations
    const allBones = new Set([...Object.keys(from), ...Object.keys(to)]);
    for (const boneName of allBones) {
      const node = vrm.humanoid.getNormalizedBoneNode(
        boneName as Parameters<typeof vrm.humanoid.getNormalizedBoneNode>[0],
      );
      if (!node) continue;
      const fa = from[boneName] ?? [0, 0, 0];
      const ta = to[boneName]   ?? [0, 0, 0];
      node.rotation.x = fa[0] + (ta[0] - fa[0]) * alpha;
      node.rotation.y = fa[1] + (ta[1] - fa[1]) * alpha;
      node.rotation.z = fa[2] + (ta[2] - fa[2]) * alpha;
    }

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
// Floor plane
// ---------------------------------------------------------------------------
function Floor() {
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
      <planeGeometry args={[4, 3]} />
      <meshStandardMaterial color="#94a3b8" roughness={0.9} />
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
      <Floor />
      <Suspense fallback={null}>
        <VRMLoader url="/models/tennis-player.vrm" />
      </Suspense>
      <OrbitControls
        target={[0, 0.9, 0]}
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
export default function SquatScene3D({ caption }: { caption?: string }) {
  return (
    <div>
      <Canvas
        style={{ width: "100%", height: 320 }}
        camera={{ position: [2.2, 1.2, 2.8], fov: 45 }}
        onCreated={({ camera }) => {
          camera.lookAt(0, 0.9, 0);
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
