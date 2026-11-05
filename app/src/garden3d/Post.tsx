import { useMemo } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three/webgpu";
import { pass, screenUV, vec3, vec4, dot, mix, smoothstep, length, pow, hash, float, uniform } from "three/tsl";
import { TIME } from "./cards";

/**
 * Film-like grade for the painted garden (three.js RenderPipeline): the raw paintings are bright and saturated; a painted
 * film frame is calmer — slightly less saturation, warm cream highlights, cool green-teal shadows, a soft lift of the
 * blacks, a gentle vignette and a fine grain that keeps flat painted areas alive.
 */
export const GRADE = { sat: uniform(0.9), warm: uniform(0.05), vignette: uniform(0.3), grain: uniform(0.012), lift: uniform(0.0) };

export function Post() {
  const { gl, scene, camera } = useThree();
  const pipe = useMemo(() => {
     
    const p = new THREE.RenderPipeline(gl as any);
    const c = pass(scene, camera, { samples: 4 }).rgb;
    const l = dot(c, vec3(0.2126, 0.7152, 0.0722));
    let g = mix(vec3(l), c, GRADE.sat);
    // split toning: cool shadows, warm highlights
    const hi = smoothstep(0.25, 0.9, l);
    g = g.mul(mix(vec3(0.95, 1.0, 1.02), vec3(1.0 + 0.6 * 0.05, 1.0, 1.0 - 0.9 * 0.05), hi));
    g = g.mul(vec3(1.0).add(vec3(1.0, 0.2, -0.6).mul(GRADE.warm).mul(hi)));
    // soft blacks (a painted frame never goes fully black); `lift` warms and opens up the follow shot, which looks down
    // into the grass and came out cooler and darker than the home view
    g = g.mul(0.94).add(vec3(0.03, 0.035, 0.03));
    g = g.mul(vec3(1.0).add(vec3(0.07, 0.05, 0.0).mul(GRADE.lift))).add(vec3(0.025, 0.022, 0.012).mul(GRADE.lift));
    const v = float(1.0).sub(pow(length(screenUV.sub(0.5)).mul(1.3), 2.4).mul(GRADE.vignette));
    // per-pixel grain (hash of one float: x + y·w + frame)
    const px = screenUV.mul(vec3(1320.0, 2868.0, 0).xy).floor();
    const n = hash(px.x.add(px.y.mul(1321.0)).add(TIME.mul(60.0).floor().mul(7919.0))).sub(0.5).mul(GRADE.grain);
    p.outputNode = vec4(g.mul(v).add(n), 1.0);
    return p;
  }, [gl, scene, camera]);
  useFrame(() => {
     
    const g = gl as any;
    const wrapped = g.render;
    g.render = g.userData?.renderRaw ?? wrapped;
    pipe.render();
    g.render = wrapped;
    g.userData?.present?.();
  }, 1);
  return null;
}
