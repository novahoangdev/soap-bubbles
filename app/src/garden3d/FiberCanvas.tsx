import * as THREE from "three/webgpu";
import React, { useEffect, useRef } from "react";
import { PixelRatio, Image, type ViewProps } from "react-native";
import { extend, createRoot, unmountComponentAtNode, events, type ReconcilerRoot, type RootState } from "@react-three/fiber";
import { Canvas, type CanvasRef } from "react-native-webgpu";

/**
 * React Three Fiber on react-native-webgpu (Dawn → Metal): three.js's WebGPURenderer drawing into a native WebGPU canvas.
 * Adapted from the react-native-webgpu example (apps/example/src/ThreeJS/components/FiberCanvas.tsx). R3F never calls the
 * canvas's present(), so the renderer's render() is wrapped to do it.
 */
type Props = {
  children: React.ReactNode;
  style?: ViewProps["style"];
  onCreated?: (s: RootState) => void;
  camera?: { fov: number; near: number; far: number; position: [number, number, number] };
};

export function FiberCanvas({ children, style, onCreated, camera }: Props) {
  const root = useRef<ReconcilerRoot<HTMLCanvasElement> | null>(null);
   
  React.useMemo(() => extend(THREE as any), []);
  const ref = useRef<CanvasRef>(null);
  useEffect(() => {
    const context = ref.current!.getContext("webgpu")!;
    const renderer = new THREE.WebGPURenderer({ antialias: true, canvas: context.canvas as unknown as HTMLCanvasElement, context });
    const canvas = context.canvas as unknown as HTMLCanvasElement;
    canvas.width = canvas.clientWidth * PixelRatio.get();
    canvas.height = canvas.clientHeight * PixelRatio.get();
    const size = { top: 0, left: 0, width: canvas.clientWidth, height: canvas.clientHeight };
    if (!root.current) root.current = createRoot(canvas);
    root.current.configure({
      size,
      events,
       
      gl: renderer as any,
      camera,
      frameloop: "always",
      // native resolution (dpr 1 rendered 440×956 and upscaled 3×: stair-stepped foliage edges, soft everything)
      dpr: Number(process.env.EXPO_PUBLIC_DPR3D ?? PixelRatio.get()),
      onCreated: async (state: RootState) => {
         
        const gl = state.gl as any as THREE.WebGPURenderer;
        await gl.init();
        const renderFrame = gl.render.bind(gl);
        // off-screen passes (the bubbles' cube map) render without presenting
         
        (gl as any).userData = { renderRaw: renderFrame, present: () => context.present() };
         
        (gl as any).render = (s: THREE.Scene, c: THREE.Camera) => {
          renderFrame(s, c);
          context.present();
        };
        onCreated?.(state);
      },
    });
    root.current.render(children);
    return () => {
      unmountComponentAtNode(canvas);
      renderer.setAnimationLoop(null);
      renderer.dispose();
      root.current = null;
    };
    // the scene is built once; rebuilding the GPU context on every parent render would be wasteful
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <Canvas ref={ref} style={style} />;
}

/**
 * Textures from bundled images: fetch the bytes Metro serves (or the release bundle holds) and decode them with the native
 * createImageBitmap that react-native-webgpu installs (three's ImageLoader needs a DOM <img>).
 */
const cache = new Map<number, Promise<THREE.Texture>>();
export const loadTexture = (mod: number, opts: { repeat?: boolean; srgb?: boolean } = {}) => {
  const hit = cache.get(mod);
  if (hit) return hit;
  const p = (async () => {
    const uri = Image.resolveAssetSource(mod)!.uri;
    const buf = await (await fetch(uri)).arrayBuffer();
    const bmp = await createImageBitmap(buf as unknown as Blob, { premultiplyAlpha: "none" } as ImageBitmapOptions);
    const t = new THREE.Texture(bmp as unknown as HTMLImageElement);
    t.flipY = true;
    t.colorSpace = opts.srgb === false ? THREE.NoColorSpace : THREE.SRGBColorSpace;
    t.anisotropy = 4;
    t.generateMipmaps = true;
    t.minFilter = THREE.LinearMipmapLinearFilter;
    if (opts.repeat) t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.needsUpdate = true;
    return t;
  })();
  cache.set(mod, p);
  return p;
};
