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

const POSES: Record<"backswing" | "midswing" | "contact", BonePose> = {
  backswing: {
    hips:          [0,    0.7,  0],
    chest:         [0.1,  0.9,  0],
    rightUpperArm: [0.2, -0.5, -1.4],
    rightLowerArm: [0,    0,    0.4],
    leftUpperArm:  [0,    0,    0.8],
    neck:          [0,    0.3,  0],
  },
  midswing: {
    hips:          [0,    0.2,  0],
    chest:         [0,    0.3,  0],
    rightUpperArm: [0.1,  0.2, -0.6],
    rightLowerArm: [0,    0,    0.1],
    leftUpperArm:  [0,    0,    0.5],
    neck:          [0,    0.1,  0],
  },
  contact: {
    hips:          [0,   -0.4,  0],
    chest:        [-0.1, -0.5,  0],
    rightUpperArm:[-0.3,  0.6,  0.5],
    rightLowerArm:[-0.3,  0,    0.2],
    rightHand:    [ 0,    0,    0.3],
    leftUpperArm: [ 0,    0,    0.3],
    neck:         [ 0,   -0.2,  0],
  },
};

const PHASE_KEYS: Array<"backswing" | "midswing" | "contact"> = [
  "backswing",
  "midswing",
  "contact",
];

function smoothstep(t: number) {
  return t * t * (3 - 2 * t);
}

// ---------------------------------------------------------------------------
// VRMAnimator — owns useFrame, receives a loaded VRM
// ---------------------------------------------------------------------------
function VRMAnimator({ vrm }: { vrm: VRM }) {
  useFrame(({ clock }, delta) => {
    const t = (clock.getElapsedTime() % 3) / 3; // 0..1 over 3-second cycle

    let fromKey: "backswing" | "midswing" | "contact";
    let toKey:   "backswing" | "midswing" | "contact";
    let alpha: number;

    if (t < 1 / 3) {
      fromKey = "backswing";
      toKey   = "midswing";
      alpha   = smoothstep(t * 3);
    } else if (t < 2 / 3) {
      fromKey = "midswing";
      toKey   = "contact";
      alpha   = smoothstep((t - 1 / 3) * 3);
    } else {
      fromKey = "contact";
      toKey   = "backswing";
      alpha   = smoothstep((t - 2 / 3) * 3);
    }

    const from = POSES[fromKey];
    const to   = POSES[toKey];

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
