import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import {
  Float,
  OrbitControls,
  PerspectiveCamera,
  Sphere,
  Line,
} from "@react-three/drei";
import * as THREE from "three";

function CoreCube() {
  const mesh = useRef();

  useFrame((_, delta) => {
    if (!mesh.current) return;

    mesh.current.rotation.x += delta * 0.18;
    mesh.current.rotation.y += delta * 0.32;
    mesh.current.rotation.z += delta * 0.08;
  });

  return (
    <Float speed={1.2} rotationIntensity={0.25} floatIntensity={0.5}>
      <group ref={mesh}>
        <mesh>
          <icosahedronGeometry args={[1.55, 1]} />
          <meshStandardMaterial
            color="#6d5dfc"
            emissive="#3928c7"
            emissiveIntensity={1.7}
            metalness={0.85}
            roughness={0.18}
            wireframe
          />
        </mesh>

        <mesh scale={0.72}>
          <icosahedronGeometry args={[1.55, 1]} />
          <meshStandardMaterial
            color="#14b8ff"
            emissive="#075985"
            emissiveIntensity={1.5}
            metalness={0.9}
            roughness={0.12}
          />
        </mesh>

        <mesh scale={0.38}>
          <sphereGeometry args={[1.2, 32, 32]} />
          <meshStandardMaterial
            color="#d9d8ff"
            emissive="#7c3aed"
            emissiveIntensity={2}
            metalness={1}
            roughness={0.1}
          />
        </mesh>
      </group>
    </Float>
  );
}

function OrbitalRing({ radius, rotation, speed, color }) {
  const ring = useRef();

  useFrame((_, delta) => {
    if (!ring.current) return;

    ring.current.rotation.z += delta * speed;
    ring.current.rotation.x += delta * speed * 0.22;
  });

  return (
    <group ref={ring} rotation={rotation}>
      <mesh>
        <torusGeometry args={[radius, 0.009, 16, 128]} />
        <meshBasicMaterial color={color} transparent opacity={0.55} />
      </mesh>

      <mesh position={[radius, 0, 0]}>
        <sphereGeometry args={[0.055, 16, 16]} />
        <meshBasicMaterial color={color} />
      </mesh>
    </group>
  );
}

function NetworkParticles() {
  const particles = useMemo(() => {
    const points = [];

    for (let i = 0; i < 260; i++) {
      const radius = 4.5 + Math.random() * 7;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);

      points.push([
        radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.sin(phi) * Math.sin(theta),
        radius * Math.cos(phi),
      ]);
    }

    return points;
  }, []);

  const ref = useRef();

  useFrame((_, delta) => {
    if (!ref.current) return;

    ref.current.rotation.y += delta * 0.018;
    ref.current.rotation.x += delta * 0.006;
  });

  return (
    <group ref={ref}>
      {particles.map((position, index) => (
        <mesh key={index} position={position}>
          <sphereGeometry args={[0.018 + (index % 4) * 0.006, 8, 8]} />
          <meshBasicMaterial
            color={index % 2 === 0 ? "#14b8ff" : "#8b5cf6"}
            transparent
            opacity={0.4 + (index % 4) * 0.12}
          />
        </mesh>
      ))}
    </group>
  );
}

function DataStreams() {
  const streams = useMemo(() => {
    return Array.from({ length: 12 }, (_, index) => {
      const angle = (index / 12) * Math.PI * 2;

      return {
        angle,
        radius: 3.1 + (index % 3) * 0.28,
      };
    });
  }, []);

  return (
    <>
      {streams.map((stream, index) => (
        <DataStream key={index} {...stream} index={index} />
      ))}
    </>
  );
}

function DataStream({ angle, radius, index }) {
  const ref = useRef();

  useFrame((state) => {
    if (!ref.current) return;

    const t = state.clock.elapsedTime * (0.32 + index * 0.018);

    ref.current.position.x =
      Math.cos(angle) * radius +
      Math.sin(t * 2.1) * 0.12;

    ref.current.position.y =
      Math.sin(t * 1.5) * 0.35;

    ref.current.position.z =
      Math.sin(angle) * radius +
      Math.cos(t * 1.8) * 0.12;
  });

  return (
    <mesh ref={ref}>
      <sphereGeometry args={[0.045, 12, 12]} />
      <meshBasicMaterial
        color={index % 2 ? "#8b5cf6" : "#14b8ff"}
      />
    </mesh>
  );
}

function ConnectionLines() {
  const lines = useMemo(() => {
    const result = [];

    for (let i = 0; i < 14; i++) {
      const angle = (i / 14) * Math.PI * 2;

      const start = [
        Math.cos(angle) * 1.8,
        Math.sin(angle * 1.7) * 0.4,
        Math.sin(angle) * 1.8,
      ];

      const end = [
        Math.cos(angle) * 5,
        Math.sin(angle * 2) * 0.9,
        Math.sin(angle) * 5,
      ];

      result.push({ start, end });
    }

    return result;
  }, []);

  return (
    <>
      {lines.map((line, index) => (
        <Line
          key={index}
          points={[line.start, line.end]}
          color={index % 2 ? "#8b5cf6" : "#14b8ff"}
          transparent
          opacity={0.2}
          lineWidth={0.5}
        />
      ))}
    </>
  );
}

function SceneContent() {
  return (
    <>
      <PerspectiveCamera makeDefault position={[0, 0, 12]} />

      <ambientLight intensity={0.18} />

      <pointLight
        position={[4, 5, 6]}
        intensity={22}
        distance={18}
        color="#635bff"
      />

      <pointLight
        position={[-5, -3, 4]}
        intensity={15}
        distance={15}
        color="#0ea5e9"
      />

      <CoreCube />

      <OrbitalRing
        radius={2.45}
        rotation={[0.6, 0.2, 0.3]}
        speed={0.2}
        color="#14b8ff"
      />

      <OrbitalRing
        radius={3}
        rotation={[1.2, 0.5, -0.4]}
        speed={-0.14}
        color="#8b5cf6"
      />

      <OrbitalRing
        radius={3.55}
        rotation={[0.15, 1, 0.7]}
        speed={0.1}
        color="#6366f1"
      />

      <ConnectionLines />

      <DataStreams />

      <NetworkParticles />

      <OrbitControls
        enableZoom={false}
        enablePan={false}
        autoRotate
        autoRotateSpeed={0.32}
        minPolarAngle={Math.PI / 2.8}
        maxPolarAngle={Math.PI / 1.8}
      />
    </>
  );
}

export default function BlockchainScene() {
  return (
    <div className="blockchain-scene">
      <Canvas dpr={[1, 1.6]}>
        <color attach="background" args={["#050711"]} />

        <fog
          attach="fog"
          args={["#050711", 7, 19]}
        />

        <SceneContent />
      </Canvas>
    </div>
  );
}