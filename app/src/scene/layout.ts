import raw from "../../assets/scene/layout.json";

/**
 * Scene layout exported by Blender (render_passes.py), in pt on the 440×956 design frame (iPhone 17 Pro Max).
 * Every layer draws inside a Group scaled "cover" to this frame, so shader and physics coordinates are design pt too.
 */
type Raw = {
  w: number;
  h: number;
  ring: { x: number; y: number; r_inner: number; r_outer: number };
  wand_front: { x: number; y: number; w: number; h: number };
  sun: { x: number; y: number };
  sun_dir: number[];
  env: { forward_u?: number };
};
const L = raw as unknown as Raw;
export const VIEW = { w: L.w, h: L.h };
export const RING = { x: L.ring.x, y: L.ring.y, r: L.ring.r_inner, ro: L.ring.r_outer };
export const WAND = L.wand_front;
export const SUN = L.sun;
export const SUN_DIR = L.sun_dir;
export const ENV_U0 = L.env.forward_u ?? 0.5;

export type Fit = { k: number; ox: number; oy: number };
export const fitView = (w: number, h: number): Fit => {
  "worklet";
  const k = Math.max(w / VIEW.w, h / VIEW.h) || 1;
  return { k, ox: (w - VIEW.w * k) / 2, oy: (h - VIEW.h * k) / 2 };
};
