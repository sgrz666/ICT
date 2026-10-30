import { memo, useEffect, useRef, useState } from "react";

import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";

import {
  CART_LENGTH,
  MomentumSim,
  type ImpactRecord,
  type LabConfig,
  type SimSample,
} from "./momentumPhysics";

const TRACK_VISUAL_LENGTH = 13.2;
const TRACK_Y = 1.2;
const CART_Y = 1.37;
const ACCENT = 0xd8ff63;
const WARM = 0xffb26b;
const COOL = 0x6fe3c0;

interface MomentumStageProps {
  config: LabConfig;
  running: boolean;
  resetToken: number;
  onSample: (sample: SimSample) => void;
  onImpact: (record: ImpactRecord) => void;
  onEnded: () => void;
}

interface VectorArrow {
  group: THREE.Group;
  shaft: THREE.Mesh<THREE.CylinderGeometry, THREE.MeshBasicMaterial>;
  head: THREE.Mesh<THREE.ConeGeometry, THREE.MeshBasicMaterial>;
}

interface CartRig {
  group: THREE.Group;
  body: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>;
  weights: THREE.Group;
  label: CSS2DObject;
  massEl: HTMLElement;
  velocityEl: HTMLElement;
  arrow: VectorArrow;
  accent: number;
}

export const MomentumStage = memo(function MomentumStageInner(props: MomentumStageProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const propsRef = useRef(props);
  propsRef.current = props;

  const configRef = useRef(props.config);
  const runningRef = useRef(props.running);
  const simRef = useRef<MomentumSim | null>(null);
  const resetRef = useRef<(() => void) | null>(null);
  const cameraResetRef = useRef<(() => void) | null>(null);
  const [webglError, setWebglError] = useState<string | null>(null);

  useEffect(() => {
    configRef.current = props.config;
  }, [props.config]);

  useEffect(() => {
    resetRef.current?.();
  }, [props.resetToken]);

  useEffect(() => {
    runningRef.current = props.running;
    const sim = simRef.current;
    if (!sim) return;
    if (props.running) sim.play();
    else if (sim.status === "running") sim.pause();
  }, [props.running]);

  useEffect(() => {
    const host = containerRef.current;
    if (!host) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: false,
        powerPreference: "high-performance",
      });
    } catch (error) {
      setWebglError(
        error instanceof Error ? error.message : "当前浏览器无法初始化 WebGL 渲染上下文。"
      );
      return;
    }

    const width = Math.max(host.clientWidth, 320);
    const height = Math.max(host.clientHeight, 320);

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height, false);
    renderer.setClearColor(0x070a08, 1);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.domElement.className = "momentum-webgl";
    renderer.domElement.setAttribute("aria-hidden", "true");
    host.appendChild(renderer.domElement);

    const labelRenderer = new CSS2DRenderer();
    labelRenderer.setSize(width, height);
    labelRenderer.domElement.className = "momentum-label-layer";
    host.appendChild(labelRenderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x070a08);
    scene.fog = new THREE.FogExp2(0x070a08, 0.021);

    const initialAspect = width / height;
    const compactStage = initialAspect < 1.2;
    const camera = new THREE.PerspectiveCamera(compactStage ? 45 : 44, initialAspect, 0.1, 90);
    const homePosition = compactStage
      ? new THREE.Vector3(7, 5.3, 14.8)
      : new THREE.Vector3(6.6, 4.9, 12);
    const homeTarget = new THREE.Vector3(0, 1.35, 0);
    camera.position.copy(homePosition);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(homeTarget);
    controls.enableDamping = true;
    controls.dampingFactor = 0.065;
    controls.minDistance = 5.5;
    controls.maxDistance = 26;
    controls.minPolarAngle = 0.32;
    controls.maxPolarAngle = Math.PI / 2 - 0.035;
    controls.enablePan = true;
    controls.panSpeed = 0.55;
    controls.rotateSpeed = 0.65;
    controls.zoomSpeed = 0.7;
    controls.update();

    const pmrem = new THREE.PMREMGenerator(renderer);
    const roomEnvironment = new RoomEnvironment();
    const environmentTarget = pmrem.fromScene(roomEnvironment, 0.04);
    scene.environment = environmentTarget.texture;
    roomEnvironment.dispose();

    const disposables: Array<{ dispose: () => void }> = [environmentTarget];
    const disposeMaterial = (material: THREE.Material) => {
      const candidate = material as THREE.MeshStandardMaterial;
      candidate.map?.dispose();
      candidate.alphaMap?.dispose();
      candidate.emissiveMap?.dispose();
      material.dispose();
    };

    // ---------------------------------------------------------------------
    // 灯光与空间
    // ---------------------------------------------------------------------
    scene.add(new THREE.HemisphereLight(0xd8ffe3, 0x11150f, 0.7));

    const keyLight = new THREE.DirectionalLight(0xf4ffdf, 3.1);
    keyLight.position.set(-4.5, 9.5, 7);
    keyLight.castShadow = true;
    keyLight.shadow.mapSize.set(2048, 2048);
    keyLight.shadow.camera.left = -10;
    keyLight.shadow.camera.right = 10;
    keyLight.shadow.camera.top = 8;
    keyLight.shadow.camera.bottom = -5;
    keyLight.shadow.camera.near = 0.5;
    keyLight.shadow.camera.far = 30;
    keyLight.shadow.bias = -0.0008;
    scene.add(keyLight);

    const warmLight = new THREE.SpotLight(0xffd4a6, 100, 26, 0.7, 0.9, 1.2);
    warmLight.position.set(-7, 6.5, 5);
    warmLight.target.position.set(-2, 1.2, 0);
    scene.add(warmLight, warmLight.target);

    const coolLight = new THREE.PointLight(0x72e5bf, 24, 16, 1.6);
    coolLight.position.set(5.5, 3.4, -2.8);
    scene.add(coolLight);

    // 远处的圆形背光让纵深成立，也给顶部留白一个视觉落点。
    const haloTexture = makeHaloTexture();
    disposables.push(haloTexture);
    const halo = new THREE.Mesh(
      new THREE.PlaneGeometry(14, 14),
      new THREE.MeshBasicMaterial({
        map: haloTexture,
        transparent: true,
        opacity: 0.72,
        depthWrite: false,
        side: THREE.DoubleSide,
      })
    );
    halo.position.set(0, 3.15, -6.6);
    scene.add(halo);

    const floorMaterial = new THREE.MeshStandardMaterial({
      color: 0x0c110d,
      roughness: 0.88,
      metalness: 0.18,
    });
    const floor = new THREE.Mesh(new THREE.CircleGeometry(21, 96), floorMaterial);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.02;
    floor.receiveShadow = true;
    scene.add(floor);

    const grid = new THREE.GridHelper(42, 42, 0x3a493d, 0x1c261f);
    grid.position.y = 0.005;
    const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material];
    for (const material of gridMaterials) {
      material.transparent = true;
      material.opacity = 0.22;
      material.depthWrite = false;
    }
    scene.add(grid);

    const ringMaterial = new THREE.MeshBasicMaterial({
      color: ACCENT,
      transparent: true,
      opacity: 0.24,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const stageRing = new THREE.Mesh(new THREE.RingGeometry(8.7, 8.73, 160), ringMaterial);
    stageRing.rotation.x = -Math.PI / 2;
    stageRing.position.y = 0.012;
    scene.add(stageRing);

    const outerRing = new THREE.Mesh(
      new THREE.RingGeometry(13.8, 13.82, 180),
      new THREE.MeshBasicMaterial({
        color: 0x78907f,
        transparent: true,
        opacity: 0.18,
        depthWrite: false,
        side: THREE.DoubleSide,
      })
    );
    outerRing.rotation.x = -Math.PI / 2;
    outerRing.position.y = 0.01;
    scene.add(outerRing);

    const radialTicks: number[] = [];
    for (let i = 0; i < 72; i += 1) {
      const angle = (i / 72) * Math.PI * 2;
      const inner = i % 6 === 0 ? 8.8 : 8.95;
      radialTicks.push(
        Math.cos(angle) * inner,
        0.014,
        Math.sin(angle) * inner,
        Math.cos(angle) * 9.1,
        0.014,
        Math.sin(angle) * 9.1
      );
    }
    const tickGeometry = new THREE.BufferGeometry();
    tickGeometry.setAttribute("position", new THREE.Float32BufferAttribute(radialTicks, 3));
    const tickLines = new THREE.LineSegments(
      tickGeometry,
      new THREE.LineBasicMaterial({ color: 0x748578, transparent: true, opacity: 0.26 })
    );
    scene.add(tickLines);

    const wall = new THREE.Mesh(
      new THREE.CylinderGeometry(20, 20, 18, 72, 1, true),
      new THREE.MeshStandardMaterial({
        color: 0x080c09,
        roughness: 1,
        metalness: 0,
        side: THREE.BackSide,
      })
    );
    wall.position.y = 8.8;
    scene.add(wall);

    // 悬浮微尘：让空间有尺度，但保持低对比，不抢实验主体。
    const dustPositions = new Float32Array(210 * 3);
    for (let i = 0; i < 210; i += 1) {
      dustPositions[i * 3] = (Math.random() - 0.5) * 18;
      dustPositions[i * 3 + 1] = 0.35 + Math.random() * 6;
      dustPositions[i * 3 + 2] = (Math.random() - 0.5) * 12;
    }
    const dustGeometry = new THREE.BufferGeometry();
    dustGeometry.setAttribute("position", new THREE.BufferAttribute(dustPositions, 3));
    const dust = new THREE.Points(
      dustGeometry,
      new THREE.PointsMaterial({
        color: 0xc9e6d1,
        size: 0.022,
        transparent: true,
        opacity: 0.32,
        depthWrite: false,
        sizeAttenuation: true,
      })
    );
    scene.add(dust);

    // 顶部灯带与吊架
    const rigMaterial = new THREE.MeshStandardMaterial({
      color: 0x202721,
      metalness: 0.8,
      roughness: 0.35,
    });
    for (const x of [-4.4, 0, 4.4]) {
      const cable = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 1.8, 6), rigMaterial);
      cable.position.set(x, 6.2, -0.9);
      scene.add(cable);
      const lamp = new THREE.Mesh(
        new THREE.BoxGeometry(2.25, 0.055, 0.11),
        new THREE.MeshBasicMaterial({ color: 0xe7ffd9 })
      );
      lamp.position.set(x, 5.28, -0.9);
      scene.add(lamp);
      const glow = new THREE.Mesh(
        new THREE.BoxGeometry(2.5, 0.02, 0.26),
        new THREE.MeshBasicMaterial({
          color: 0xb9e6a8,
          transparent: true,
          opacity: 0.14,
          depthWrite: false,
        })
      );
      glow.position.set(x, 5.24, -0.9);
      scene.add(glow);
    }

    for (const x of [-8.7, 8.7]) {
      const post = new THREE.Mesh(
        new THREE.CylinderGeometry(0.045, 0.055, 6.4, 8),
        rigMaterial
      );
      post.position.set(x, 3.2, -4.4);
      scene.add(post);
    }

    // ---------------------------------------------------------------------
    // 气垫导轨
    // ---------------------------------------------------------------------
    const track = new THREE.Group();
    scene.add(track);

    const beamMaterial = new THREE.MeshStandardMaterial({
      color: 0x39443b,
      metalness: 0.76,
      roughness: 0.27,
    });
    const beam = new THREE.Mesh(
      new THREE.BoxGeometry(TRACK_VISUAL_LENGTH, 0.26, 0.94),
      beamMaterial
    );
    beam.position.y = TRACK_Y;
    beam.castShadow = true;
    beam.receiveShadow = true;
    track.add(beam);

    const topSurface = new THREE.Mesh(
      new THREE.BoxGeometry(TRACK_VISUAL_LENGTH - 0.08, 0.035, 0.8),
      new THREE.MeshStandardMaterial({ color: 0x111a14, metalness: 0.55, roughness: 0.4 })
    );
    topSurface.position.y = 1.348;
    topSurface.receiveShadow = true;
    track.add(topSurface);

    const railEdgeMaterial = new THREE.MeshStandardMaterial({
      color: 0x6f7f72,
      metalness: 0.92,
      roughness: 0.2,
    });
    for (const z of [-0.47, 0.47]) {
      const rail = new THREE.Mesh(
        new THREE.BoxGeometry(TRACK_VISUAL_LENGTH, 0.035, 0.012),
        railEdgeMaterial
      );
      rail.position.set(0, 1.323, z);
      track.add(rail);
    }

    const led = new THREE.Mesh(
      new THREE.BoxGeometry(TRACK_VISUAL_LENGTH - 0.4, 0.012, 0.008),
      new THREE.MeshBasicMaterial({ color: 0x8ee8b4, transparent: true, opacity: 0.7 })
    );
    led.position.set(0, 1.232, 0.472);
    track.add(led);

    const supports = [-5.75, -2.9, 0, 2.9, 5.75];
    for (const x of supports) {
      const leg = new THREE.Mesh(new THREE.BoxGeometry(0.16, 1.08, 0.46), beamMaterial);
      leg.position.set(x, 0.54, 0);
      leg.castShadow = true;
      track.add(leg);
      const foot = new THREE.Mesh(
        new THREE.BoxGeometry(0.54, 0.05, 0.72),
        new THREE.MeshStandardMaterial({ color: 0x151b16, metalness: 0.6, roughness: 0.5 })
      );
      foot.position.set(x, 0.025, 0);
      foot.receiveShadow = true;
      track.add(foot);
    }

    const endMaterial = new THREE.MeshStandardMaterial({
      color: 0x1a221b,
      metalness: 0.7,
      roughness: 0.4,
    });
    for (const x of [-6.64, 6.64]) {
      const end = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.36, 1.04), endMaterial);
      end.position.set(x, 1.22, 0);
      end.castShadow = true;
      track.add(end);
      const reflector = new THREE.Mesh(
        new THREE.BoxGeometry(0.01, 0.07, 0.18),
        new THREE.MeshBasicMaterial({ color: WARM })
      );
      reflector.position.set(x > 0 ? x - 0.071 : x + 0.071, 1.28, 0.24);
      track.add(reflector);
    }

    // 气孔
    const holeRows = [-0.22, 0.22];
    const holeCount = 51 * holeRows.length;
    const holes = new THREE.InstancedMesh(
      new THREE.CylinderGeometry(0.015, 0.015, 0.006, 10),
      new THREE.MeshBasicMaterial({ color: 0x020403 }),
      holeCount
    );
    const dummy = new THREE.Object3D();
    let holeIndex = 0;
    for (let i = 0; i < 51; i += 1) {
      const x = -6.2 + i * 0.248;
      for (const z of holeRows) {
        dummy.position.set(x, 1.367, z);
        dummy.updateMatrix();
        holes.setMatrixAt(holeIndex, dummy.matrix);
        holeIndex += 1;
      }
    }
    holes.instanceMatrix.needsUpdate = true;
    track.add(holes);

    // 导轨侧面的刻度带，直接画进 canvas，避免大量 DOM 标签。
    const rulerTexture = makeRulerTexture();
    disposables.push(rulerTexture);
    const ruler = new THREE.Mesh(
      new THREE.PlaneGeometry(13.02, 0.22),
      new THREE.MeshBasicMaterial({
        map: rulerTexture,
        transparent: true,
        depthWrite: false,
      })
    );
    ruler.position.set(0, 1.2, 0.478);
    track.add(ruler);

    // 地面编号，作为空间定位锚点。
    const floorDecalTexture = makeFloorDecalTexture();
    disposables.push(floorDecalTexture);
    const floorDecal = new THREE.Mesh(
      new THREE.PlaneGeometry(4.4, 1.65),
      new THREE.MeshBasicMaterial({
        map: floorDecalTexture,
        transparent: true,
        opacity: 0.72,
        depthWrite: false,
      })
    );
    floorDecal.rotation.x = -Math.PI / 2;
    floorDecal.position.set(0, 0.016, 3.35);
    scene.add(floorDecal);

    // ---------------------------------------------------------------------
    // 两辆实验车
    // ---------------------------------------------------------------------
    const cartA = createCart("01", WARM, "a");
    const cartB = createCart("02", COOL, "b");
    cartA.group.position.set(-2.6, CART_Y, 0);
    cartB.group.position.set(0.4, CART_Y, 0);
    scene.add(cartA.group, cartB.group);

    // 反冲弹簧：只在弹簧反冲场景、未释放时显示。
    const spring = createSpring();
    spring.position.set(0, CART_Y + 0.24, 0);
    scene.add(spring);

    const pulse = new THREE.Mesh(
      new THREE.RingGeometry(0.24, 0.27, 72),
      new THREE.MeshBasicMaterial({
        color: ACCENT,
        transparent: true,
        opacity: 0,
        side: THREE.DoubleSide,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      })
    );
    pulse.position.set(0, CART_Y + 0.34, 0.94);
    scene.add(pulse);

    const pulseLight = new THREE.PointLight(ACCENT, 0, 6, 2);
    pulseLight.position.set(0, CART_Y + 0.55, 0.4);
    scene.add(pulseLight);

    const sim = new MomentumSim(configRef.current);
    simRef.current = sim;

    let pulseEnergy = 0;
    let lastSampleAt = 0;
    let completed = false;
    let cameraGoal: { position: THREE.Vector3; target: THREE.Vector3 } | null = null;

    const syncConfigVisuals = () => {
      const config = configRef.current;
      sim.reset(config);
      cartA.group.position.x = sim.x1;
      cartB.group.position.x = sim.x2;
      cartA.group.position.y = CART_Y;
      cartB.group.position.y = CART_Y;
      setCartMass(cartA, config.m1);
      setCartMass(cartB, config.m2);
      updateCartReadout(cartA, config.m1, sim.v1);
      updateCartReadout(cartB, config.m2, sim.v2);
      spring.visible = config.sceneId === "explosion";
      pulseEnergy = 0;
      pulse.material.opacity = 0;
      pulseLight.intensity = 0;
      completed = false;
      lastSampleAt = 0;
      if (config.sceneId === "explosion") {
        spring.position.x = (sim.x1 + sim.x2) / 2;
        spring.scale.x = Math.max(0.05, sim.x2 - sim.x1 - CART_LENGTH);
      }
      propsRef.current.onSample(sim.sample());
    };

    resetRef.current = syncConfigVisuals;
    syncConfigVisuals();

    const resetCamera = () => {
      cameraGoal = {
        position: homePosition.clone(),
        target: homeTarget.clone(),
      };
    };
    cameraResetRef.current = resetCamera;

    const handleDoubleClick = (event: MouseEvent) => {
      event.preventDefault();
      resetCamera();
    };
    renderer.domElement.addEventListener("dblclick", handleDoubleClick);

    const resize = () => {
      const nextWidth = Math.max(host.clientWidth, 320);
      const nextHeight = Math.max(host.clientHeight, 280);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(nextWidth, nextHeight, false);
      labelRenderer.setSize(nextWidth, nextHeight);
      camera.aspect = nextWidth / nextHeight;
      camera.updateProjectionMatrix();
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);
    resize();

    let lastFrameAt = performance.now();
    let lastSampledStatus = sim.status;
    let frameId = 0;

    const animate = () => {
      frameId = requestAnimationFrame(animate);
      const now = performance.now();
      const dt = Math.min((now - lastFrameAt) / 1000, 0.05);
      lastFrameAt = now;
      const config = configRef.current;

      if (runningRef.current) {
        sim.step(dt * config.timeScale);
        for (const event of sim.consumeEvents()) {
          if (event.type === "impact") {
            pulseEnergy = 1;
            pulse.position.x = event.record.x;
            pulseLight.position.x = event.record.x;
            if (event.record.kind === "explosion") {
              spring.visible = false;
            }
            propsRef.current.onImpact(event.record);
          } else if (event.type === "end") {
            if (!completed) {
              completed = true;
              runningRef.current = false;
              propsRef.current.onEnded();
            }
          }
        }
      }

      // 3D 位置与数据标签
      cartA.group.position.x = sim.x1;
      cartB.group.position.x = sim.x2;
      updateCartArrow(cartA, sim.v1);
      updateCartArrow(cartB, sim.v2);
      updateCartReadout(cartA, config.m1, sim.v1);
      updateCartReadout(cartB, config.m2, sim.v2);
      spring.visible =
        config.sceneId === "explosion" && !sim.exploded && sim.collisions === 0;

      if (pulseEnergy > 0) {
        pulseEnergy = Math.max(0, pulseEnergy - dt * 2.35);
        const progress = 1 - pulseEnergy;
        pulse.scale.setScalar(1 + progress * 4.6);
        pulse.material.opacity = pulseEnergy * 0.85;
        pulseLight.intensity = pulseEnergy * 12;
      } else {
        pulse.material.opacity = 0;
        pulseLight.intensity = 0;
      }

      dust.rotation.y += dt * 0.008;
      controls.update();

      if (cameraGoal) {
        camera.position.lerp(cameraGoal.position, 0.09);
        controls.target.lerp(cameraGoal.target, 0.09);
        if (
          camera.position.distanceTo(cameraGoal.position) < 0.03 &&
          controls.target.distanceTo(cameraGoal.target) < 0.02
        ) {
          camera.position.copy(cameraGoal.position);
          controls.target.copy(cameraGoal.target);
          cameraGoal = null;
        }
      }

      if (
        (runningRef.current || sim.status !== lastSampledStatus) &&
        now - lastSampleAt > 72
      ) {
        lastSampleAt = now;
        lastSampledStatus = sim.status;
        propsRef.current.onSample(sim.sample());
      }

      renderer.render(scene, camera);
      labelRenderer.render(scene, camera);
    };

    animate();

    return () => {
      cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("dblclick", handleDoubleClick);
      controls.dispose();
      scene.traverse(object => {
        const mesh = object as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
        if (mesh.material) {
          const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
          for (const material of materials) disposeMaterial(material);
        }
      });
      for (const item of disposables) item.dispose();
      pmrem.dispose();
      labelRenderer.domElement.remove();
      renderer.domElement.remove();
      renderer.dispose();
      simRef.current = null;
      resetRef.current = null;
      cameraResetRef.current = null;
    };
  }, []);

  return (
    <div className="momentum-stage" role="region" aria-label="3D 动量守恒实验场景">
      <div className="momentum-canvas-host" ref={containerRef} />
      {webglError ? (
        <div className="momentum-stage-error" role="alert">
          <span className="stage-kicker">WEBGL OFFLINE</span>
          <strong>3D 实验台未能启动</strong>
          <p>{webglError}</p>
          <p>请在支持 WebGL 2 的浏览器中打开，或检查显卡加速是否被禁用。</p>
        </div>
      ) : null}

      <div className="stage-overlay" aria-hidden="true">
        <div className="stage-corner stage-corner--tl" />
        <div className="stage-corner stage-corner--br" />
        <div className="stage-id">
          <span>EXPERIMENT</span>
          <strong>04</strong>
          <em>AIR TRACK / 1D</em>
        </div>
        <div className="stage-live">
          <span className="stage-live__dot" />
          <span>LIVE 3D</span>
          <em>WEBGL</em>
        </div>
        <div className="stage-scale">
          <span>SCALE</span>
          <div className="stage-scale__rule">
            <i />
            <i />
            <i />
            <i />
            <i />
          </div>
          <strong>1 m</strong>
        </div>
        <div className="stage-hint">拖拽旋转 · 滚轮缩放 · 双击复位</div>
      </div>

      <button
        type="button"
        className="stage-camera-button"
        onClick={() => cameraResetRef.current?.()}
        title="复位 3D 视角"
      >
        <CameraIcon />
        <span>复位视角</span>
      </button>
    </div>
  );
});

function createCart(number: string, accent: number, variant: "a" | "b"): CartRig {
  const group = new THREE.Group();
  group.name = `cart-${number}`;

  const baseMaterial = new THREE.MeshStandardMaterial({
    color: 0x111713,
    metalness: 0.72,
    roughness: 0.35,
  });
  const base = new THREE.Mesh(
    new RoundedBoxGeometry(0.98, 0.1, 0.72, 3, 0.035),
    baseMaterial
  );
  base.position.y = 0.05;
  base.castShadow = true;
  group.add(base);

  const bodyMaterial = new THREE.MeshStandardMaterial({
    color: accent,
    metalness: 0.42,
    roughness: 0.29,
    emissive: new THREE.Color(accent),
    emissiveIntensity: 0.09,
  });
  const body = new THREE.Mesh(
    new RoundedBoxGeometry(0.9, 0.24, 0.64, 4, 0.055),
    bodyMaterial
  );
  body.position.y = 0.22;
  body.castShadow = true;
  body.receiveShadow = true;
  group.add(body);

  const topPlate = new THREE.Mesh(
    new RoundedBoxGeometry(0.78, 0.03, 0.52, 2, 0.018),
    new THREE.MeshStandardMaterial({ color: 0x121814, metalness: 0.7, roughness: 0.4 })
  );
  topPlate.position.y = 0.355;
  group.add(topPlate);

  const weights = new THREE.Group();
  weights.position.y = 0.373;
  group.add(weights);

  for (const side of [-1, 1]) {
    const bumper = new THREE.Mesh(
      new THREE.BoxGeometry(0.035, 0.13, 0.35),
      new THREE.MeshStandardMaterial({ color: 0x2a302b, metalness: 0.75, roughness: 0.35 })
    );
    bumper.position.set(side * 0.49, 0.16, 0);
    bumper.castShadow = true;
    group.add(bumper);
  }

  const led = new THREE.Mesh(
    new THREE.BoxGeometry(0.3, 0.014, 0.008),
    new THREE.MeshBasicMaterial({ color: accent })
  );
  led.position.set(0, 0.195, 0.328);
  group.add(led);

  const labelElement = document.createElement("div");
  labelElement.className = `momentum-cart-label momentum-cart-label--${variant}`;

  const id = document.createElement("span");
  id.className = "momentum-cart-label__id";
  id.textContent = `CART ${number}`;
  const mass = document.createElement("strong");
  mass.className = "momentum-cart-label__mass";
  const velocity = document.createElement("span");
  velocity.className = "momentum-cart-label__velocity";
  labelElement.append(id, mass, velocity);

  const label = new CSS2DObject(labelElement);
  label.position.set(0, 0.92, 0);
  group.add(label);

  const arrow = createVectorArrow(accent);
  arrow.group.position.set(0, 0.82, 0.38);
  group.add(arrow.group);

  return {
    group,
    body,
    weights,
    label,
    massEl: mass,
    velocityEl: velocity,
    arrow,
    accent,
  };
}

function setCartMass(rig: CartRig, mass: number): void {
  while (rig.weights.children.length > 0) {
    const child = rig.weights.children[0] as THREE.Mesh;
    rig.weights.remove(child);
    child.geometry.dispose();
    const material = child.material;
    if (Array.isArray(material)) material.forEach(item => item.dispose());
    else material.dispose();
  }

  const count = Math.max(1, Math.min(7, Math.round(mass * 1.15)));
  for (let i = 0; i < count; i += 1) {
    const plate = new THREE.Mesh(
      new RoundedBoxGeometry(0.58 - i * 0.025, 0.028, 0.42 - i * 0.015, 2, 0.008),
      new THREE.MeshStandardMaterial({
        color: i % 2 === 0 ? 0x4a514b : 0x363c37,
        metalness: 0.78,
        roughness: 0.34,
      })
    );
    plate.position.y = i * 0.031;
    plate.castShadow = true;
    rig.weights.add(plate);
  }
  rig.massEl.textContent = `${mass.toFixed(1)} kg`;
}

function updateCartReadout(rig: CartRig, mass: number, velocity: number): void {
  const massText = `${mass.toFixed(1)} kg`;
  if (rig.massEl.textContent !== massText) rig.massEl.textContent = massText;
  const sign = velocity > 0.004 ? "+" : "";
  const velocityText = `${sign}${velocity.toFixed(2)} m/s`;
  if (rig.velocityEl.textContent !== velocityText) {
    rig.velocityEl.textContent = velocityText;
  }
  const direction = velocity > 0.004 ? "right" : velocity < -0.004 ? "left" : "still";
  if (rig.velocityEl.dataset.direction !== direction) {
    rig.velocityEl.dataset.direction = direction;
  }
}

function createVectorArrow(accent: number): VectorArrow {
  const group = new THREE.Group();
  const material = new THREE.MeshBasicMaterial({
    color: accent,
    transparent: true,
    opacity: 0.92,
  });
  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, 1, 8), material);
  shaft.rotation.z = -Math.PI / 2;
  group.add(shaft);
  const head = new THREE.Mesh(new THREE.ConeGeometry(0.085, 0.2, 12), material);
  head.rotation.z = -Math.PI / 2;
  group.add(head);
  return { group, shaft, head };
}

function updateCartArrow(rig: CartRig, velocity: number): void {
  const magnitude = Math.abs(velocity);
  const visible = magnitude > 0.025;
  rig.arrow.group.visible = visible;
  if (!visible) return;
  const length = 0.56 + Math.min(magnitude, 4) * 0.38;
  const shaftLength = Math.max(0.12, length - 0.18);
  rig.arrow.shaft.scale.y = shaftLength;
  rig.arrow.shaft.position.x = shaftLength / 2;
  rig.arrow.head.position.x = shaftLength + 0.09;
  rig.arrow.group.rotation.y = velocity > 0 ? 0 : Math.PI;
}

function createSpring(): THREE.Group {
  const group = new THREE.Group();
  const points: THREE.Vector3[] = [];
  const coils = 7;
  const samples = 160;
  for (let i = 0; i < samples; i += 1) {
    const p = i / (samples - 1);
    const angle = p * coils * Math.PI * 2;
    points.push(
      new THREE.Vector3(
        p - 0.5,
        Math.sin(angle) * 0.095,
        Math.cos(angle) * 0.095
      )
    );
  }
  const curve = new THREE.CatmullRomCurve3(points);
  const geometry = new THREE.TubeGeometry(curve, 200, 0.012, 7, false);
  const material = new THREE.MeshStandardMaterial({
    color: 0xbccf74,
    metalness: 0.8,
    roughness: 0.25,
    emissive: 0x5f6e2b,
    emissiveIntensity: 0.2,
  });
  group.add(new THREE.Mesh(geometry, material));
  return group;
}

function makeRulerTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 2048;
  canvas.height = 160;
  const context = canvas.getContext("2d");
  if (!context) return new THREE.CanvasTexture(canvas);

  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "rgba(8, 13, 10, 0.94)";
  context.fillRect(0, 0, canvas.width, canvas.height);

  const left = 24;
  const right = canvas.width - 24;
  const usable = right - left;
  const baseline = 30;
  context.strokeStyle = "rgba(207, 224, 205, 0.62)";
  context.lineWidth = 2;
  context.beginPath();
  context.moveTo(left, baseline);
  context.lineTo(right, baseline);
  context.stroke();

  for (let i = 0; i <= 24; i += 1) {
    const x = left + (i / 24) * usable;
    const major = i % 2 === 0;
    const zero = i === 12;
    context.strokeStyle = zero
      ? "rgba(216, 255, 99, 0.95)"
      : major
        ? "rgba(207, 224, 205, 0.65)"
        : "rgba(207, 224, 205, 0.28)";
    context.lineWidth = zero ? 4 : major ? 2 : 1;
    context.beginPath();
    context.moveTo(x, baseline);
    context.lineTo(x, baseline + (zero ? 38 : major ? 26 : 14));
    context.stroke();

    if (major && (i % 4 === 0 || zero)) {
      const meter = i / 2 - 6;
      context.fillStyle = zero ? "#d8ff63" : "rgba(210, 224, 208, 0.56)";
      context.font = '700 29px "Cascadia Mono", Consolas, monospace';
      context.textAlign = "center";
      context.textBaseline = "top";
      context.fillText(
        `${meter > 0 ? "+" : ""}${meter.toFixed(0)}`,
        x,
        baseline + 52
      );
    }
  }

  context.fillStyle = "rgba(207, 224, 205, 0.34)";
  context.font = '600 20px "Cascadia Mono", Consolas, monospace';
  context.textAlign = "right";
  context.fillText("X / METER", right, 104);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  texture.needsUpdate = true;
  return texture;
}

function makeHaloTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 1024;
  const context = canvas.getContext("2d");
  if (!context) return new THREE.CanvasTexture(canvas);

  context.clearRect(0, 0, 1024, 1024);
  const glow = context.createRadialGradient(512, 512, 30, 512, 512, 510);
  glow.addColorStop(0, "rgba(78, 123, 88, 0.42)");
  glow.addColorStop(0.38, "rgba(45, 75, 53, 0.26)");
  glow.addColorStop(0.72, "rgba(20, 34, 24, 0.12)");
  glow.addColorStop(1, "rgba(6, 10, 7, 0)");
  context.fillStyle = glow;
  context.beginPath();
  context.arc(512, 512, 510, 0, Math.PI * 2);
  context.fill();

  context.strokeStyle = "rgba(216, 255, 99, 0.16)";
  context.lineWidth = 2;
  context.beginPath();
  context.arc(512, 512, 410, 0, Math.PI * 2);
  context.stroke();

  context.strokeStyle = "rgba(216, 255, 99, 0.08)";
  context.setLineDash([3, 12]);
  context.beginPath();
  context.arc(512, 512, 330, 0, Math.PI * 2);
  context.stroke();
  context.setLineDash([]);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function makeFloorDecalTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 1200;
  canvas.height = 450;
  const context = canvas.getContext("2d");
  if (!context) return new THREE.CanvasTexture(canvas);

  context.clearRect(0, 0, canvas.width, canvas.height);
  context.strokeStyle = "rgba(216, 255, 99, 0.24)";
  context.lineWidth = 2;
  context.strokeRect(30, 30, canvas.width - 60, canvas.height - 60);

  context.fillStyle = "rgba(216, 255, 99, 0.38)";
  context.font = '800 270px "Bahnschrift", "Arial Narrow", sans-serif';
  context.textAlign = "left";
  context.textBaseline = "middle";
  context.fillText("04", 54, 228);

  context.fillStyle = "rgba(224, 235, 218, 0.2)";
  context.font = '600 30px "Cascadia Mono", Consolas, monospace';
  context.fillText("MOMENTUM / AIR TRACK", 430, 184);
  context.font = '500 22px "Cascadia Mono", Consolas, monospace';
  context.fillStyle = "rgba(224, 235, 218, 0.14)";
  context.fillText("EDUFORGE PHYSICS LAB", 432, 236);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  texture.needsUpdate = true;
  return texture;
}

function CameraIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M4 8.5h3l1.4-2h7.2l1.4 2h3v10H4z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="13" r="3.1" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}
