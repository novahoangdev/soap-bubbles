import golden from "../../assets/scene/golden2/layout.json";
import night from "../../assets/scene/night/layout.json";
import studio from "../../assets/scene/studio/layout.json";
import dawn from "../../assets/scene/dawn/layout.json";

/**
 * The two lighting looks rendered by Blender (blender/README.md): golden hour (backlit by a low sun) and twilight with
 * fairy lights. Both share the camera, the wand and the ring position; only the pictures and the light differ.
 *  - envGain: LDR environment → linear radiance for the film reflections
 *  - sunGain / sunDir: the analytic highlight (the sun, or the brightest light cluster at night)
 */
type Layout = { w: number; h: number; sun: { x: number; y: number }; wand_front: { x: number; y: number; w: number; h: number }; sun_dir: number[]; env: { forward_u?: number } };
export type Look = {
  name: "golden" | "night" | "studio" | "dawn";
  bg: number;
  env: number;
  wand: number;
  wandRect: { x: number; y: number; w: number; h: number };
  envU0: number;
  envGain: number;
  sunGain: number;
  sunDir: number[];
  /** clear colour behind the scene (launch / letterbox) */
  base: string;
  /** blurred world seen by defocused bubbles, the wand film and the cluster walls */
  softSky: number[];
  softGround: number[];
  /** post: warm lift around the key light (uv) and its strength */
  sunUV: number[];
  warm: number;
  /** lit window behind the photographer, mirrored sharp in every bubble: [azimuth around +z, elevation, half width, half
   *  height] (rad) and its linear radiance (0 = none) */
  win: number[];
  winCol: number[];
  /** sun (golden) / key lantern (night) on screen, pt: tap it to switch looks */
  sunPt: number[];
  /** (v37) bulb lift (clipped env → hot points), film colour amount, black-film veil scale, back-surface gain */
  lookK: number[];
  /** (v37) swirl scale of the film thickness (studio: finer bands) */
  filmF: number;
};

type Extra = Pick<Look, "softSky" | "softGround" | "warm" | "win" | "winCol" | "lookK" | "filmF">;
const mk = (name: Look["name"], L: Layout, assets: { bg: number; env: number; wand: number }, envGain: number, sunGain: number, base: string, x: Extra): Look => ({
  name,
  ...x,
  sunUV: [L.sun.x / L.w, L.sun.y / L.h],
  sunPt: [L.sun.x, L.sun.y],
  ...assets,
  wandRect: L.wand_front,
  envU0: L.env.forward_u ?? 0.5,
  envGain,
  sunGain,
  sunDir: L.sun_dir,
  base,
});

export const LOOKS: Look[] = [
  mk(
    "golden",
    golden as unknown as Layout,
    {
      // (v38) golden hour v2 (blender/scripts/golden2_look.py): backlit park at sunset, peach-amber glow, creamy bokeh; the
      // v1 garden (assets/scene/bg.jpg …) read as a murky mustard wash
      bg: require("../../assets/scene/golden2/bg.jpg"),
      env: require("../../assets/scene/golden2/env.jpg"),
      wand: require("../../assets/scene/golden2/wand_front.png"),
    },
    0.5,
    0.7,
    "#0f0d0b",
    { softSky: [0.82, 0.74, 0.66], softGround: [0.03, 0.035, 0.025], warm: 0.04, win: [0, 0, 0, 0], winCol: [0, 0, 0], lookK: [0, 1, 1, 0.35], filmF: 1 },
  ),
  mk(
    "night",
    night as unknown as Layout,
    {
      bg: require("../../assets/scene/night/bg.jpg"),
      env: require("../../assets/scene/night/env.jpg"),
      wand: require("../../assets/scene/night/wand_front.png"),
    },
    5.5,
    0.9,
    "#05060d",
    {
      softSky: [0.12, 0.12, 0.3], softGround: [0.01, 0.012, 0.02], warm: 0.015,
      // a warm porch window behind and above-left of the camera (v26: replaces the soft porch glow baked into the env)
      win: [-0.42, 0.3, 0.16, 0.22], winCol: [6.5, 5.1, 3.6],
      // (v37) bulbs clip to hot points, the back image at about half
      lookK: [14, 1, 1, 0.42], filmF: 1,
    },
  ),
  // (v35) classic bubble macro photography: black velvet, one large 5000 K softbox up-left behind the camera (in the env, so
  // no analytic window) and a thin strip light right; the film colours glow on black
  mk(
    "studio",
    studio as unknown as Layout,
    {
      bg: require("../../assets/scene/studio/bg.jpg"),
      env: require("../../assets/scene/studio/env.jpg"),
      wand: require("../../assets/scene/studio/wand_front.png"),
    },
    7.0,
    0.0,
    "#000000",
    { softSky: [0.06, 0.055, 0.05], softGround: [0.004, 0.004, 0.004], warm: 0.0, win: [0, 0, 0, 0], winCol: [0, 0, 0], lookK: [-3, 1, 1, 0.35], filmF: 1 },
  ),
  // (v35) a misty pastel spring morning: blossom bokeh, the low sun hidden in the haze
  mk(
    "dawn",
    dawn as unknown as Layout,
    {
      bg: require("../../assets/scene/dawn/bg.jpg"),
      env: require("../../assets/scene/dawn/env.jpg"),
      wand: require("../../assets/scene/dawn/wand_front.png"),
    },
    0.14,
    0.35,
    "#d8c6cb",
    { softSky: [0.85, 0.72, 0.76], softGround: [0.22, 0.2, 0.22], warm: 0.03, win: [0, 0, 0, 0], winCol: [0, 0, 0], lookK: [4, 0.85, 0.25, 0.4], filmF: 1 },
  ),
];

/** EXPO_PUBLIC_LOOK=night starts in the twilight look (demo recordings of the second clip) */
export const START_LOOK = Math.max(0, LOOKS.findIndex((l) => l.name === (process.env.EXPO_PUBLIC_LOOK ?? "night")));
