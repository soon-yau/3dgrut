import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";

function Cloud({
  positions,
  colors,
}: {
  positions: number[][];
  colors: number[][];
}) {
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const n = positions.length;
    const p = new Float32Array(n * 3);
    const c = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      p[i * 3] = positions[i][0];
      p[i * 3 + 1] = positions[i][1];
      p[i * 3 + 2] = positions[i][2];
      const rgb = colors[i] || [128, 128, 128];
      c[i * 3] = rgb[0] / 255;
      c[i * 3 + 1] = rgb[1] / 255;
      c[i * 3 + 2] = rgb[2] / 255;
    }
    g.setAttribute("position", new THREE.BufferAttribute(p, 3));
    g.setAttribute("color", new THREE.BufferAttribute(c, 3));
    return g;
  }, [positions, colors]);

  return (
    <points geometry={geometry}>
      <pointsMaterial vertexColors size={0.02} sizeAttenuation />
    </points>
  );
}

export function PointCloudPreview({
  positions,
  colors,
}: {
  positions: number[][] | null;
  colors: number[][] | null;
}) {
  if (!positions?.length) {
    return (
      <div style={{ height: 280, background: "#1a1d26", borderRadius: 8, padding: 12 }}>
        No point cloud yet.
      </div>
    );
  }
  return (
    <div style={{ height: 320, borderRadius: 8, overflow: "hidden", background: "#0d0f14" }}>
      <Canvas camera={{ position: [0, 0, 4], fov: 55 }}>
        <color attach="background" args={["#0d0f14"]} />
        <ambientLight intensity={0.6} />
        <Cloud positions={positions} colors={colors || positions.map(() => [200, 200, 200])} />
        <OrbitControls makeDefault />
      </Canvas>
    </div>
  );
}
