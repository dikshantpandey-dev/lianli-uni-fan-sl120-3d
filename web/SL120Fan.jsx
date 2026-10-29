// React Three Fiber component for the Lian Li UNI FAN SL120 RGB model.
// npm i three @react-three/fiber @react-three/drei
// Copy glb/LianLi_UNI_FAN_SL120.glb to your public/ folder.
import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import * as THREE from 'three';

const URL = '/LianLi_UNI_FAN_SL120.glb';

/**
 * props:
 *  rpm        rotor speed (official range 800-1900; lower values read better on screen)
 *  rgb        'rainbow' | CSS colour string | null (off)
 *  intensity  emissive strength (pair with a Bloom pass for the glow)
 *  screws     show the 4 bundled black fan screws
 * The model is in metres (0.12 m wide). Scale the group for other unit systems.
 */
export function SL120Fan({ rpm = 400, rgb = 'rainbow', intensity = 3, screws = true, ...props }) {
  const { scene } = useGLTF(URL);
  const fan = useMemo(() => scene.clone(true), [scene]);
  const rotor = useMemo(() => fan.getObjectByName('Rotor'), [fan]);
  const rgbMats = useMemo(() => {
    const mats = [];
    fan.traverse((o) => {
      if (o.isMesh && o.material.name === 'MAT_RGB_Diffuser_PC') {
        o.material = o.material.clone();            // per-instance colour control
        o.material.emissiveMap = o.material.emissiveMap.clone();
        o.material.emissiveMap.wrapS = THREE.RepeatWrapping;
        o.material.userData.rainbow = o.material.emissiveMap;
        mats.push(o.material);
      }
    });
    return mats;
  }, [fan]);

  useEffect(() => {
    const s = fan.getObjectByName('Screws');
    if (s) s.visible = screws;
  }, [fan, screws]);

  useEffect(() => {
    for (const m of rgbMats) {
      m.emissiveIntensity = rgb ? intensity : 0;
      if (rgb === 'rainbow') { m.emissiveMap = m.userData.rainbow; m.emissive.set('#ffffff'); }
      else if (rgb) { m.emissiveMap = null; m.emissive.set(rgb); }
      m.needsUpdate = true;
    }
  }, [rgbMats, rgb, intensity]);

  useFrame((_, dt) => {
    if (rotor) rotor.rotation.z += (rpm / 60) * Math.PI * 2 * dt;   // counter-clockwise seen from the front
    if (rgb === 'rainbow') for (const m of rgbMats) m.emissiveMap.offset.x -= dt * 0.25;
  });

  return <primitive object={fan} {...props} />;
}

useGLTF.preload(URL);

// Usage:
// <Canvas camera={{ position: [-0.17, 0.09, 0.27], fov: 30, near: 0.01 }}>
//   <Environment preset="studio" />
//   <SL120Fan rpm={500} rgb="rainbow" />
//   <OrbitControls autoRotate />
//   <EffectComposer><Bloom intensity={0.6} luminanceThreshold={0.8} /></EffectComposer>
// </Canvas>
