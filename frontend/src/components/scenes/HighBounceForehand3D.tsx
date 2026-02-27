"use client";

import { useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";

// ---------------------------------------------------------------------------
// Static joint positions (Y-up, figure ~1.8 units tall)
// ---------------------------------------------------------------------------
const J = {
  HEAD:           new THREE.Vector3(0,    1.68,  0),
  NECK:           new THREE.Vector3(0,    1.55,  0),
  L_SHOULDER:     new THREE.Vector3(-0.22, 1.45,  0),
  R_SHOULDER:     new THREE.Vector3( 0.22, 1.45,  0),
  HIP_CENTER:     new THREE.Vector3(0,    1.00,  0),
  L_HIP:          new THREE.Vector3(-0.14, 1.00,  0),
  R_HIP:          new THREE.Vector3( 0.14, 1.00,  0),
  L_KNEE:         new THREE.Vector3(-0.20, 0.55,  0.04),
  L_ANKLE:        new THREE.Vector3(-0.22, 0.06,  0),
  R_KNEE:         new THREE.Vector3( 0.22, 0.45, -0.08),
  R_ANKLE:        new THREE.Vector3( 0.28, 0.06, -0.02),
  L_ELBOW:        new THREE.Vector3(-0.40, 1.32,  0.10),
  L_WRIST:        new THREE.Vector3(-0.52, 1.18,  0.18),
};

// ---------------------------------------------------------------------------
// Animated keyframes — right elbow & wrist only
// ---------------------------------------------------------------------------
const KF = {
  backswing: {
    elbow: new THREE.Vector3( 0.36, 1.20, -0.25),
    wrist: new THREE.Vector3( 0.45, 0.90, -0.38),
  },
  midswing: {
    elbow: new THREE.Vector3( 0.52, 1.42,  0.05),
    wrist: new THREE.Vector3( 0.72, 1.42,  0.12),
  },
  contact: {
    elbow: new THREE.Vector3( 0.48, 1.50,  0.15),
    wrist: new THREE.Vector3( 0.66, 1.68,  0.20),
  },
};

// ---------------------------------------------------------------------------
// Cylinder-between-joints helper
// Returns { position, quaternion, length } so we can apply to a mesh
// ---------------------------------------------------------------------------
function limbTransform(A: THREE.Vector3, B: THREE.Vector3) {
  const mid = A.clone().add(B).multiplyScalar(0.5);
  const length = A.distanceTo(B);
  const dir = B.clone().sub(A).normalize();
  const up = new THREE.Vector3(0, 1, 0);
  let quat: THREE.Quaternion;
  if (Math.abs(dir.dot(up) + 1) < 0.0001) {
    // dir ≈ -Y → 180° around X
    quat = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);
  } else {
    quat = new THREE.Quaternion().setFromUnitVectors(up, dir);
  }
  return { position: mid, quaternion: quat, length };
}

// Mutates a mesh ref to match the limb between A and B
function applyLimbTransform(
  mesh: THREE.Mesh,
  A: THREE.Vector3,
  B: THREE.Vector3,
) {
  const { position, quaternion, length } = limbTransform(A, B);
  mesh.position.copy(position);
  mesh.quaternion.copy(quaternion);
  mesh.scale.set(1, length, 1);
}

// Smoothstep
function smoothstep(t: number) {
  return t * t * (3 - 2 * t);
}

// ---------------------------------------------------------------------------
// Static limb component
// ---------------------------------------------------------------------------
function StaticLimb({
  A,
  B,
  radius = 0.025,
  color = "#334155",
}: {
  A: THREE.Vector3;
  B: THREE.Vector3;
  radius?: number;
  color?: string;
}) {
  const { position, quaternion, length } = useMemo(
    () => limbTransform(A, B),
    [A, B],
  );
  return (
    <mesh position={position} quaternion={quaternion} scale={[1, length, 1]}>
      <cylinderGeometry args={[radius, radius, 1, 8]} />
      <meshStandardMaterial color={color} />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// Animated stick figure — handles right arm + racket imperatively
// ---------------------------------------------------------------------------
function StickFigure() {
  // Refs for animated meshes
  const rUpperArmRef = useRef<THREE.Mesh>(null!);
  const rForearmRef  = useRef<THREE.Mesh>(null!);
  const racketRef    = useRef<THREE.Group>(null!);
  const ballRef      = useRef<THREE.Mesh>(null!);

  // Working vectors (reused each frame — no allocations)
  const elbowPos = useRef(KF.backswing.elbow.clone());
  const wristPos = useRef(KF.backswing.wrist.clone());

  useFrame(({ clock }) => {
    const t = (clock.getElapsedTime() % 3) / 3; // 0..1 over 3-second cycle

    // Determine which segment we're in and local progress
    let from: { elbow: THREE.Vector3; wrist: THREE.Vector3 };
    let to:   { elbow: THREE.Vector3; wrist: THREE.Vector3 };
    let alpha: number;

    if (t < 1 / 3) {
      from  = KF.backswing;
      to    = KF.midswing;
      alpha = smoothstep(t * 3);
    } else if (t < 2 / 3) {
      from  = KF.midswing;
      to    = KF.contact;
      alpha = smoothstep((t - 1 / 3) * 3);
    } else {
      from  = KF.contact;
      to    = KF.backswing;
      alpha = smoothstep((t - 2 / 3) * 3);
    }

    elbowPos.current.lerpVectors(from.elbow, to.elbow, alpha);
    wristPos.current.lerpVectors(from.wrist, to.wrist, alpha);

    if (rUpperArmRef.current) {
      applyLimbTransform(rUpperArmRef.current, J.R_SHOULDER, elbowPos.current);
    }
    if (rForearmRef.current) {
      applyLimbTransform(rForearmRef.current, elbowPos.current, wristPos.current);
    }

    // Racket: position at wrist, orientation matches forearm direction
    if (racketRef.current) {
      racketRef.current.position.copy(wristPos.current);
      const dir = wristPos.current.clone().sub(elbowPos.current).normalize();
      const up = new THREE.Vector3(0, 1, 0);
      if (Math.abs(dir.dot(up) + 1) > 0.0001) {
        racketRef.current.quaternion.setFromUnitVectors(up, dir);
      }
    }

    // Ball: fades in at contact phase
    if (ballRef.current) {
      const mat = ballRef.current.material as THREE.MeshStandardMaterial;
      // Contact phase is t in [1/3, 2/3], peak at t=0.5
      const contactT = Math.max(0, Math.min(1, (t - 1 / 3) * 3));
      const fade = contactT < 0.5
        ? smoothstep(contactT * 2)
        : smoothstep((1 - contactT) * 2);
      mat.opacity = fade * 0.9;
      // Position ball at wrist during contact
      ballRef.current.position.copy(wristPos.current);
      ballRef.current.position.x += 0.08;
      ballRef.current.position.y += 0.06;
    }
  });

  return (
    <group>
      {/* Head */}
      <mesh position={J.HEAD}>
        <sphereGeometry args={[0.12, 12, 8]} />
        <meshStandardMaterial color="#fde8d8" />
      </mesh>

      {/* Torso */}
      <StaticLimb A={J.NECK} B={J.HIP_CENTER} radius={0.03} color="#334155" />

      {/* Spine top (neck–head connection) */}
      <StaticLimb A={J.HEAD} B={J.NECK} radius={0.02} color="#334155" />

      {/* Shoulders */}
      <StaticLimb A={J.L_SHOULDER} B={J.R_SHOULDER} radius={0.025} color="#334155" />

      {/* Hips */}
      <StaticLimb A={J.L_HIP} B={J.R_HIP} radius={0.025} color="#334155" />

      {/* Hip–torso connection */}
      <StaticLimb A={J.HIP_CENTER} B={J.L_HIP} radius={0.022} color="#334155" />
      <StaticLimb A={J.HIP_CENTER} B={J.R_HIP} radius={0.022} color="#334155" />

      {/* Left leg */}
      <StaticLimb A={J.L_HIP} B={J.L_KNEE} radius={0.025} color="#334155" />
      <StaticLimb A={J.L_KNEE} B={J.L_ANKLE} radius={0.022} color="#334155" />

      {/* Right leg (open stance) */}
      <StaticLimb A={J.R_HIP} B={J.R_KNEE} radius={0.025} color="#334155" />
      <StaticLimb A={J.R_KNEE} B={J.R_ANKLE} radius={0.022} color="#334155" />

      {/* Left arm (balance arm — static) */}
      <StaticLimb A={J.L_SHOULDER} B={J.L_ELBOW} radius={0.022} color="#334155" />
      <StaticLimb A={J.L_ELBOW} B={J.L_WRIST} radius={0.020} color="#334155" />

      {/* Right upper arm (animated) */}
      <mesh ref={rUpperArmRef}>
        <cylinderGeometry args={[0.025, 0.025, 1, 8]} />
        <meshStandardMaterial color="#334155" />
      </mesh>

      {/* Right forearm (animated) */}
      <mesh ref={rForearmRef}>
        <cylinderGeometry args={[0.022, 0.022, 1, 8]} />
        <meshStandardMaterial color="#334155" />
      </mesh>

      {/* Joint dots at knees and elbows */}
      {[J.L_KNEE, J.R_KNEE, J.L_ELBOW, J.L_WRIST].map((pos, i) => (
        <mesh key={i} position={pos}>
          <sphereGeometry args={[0.035, 8, 6]} />
          <meshStandardMaterial color="#64748b" />
        </mesh>
      ))}

      {/* Racket group — positioned/oriented imperatively */}
      <group ref={racketRef}>
        {/* Handle: extends behind wrist along forearm direction */}
        <mesh position={[0, -0.18, 0]}>
          <cylinderGeometry args={[0.012, 0.012, 0.28, 6]} />
          <meshStandardMaterial color="#7c3aed" />
        </mesh>
        {/* Head frame (torus) */}
        <mesh position={[0, 0.14, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.14, 0.015, 6, 20]} />
          <meshStandardMaterial color="#7c3aed" />
        </mesh>
        {/* Strings hint — two thin cross-pieces */}
        <mesh position={[0, 0.14, 0]}>
          <cylinderGeometry args={[0.003, 0.003, 0.26, 4]} />
          <meshStandardMaterial color="#a78bfa" opacity={0.6} transparent />
        </mesh>
        <mesh position={[0, 0.14, 0]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.003, 0.003, 0.26, 4]} />
          <meshStandardMaterial color="#a78bfa" opacity={0.6} transparent />
        </mesh>
      </group>

      {/* Ball — fades in at contact */}
      <mesh ref={ballRef}>
        <sphereGeometry args={[0.05, 10, 8]} />
        <meshStandardMaterial color="#facc15" opacity={0} transparent />
      </mesh>
    </group>
  );
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
      <StickFigure />
      <OrbitControls
        target={[0, 1.1, 0]}
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
          camera.lookAt(0, 1.1, 0);
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
