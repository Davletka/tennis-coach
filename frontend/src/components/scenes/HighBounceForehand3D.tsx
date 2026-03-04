"use client";

import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";

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
