import { useEffect, useRef, memo } from 'react';
import * as THREE from 'three';

interface IOSShellProps {
  children: React.ReactNode;
}

// Mobile detection helper
const isMobileDevice = (): boolean => {
  if (typeof window === 'undefined') return false;

  const ua = navigator.userAgent || navigator.vendor;
  const mobileRegex = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i;

  const hasTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  const smallScreen = window.innerWidth < 768;

  return mobileRegex.test(ua) || (hasTouch && smallScreen);
};

// Get particle count with safe env access
const getParticleCount = (): number => {
  const env = import.meta.env;
  const envCount = env?.VITE_THREE_PARTICLES_COUNT;

  if (envCount && !isNaN(Number(envCount))) {
    return Number(envCount);
  }

  return isMobileDevice() ? 500 : 1500;
};

// Check if device supports WebGL properly
const supportsWebGL = (): boolean => {
  try {
    const canvas = document.createElement('canvas');
    return !!(window.WebGLRenderingContext &&
      (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
  } catch {
    return false;
  }
};

export const IOSShell: React.FC<IOSShellProps> = memo(({ children }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    if (!supportsWebGL()) {
      console.warn('🎨 WebGL not supported - skipping Three.js background');
      return;
    }

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      75,
      window.innerWidth / window.innerHeight,
      1,
      2000
    );

    const renderer = new THREE.WebGLRenderer({
      antialias: false,
      alpha: true,
      powerPreference: isMobileDevice() ? 'low-power' : 'high-performance'
    });

    rendererRef.current = renderer;
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const particleCount = getParticleCount();
    const geo = new THREE.BufferGeometry();
    const pos = [];

    for (let i = 0; i < particleCount; i++) {
      pos.push(
        THREE.MathUtils.randFloatSpread(2000),
        THREE.MathUtils.randFloatSpread(2000),
        THREE.MathUtils.randFloatSpread(2000)
      );
    }
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));

    const mat = new THREE.PointsMaterial({
      color: 0xb8956a,
      size: isMobileDevice() ? 1.0 : 1.5,
      transparent: true,
      opacity: 0.35,
      sizeAttenuation: true,
    });

    const cloud = new THREE.Points(geo, mat);
    scene.add(cloud);
    camera.position.z = 800;

    const isMobile = isMobileDevice();
    const animationSpeed = isMobile ? 0.00015 : 0.0003;
    const animationSpeedX = isMobile ? 0.00005 : 0.0001;

    let animationFrameId: number;
    const anim = () => {
      animationFrameId = requestAnimationFrame(anim);
      cloud.rotation.y += animationSpeed;
      cloud.rotation.x += animationSpeedX;
      renderer.render(scene, camera);
    };
    anim();

    const handleResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    };

    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', handleResize);

      if (container && renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }

      renderer.dispose();
      geo.dispose();
      mat.dispose();
    };
  }, []);

  return (
    // Используем h-screen для полной высоты и w-full для ширины (без vw, чтобы избежать проблем)
    <div className="relative h-screen w-full overflow-hidden font-mono">
      <div ref={containerRef} id="three-container" className="absolute inset-0 z-0" />
      <div className="relative z-10 h-full flex flex-col">{children}</div>
    </div>
  );
});

IOSShell.displayName = 'IOSShell';
