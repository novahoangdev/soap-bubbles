import { useEffect, useMemo, useRef, useState } from "react";
import { Animated, Easing, Pressable, StyleSheet, Text, View, type GestureResponderEvent } from "react-native";
import { TIMESCALE, ms } from "../scene/clock";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three/webgpu";
import { normalWorld, normalize, dot, vec3, mix, smoothstep, max, pow, positionWorld, cameraPosition, uniform, float, uv, sin } from "three/tsl";
import { useSharedValue } from "react-native-reanimated";
import { BreathMic } from "../audio/breath";
import { MicHint } from "../ui/MicHint";
import { sfx, initSfx, startMusic } from "../fx/sfx";
import { fireHaptic } from "../fx/haptics";
import { FiberCanvas } from "./FiberCanvas";
import { Post, GRADE } from "./Post";
import { Droplets } from "./Droplets";
import { World, groundAt, SUN_DIR, GARDEN, TRUNKS } from "./World";
import { makeBubbleMaterial, SUN, FOLLOW } from "./bubbleMaterial";
import { LENS, TIME } from "./cards";
import { MAXB, bubbleMatrix, makeSim3D, popBubble, stepSim3D, type Sim3D } from "./sim3d";
import { demoBreath3D, DEMO3D } from "./demo3d";

/**
 * Garden 3D: blow soap bubbles into a deep painted meadow (three.js WebGPURenderer on react-native-webgpu, scenes in
 * React Three Fiber). The player stands in the meadow with the wand in front of the camera. Blow (mic, or press and hold)
 * to inflate a bubble on the ring; it flies off along the breath. When a big one has flown for a moment the camera eases
 * after it, dollying in and narrowing the lens, follows it over the flowers until it pops, then drifts back to the wand.
 */
const DBG = { renders: 0 };
// low in the meadow, among the flowers (art director: the camera looked down onto a flower carpet)
const HOME = new THREE.Vector3(0, 0.36, 2.4);
const HOME_LOOK = new THREE.Vector3(0, 1.3, -8);
const FOV_HOME = 52;
const FOV_FOLLOW = 40;
/** the wand in camera space (m): low and near the middle of the frame, a little in front (g32 sat at x 0.075, most of
 * the way to the right edge of the narrow portrait view) */
const WAND_CAM = new THREE.Vector3(0.012, -0.118, -0.42);
const HOME_FWD = HOME_LOOK.clone().sub(HOME).normalize();

type Rig = {
  mode: "home" | "follow" | "return";
  t: number;
  pos: THREE.Vector3;
  /** gaze direction (unit) */
  look: THREE.Vector3;
  fov: number;
  /** scene time since the garden finished loading (the demo script runs on it) */
  sceneT: number;
};

/** painted toon shading for the wand: two soft tones, a cool shadow side, a warm rim and one soft highlight */
/** frame rate (real seconds) under which the garden lowers its resolution; EXPO_PUBLIC_FPS_FLOOR to test */
const FPS_FLOOR = Number(process.env.EXPO_PUBLIC_FPS_FLOOR ?? 48);

const toon = (lit: string, shadow: string, rimCol: string) => {
  const m = new THREE.MeshBasicNodeMaterial();
  const N = normalize(normalWorld);
  const L = vec3(SUN_DIR.x, SUN_DIR.y, SUN_DIR.z);
  const V = normalize(cameraPosition.sub(positionWorld));
  const ndl = dot(N, L);
  // soft painted form (round 5: it read flat): a wide light-to-shade turn, a cool sky rim on the upper side, a broad
  // satin highlight
  const base = mix(uniform(new THREE.Color(shadow)), uniform(new THREE.Color(lit)), smoothstep(-0.45, 0.6, ndl));
  const fres = pow(max(dot(N, V).oneMinus(), 0.0), 2.5);
  const rim = fres.mul(0.3);
  const sky = vec3(0.62, 0.72, 0.9).mul(fres.mul(0.35).mul(max(N.y, 0.0)));
  const spec = smoothstep(0.82, 0.97, dot(N, normalize(L.add(V)))).mul(0.3);
  m.colorNode = base.mul(mix(float(0.86), float(1.0), smoothstep(-0.6, 0.4, N.y))).add(uniform(new THREE.Color(rimCol)).mul(rim)).add(sky).add(vec3(1, 1, 1).mul(spec));
  return m;
};

const LEAN = new THREE.Quaternion().setFromEuler(new THREE.Euler(0.1, 0, -0.1, "ZXY"));

function Wand({ ringOut }: { ringOut: THREE.Vector3 }) {
  const ref = useRef<THREE.Group>(null);
  const { camera } = useThree();
  // pale birch wood, matte, painted soft, no outline (round 14: even dusty rose read as a plastic toy)
  const pink = useMemo(() => toon("#e6d6bd", "#b39d80", "#fff4e4"), []);
  // the stick in the same matte dusty rose, a shade deeper (a mint stick read as translucent plastic)
  const mint = useMemo(() => toon("#dccbae", "#a89276", "#fff4e4"), []);
  // the soap film resting in the ring: faint drifting pastel interference bands (round 6: the empty ring read as a toy)
  const film = useMemo(() => {
    const m = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide });
    const q = uv().sub(0.5);
    const d = q.length().mul(2.0);
    const ph = d.mul(2.2).add(sin(q.x.mul(9.0).add(TIME.mul(0.7))).mul(0.18)).add(TIME.mul(0.12)).add(q.y.mul(1.4));
    const band = vec3(sin(ph.mul(6.283)), sin(ph.mul(6.283).add(2.1)), sin(ph.mul(6.283).add(4.2))).mul(0.5).add(0.5);
    // (round 12: a whitish film read as a magnifying glass: barely there, the sheen only)
    m.colorNode = mix(vec3(1.0, 0.98, 0.95), band, 0.6);
    m.opacityNode = float(0.035).add(smoothstep(0.55, 1.0, d).mul(0.06));
    return m;
  }, []);
  const st = useMemo(() => ({ off: new THREE.Vector3(), held: new THREE.Vector3(), heldQ: new THREE.Quaternion(), q: new THREE.Quaternion(), fwd: new THREE.Vector3(), init: false }), []);
  useFrame(() => {
    const g = ref.current;
    if (!g) return;
    // held still at the bottom of the frame while the camera is home; when the camera takes off after a bubble the wand
    // stays where it was (it used to ride along with the camera, sinking and rising back), and the camera comes back to it
    st.off.copy(WAND_CAM).applyMatrix4(camera.matrixWorld);
    st.q.copy(camera.quaternion);
    // a slight lean, as if held in a hand (g32: −0.28 rad read as tipped over to the right)
    st.q.multiply(LEAN);
    camera.getWorldDirection(st.fwd);
    const near = 1 - THREE.MathUtils.smoothstep(camera.position.distanceTo(HOME), 0.05, 0.3);
    const level = 1 - THREE.MathUtils.smoothstep(st.fwd.angleTo(HOME_FWD), 0.09, 0.3);
    const w = near * level;
    if (!st.init || w > 0.999) {
      st.held.copy(st.off);
      st.heldQ.copy(st.q);
      st.init = true;
    }
    g.position.copy(st.held).lerp(st.off, w);
    g.quaternion.copy(st.heldQ).slerp(st.q, w);
    ringOut.copy(g.position);
  });
  const R = 0.028, tube = 0.0019;
  return (
    <group ref={ref}>
      <mesh material={pink}>
        <torusGeometry args={[R, tube, 16, 72]} />
      </mesh>
      <mesh material={film} renderOrder={4}>
        <circleGeometry args={[R - tube * 0.5, 48]} />
      </mesh>
      <mesh material={mint} position={[0, -R - 0.09, 0]}>
        <cylinderGeometry args={[0.005, 0.0058, 0.18, 16]} />
      </mesh>
    </group>
  );
}

function Bubbles({ sim, breath, hold, rig }: { sim: Sim3D; breath: { value: number }; hold: { current: number }; rig: Rig }) {
  const { gl, scene, camera } = useThree();
  // the garden as the films see it: a cube map rendered from the middle of the meadow (bubbles hidden), refreshed slowly
  const cube = useMemo(() => {
    // small and mip-mapped: the films sample a soft garden (a sharp 256² map of the dense meadow glittered with noise)
    const rt = new THREE.CubeRenderTarget(128, { generateMipmaps: true, minFilter: THREE.LinearMipmapLinearFilter });
    const cam = new THREE.CubeCamera(0.1, 900, rt);
    cam.position.set(0, 1.2, -6);
    return { rt, cam };
  }, []);
  const geo = useMemo(() => new THREE.SphereGeometry(1, 48, 32), []);
  const back = useMemo(() => makeBubbleMaterial(cube.rt.texture, "back"), [cube]);
  const front = useMemo(() => makeBubbleMaterial(cube.rt.texture, "front"), [cube]);
  const data = useMemo(() => new THREE.InstancedBufferAttribute(new Float32Array(MAXB * 4), 4), []);
  const popd = useMemo(() => new THREE.InstancedBufferAttribute(new Float32Array(MAXB * 3), 3), []);
  useMemo(() => {
    geo.setAttribute("iData", data);
    geo.setAttribute("iPop", popd);
    SUN.value.copy(SUN_DIR);
  }, [geo, data, popd]);
  const backRef = useRef<THREE.InstancedMesh>(null);
  const frontRef = useRef<THREE.InstancedMesh>(null);
  const envT = useRef(-1);
  const fps = useRef({ n: 0, t: 0 });
  const lastEv = useRef({ pops: 0, big: 0, release: 0, spray: 0 });
  const m = useMemo(() => new THREE.Matrix4(), []);
  const ring = useMemo(() => new THREE.Vector3(), []);
  const fwd = useMemo(() => new THREE.Vector3(), []);
  const up = useMemo(() => new THREE.Vector3(0, 1, 0), []);

  useFrame((state, dtRaw) => {
    if (!GARDEN.ready || !GARDEN.flowers) return;
    const dt = Math.min(dtRaw, 1 / 30) * TIMESCALE;
    const t = state.clock.elapsedTime * TIMESCALE;
    if (rig.sceneT === 0) {
      console.log("GARDEN3D_READY");
      GARDEN.onStart?.();
    }
    rig.sceneT += dt;
    fps.current.n++;
    const rt = state.clock.elapsedTime;
    if (rt - fps.current.t > 2) {
      const f = fps.current.n / (rt - fps.current.t);
      console.log(`FPS ${f.toFixed(1)} renders ${DBG.renders}`);
      fps.current = { n: 0, t: rt };
      // a slower GPU (an older phone): step the resolution down rather than stutter (native 3× → 2.25 → 1.5)
      const dpr = state.viewport.dpr;
      if (rt > 5 && f < FPS_FLOOR && dpr > 1.6) {
        state.setDpr(Math.max(1.5, dpr - 0.75));
        console.log(`GARDEN3D_DPR ${state.viewport.dpr}`);
      }
    }
    // env refresh (first frames, then every 4 s): render the six faces without presenting them
    if (envT.current < 0 || t - envT.current > 4) {
      const bv = backRef.current, fv = frontRef.current;
      if (bv) bv.visible = false;
      if (fv) fv.visible = false;
       
      const g = gl as any;
      const wrapped = g.render;
      g.render = g.userData?.renderRaw ?? wrapped;
      cube.cam.update(g, scene);
      g.render = wrapped;
      if (bv) bv.visible = true;
      if (fv) fv.visible = true;
      envT.current = t;
    }
    camera.getWorldDirection(fwd);
    const b = rig.mode === "home" ? Math.max(breath.value, hold.current, DEMO3D ? demoBreath3D(rig.sceneT) : 0) : 0;
    const ev0 = { ...sim.events };
    stepSim3D(sim, dt, ring, fwd, up, b, groundAt);
    if (sim.events.big > ev0.big) sfx("pop_big");
    else if (sim.events.pops > ev0.pops) sfx("pop", 0.8 + Math.random() * 0.2);
    if (sim.events.release > ev0.release) sfx("bloop");
    if (DEMO3D) {
      // event log for the promo audio (tools/events3d.py): scene seconds of every pop / release / spray in this run
      const L = lastEv.current, E = sim.events;
      if (E.pops !== L.pops || E.release !== L.release || E.spray !== L.spray) {
        console.log(`EVT3 ${rig.sceneT.toFixed(3)} pops=${E.pops - L.pops} big=${E.big - L.big} release=${E.release - L.release} spray=${E.spray - L.spray} heroBig=${sim.hero >= 0 && sim.b[sim.hero].big ? 1 : 0}`);
        lastEv.current = { ...E };
      }
    }
    const bv = backRef.current, fv = frontRef.current;
    if (!bv || !fv) return;
    let k = 0;
    const D = data.array as Float32Array, P = popd.array as Float32Array;
    for (let i = 0; i < MAXB; i++) {
      const x = sim.b[i];
      if (!x.alive) continue;
      bubbleMatrix(x, m);
      bv.setMatrixAt(k, m);
      fv.setMatrixAt(k, m);
      const popA = x.pop < 0 ? -1 : (x.pop / (0.09 * Math.min(2, Math.max(1, Math.sqrt(x.r / 0.05))))) * 3.3;
      D.set([x.age, x.seed, x.th, popA], k * 4);
      P.set([x.popDir.x, x.popDir.y, x.popDir.z], k * 3);
      k++;
    }
    bv.count = fv.count = k;
    bv.instanceMatrix.needsUpdate = fv.instanceMatrix.needsUpdate = true;
    data.needsUpdate = popd.needsUpdate = true;
  });
  return (
    <>
      <instancedMesh ref={backRef} args={[geo, back, MAXB]} frustumCulled={false} renderOrder={5} />
      <instancedMesh ref={frontRef} args={[geo, front, MAXB]} frustumCulled={false} renderOrder={6} />
      <Wand ringOut={ring} />
    </>
  );
}

/** camera: home at the wand; after a big bubble has flown ~1.1 s, ease after it (dolly + zoom), back home when it pops */
function CameraRig({ sim, rig }: { sim: Sim3D; rig: Rig }) {
  const { camera } = useThree();
  const target = useMemo(() => new THREE.Vector3(), []);
  const lookT = useMemo(() => new THREE.Vector3(), []);
  const vdir = useMemo(() => new THREE.Vector3(), []);
  const wantD = useMemo(() => new THREE.Vector3(), []);
  const lookP = useMemo(() => new THREE.Vector3(), []);
  // the camera's velocity (m/s), measured in follow / home, integrated while it glides home
  const vel = useMemo(() => new THREE.Vector3(), []);
  const prev = useMemo(() => new THREE.Vector3().copy(HOME), []);
  // the way home after the pop: one smooth curve (a cubic Bézier from where the camera is, up over the meadow, down onto
  // the wand), carrying the camera's own drift at the start, eased in and out (user: the old glide stopped dead, then
  // went up, back and down "like a square")
  const ret = useMemo(() => ({ p0: new THREE.Vector3(), v0: new THREE.Vector3(), l0: new THREE.Vector3(), p1: new THREE.Vector3(), p2: new THREE.Vector3(), D: 6 }), []);
  useFrame((state, dtRaw) => {
    const dt = Math.min(dtRaw, 1 / 30) * TIMESCALE;
    const t = state.clock.elapsedTime * TIMESCALE;
    rig.t += dt;
    const hero = sim.hero >= 0 ? sim.b[sim.hero] : null;
    const heroAlive = !!hero && hero.alive && hero.pop < 0 && !hero.attached;
    // (a moment to watch it float off before the camera goes after it)
    if (rig.mode === "home" && heroAlive && sim.t - sim.heroT > 1.8) {
      rig.mode = "follow";
      rig.t = 0;
    }
    if (rig.mode === "follow" && (!heroAlive || rig.t > 14)) {
      if (heroAlive) {
        popBubble(sim, sim.hero);
        if (DEMO3D) console.log(`EVT3HERO ${rig.sceneT.toFixed(3)}`);
      }
      rig.mode = "return";
      rig.t = 0;
      ret.p0.copy(rig.pos);
      ret.v0.copy(vel);
      ret.l0.copy(rig.look);
      const dist = rig.pos.distanceTo(HOME);
      ret.D = THREE.MathUtils.clamp(dist / 0.85 + 1.5, 5, 8); // ~8 s from deep in the meadow, ≤ ~1.3 m/s
      ret.p1.copy(HOME).sub(rig.pos).multiplyScalar(0.3).add(rig.pos);
      ret.p1.y += 0.3;
      ret.p2.set(HOME.x, HOME.y + 0.3, HOME.z + 0.15);
    }
    if (rig.mode === "return" && rig.t >= ret.D) {
      rig.mode = "home";
      rig.t = 0;
    }
    let k: number, fovT = FOV_HOME;
    if (rig.mode === "follow" && hero) {
      // behind and a little above the bubble, looking past it over the meadow
      vdir.copy(hero.v);
      vdir.y = 0;
      if (vdir.lengthSq() < 1e-4) vdir.set(0, 0, -1);
      vdir.normalize();
      // (round 14: further behind, so the flight ends on sky and clearing, not a wall of painted trees)
      const back = 0.85 + hero.r * 4;
      target.copy(hero.p).addScaledVector(vdir, -back);
      // a little above the bubble and never skimming the grass (a low camera looking down filled the frame with blades)
      // (g16: the bubble now floats at ~1 m; level with it, the meadow reads at a grazing angle instead of bare ground
      // between blades seen from above)
      target.y += -0.08 + hero.r * 0.5;
      target.y = Math.max(target.y, groundAt(target.x, target.z) + 0.55);
      // look just past the bubble so it sits in the frame (0.6 m past it, it hung at the edge of the narrow portrait view)
      lookT.copy(hero.p).addScaledVector(vdir, 0.22);
      // looking a little up (round 8: the lower 60 % of the follow frame was a wall of grass)
      lookT.y += 0.09; // (round 20: at +0.16 the top third of the follow frame was empty sky)
      // keep the view within ±72° of straight down the meadow (the garden is built ahead of the player)
      {
        const lx = lookT.x - target.x, lz = lookT.z - target.z;
        const yaw = Math.atan2(lx, -lz), lim = 1.25;
        if (Math.abs(yaw) > lim) {
          const yy = Math.sign(yaw) * lim, d = Math.hypot(lx, lz);
          lookT.x = target.x + Math.sin(yy) * d;
          lookT.z = target.z - Math.cos(yy) * d;
        }
      }
      // never inside or right against a tree trunk
      for (const [tx, tz, tr] of TRUNKS) {
        const dx = target.x - tx, dz = target.z - tz, d = Math.hypot(dx, dz), R = tr + 0.9;
        if (d < R && d > 1e-3) { target.x = tx + (dx / d) * R; target.z = tz + (dz / d) * R; }
      }
      k = 0.5 + Math.min(1, rig.t / 3) * 1.6; // eases in slowly

      fovT = FOV_FOLLOW;
    } else {
      target.copy(HOME);
      lookT.copy(HOME_LOOK);
      // coming home: over the wand and back down to it from behind (straight back, the camera reversed through the
      // wand, which filled the bottom of the frame: the curve home comes down onto it from above)
      // a breathing handheld sway
      target.x += Math.sin(t * 0.7) * 0.015;
      target.y += Math.sin(t * 1.1) * 0.01;
      // a slow drift of the gaze across the meadow, so a long hold never looks frozen
      lookT.x += Math.sin(t * 0.13) * 0.45;
      // (home: the pull builds up over ~2 s, so the hand-over from the glide home keeps its speed)
      k = rig.mode === "return" ? 0.9 : Math.min(3, 0.6 + rig.t * 1.2);
    }
    const a = 1 - Math.exp(-k * dt);
    let eLook = -1;
    if (rig.mode === "return") {
      const u = Math.min(1, rig.t / ret.D);
      const e = u * u * u * (u * (u * 6 - 15) + 10); // smootherstep: starts and ends at rest along the curve
      const w = 1 - e, b0 = w * w * w, b1 = 3 * w * w * e, b2 = 3 * w * e * e, b3 = e * e * e;
      rig.pos.set(0, 0, 0).addScaledVector(ret.p0, b0).addScaledVector(ret.p1, b1).addScaledVector(ret.p2, b2).addScaledVector(HOME, b3);
      // the drift it had when the bubble popped, dying away over ~1 s (so the move starts at its own speed, no stop)
      rig.pos.addScaledVector(ret.v0, 0.8 * (1 - Math.exp(-rig.t / 0.8)) * w);
      eLook = THREE.MathUtils.smootherstep(u, 0.05, 0.9);
    } else rig.pos.lerp(target, a);
    if (dt > 1e-4) vel.copy(rig.pos).sub(prev).divideScalar(dt);
    prev.copy(rig.pos);
    // the gaze turns as a direction, at most ~50°/s: lerping the look-at POINT whipped the view round when the target
    // jumped from a bubble 1 m away to the far meadow (g4: a 0.2 s whip pan at the pop)
    wantD.copy(lookT).sub(rig.pos).normalize();
    if (eLook >= 0) {
      // coming home the gaze swings round with the same easing as the move
      rig.look.copy(ret.l0).lerp(wantD, eLook).normalize();
    } else {
      const ang = rig.look.angleTo(wantD);
      const f = ang > 1e-5 ? Math.min(1, a * 1.3, ((rig.mode === "follow" ? 1.8 : 0.9) * dt) / ang) : 1;
      rig.look.lerp(wantD, f).normalize();
    }
    rig.fov += (fovT - rig.fov) * (1 - Math.exp(-1.5 * dt));
    camera.position.copy(rig.pos);
    camera.lookAt(lookP.copy(rig.pos).add(rig.look));
    const pc = camera as THREE.PerspectiveCamera;
    if (Math.abs(pc.fov - rig.fov) > 0.01) {
      pc.fov = rig.fov;
      pc.updateProjectionMatrix();
    }
    // (demo) where the follow camera goes, for placing the flowers along its path
    if (DEMO3D && rig.mode !== "home" && Math.floor(rig.t * 4) !== Math.floor((rig.t - dt) * 4))
      console.log(`CAM3 ${rig.mode} ${rig.t.toFixed(2)} v ${vel.length().toFixed(2)} cam ${camera.position.x.toFixed(2)} ${camera.position.z.toFixed(2)} look ${rig.look.x.toFixed(2)} ${rig.look.z.toFixed(2)}`);
    // follow-shot grade lift (eases in and out with the camera)
    GRADE.lift.value += ((rig.mode === "follow" ? 1 : 0) - GRADE.lift.value) * (1 - Math.exp(-1.2 * dt));
    FOLLOW.value = GRADE.lift.value;
    // the lens: at home focused a few metres out (the near flowers go soft, as in a low meadow shot); following, on the bubble
    const focusT = rig.mode === "follow" && hero ? Math.max(0.3, hero.p.distanceTo(camera.position)) : 3.2;
    LENS.focus.value += (focusT - LENS.focus.value) * (1 - Math.exp(-4 * dt));
  });
  return null;
}

export function Garden3D({ onExit }: { onExit?: () => void }) {
  const sim = useMemo(() => makeSim3D(11), []);
  const [veil] = useState(() => new Animated.Value(1));
  useEffect(() => {
    // started from the frame loop on the scene clock's first frame: the fade's first frame marks app t = 0 in a recording
    // (tools/filmstart3d.py), so it is linear
    GARDEN.onStart = () => Animated.timing(veil, { toValue: 0, duration: ms(700), easing: Easing.linear, useNativeDriver: true }).start();
    return () => {
      GARDEN.onStart = undefined;
    };
  }, [veil]);
  const breath = useSharedValue(0);
  const hold = useRef(0);
  const holding = useRef(false);
  const rig = useMemo<Rig>(() => ({ mode: "home", t: 0, pos: HOME.clone(), look: HOME_LOOK.clone().sub(HOME).normalize(), fov: FOV_HOME, sceneT: 0 }), []);
  const camRef = useRef<THREE.PerspectiveCamera | null>(null);
  const size = useRef({ w: 1, h: 1 });
  useEffect(() => {
    initSfx();
    startMusic();
    // press-and-hold breath: ramps up while held, eases off on release
    const id = setInterval(() => {
      hold.current = holding.current ? Math.min(0.85, hold.current + 0.06) : Math.max(0, hold.current - 0.12);
      // (lets the first-run hint know a breath happened, also when it came from a hold)
      if (hold.current > 0.2 && breath.value < hold.current) breath.value = hold.current;
    }, 33);
    return () => clearInterval(id);
  }, [breath]);
  const tap = (e: GestureResponderEvent) => {
    // pop the bubble under the finger (ray-sphere against every free bubble)
    const cam = camRef.current;
    if (!cam) return;
    const { locationX, locationY } = e.nativeEvent;
    const ndc = new THREE.Vector2((locationX / size.current.w) * 2 - 1, -(locationY / size.current.h) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, cam);
    let best = -1, bd = 1e9;
    sim.b.forEach((x, i) => {
      if (!x.alive || x.pop >= 0 || x.attached) return;
      const d = ray.ray.distanceToPoint(x.p);
      const along = x.p.clone().sub(ray.ray.origin).dot(ray.ray.direction);
      if (d < x.r * 1.4 + 0.02 && along < bd) { bd = along; best = i; }
    });
    if (best >= 0) {
      popBubble(sim, best, ray.ray.direction.clone().negate());
      fireHaptic("light");
    }
  };
  return (
    <View style={styles.root} onLayout={(e) => (size.current = { w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height })}>
      {!DEMO3D && <BreathMic out={breath} />}
      {!DEMO3D && <MicHint breath={breath} top={250} lines={["blow gently", "into the mic · or press and hold", "a big bubble flies off: follow it"]} />}
      <FiberCanvas
        style={StyleSheet.absoluteFill}
        camera={{ fov: FOV_HOME, near: 0.02, far: 1200, position: [HOME.x, HOME.y, HOME.z] }}
        onCreated={({ gl, camera }) => {
           
          const g = gl as any;
          g.toneMapping = THREE.NoToneMapping;
          camRef.current = camera as THREE.PerspectiveCamera;
          const r0 = g.render;
          g.render = (s: THREE.Scene, c: THREE.Camera) => {
            DBG.renders++;
            r0(s, c);
          };
        }}
      >
        <World />
        <Bubbles sim={sim} breath={breath} hold={hold} rig={rig} />
        <Droplets sim={sim} />
        <CameraRig sim={sim} rig={rig} />
        <Post />
      </FiberCanvas>
      {/* a soft haze veil until the paintings and the flowers are in (the first frames showed an empty, unlit scene) */}
      <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.veil, { opacity: veil }]} />
      <Pressable
        style={StyleSheet.absoluteFill}
        onPress={tap}
        onLongPress={() => (holding.current = true)}
        delayLongPress={160}
        onPressOut={() => (holding.current = false)}
      />
      {onExit && (
        <Pressable style={styles.exit} onPress={onExit} hitSlop={12}>
          <Text style={styles.exitText}>2D</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#e6ecdc" },
  veil: { backgroundColor: "#e6ecdc" },
  exit: { position: "absolute", top: 58, left: 18, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 14, backgroundColor: "rgba(255,255,255,0.55)" },
  exitText: { color: "#3e5a35", fontWeight: "600", fontSize: 13 },
});
