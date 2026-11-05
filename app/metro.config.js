// Metro for the 3D garden on react-native-webgpu (three.js WebGPURenderer):
//  - every `three` import resolves to the WebGPU build (three/tsl and three/addons too)
//  - @react-three/fiber resolves to its web build: its "react-native" entry is the old expo-gl (OpenGL ES) path, which the
//    iOS Simulator renders on the CPU (~0.1 fps for the meadow)
const path = require("path");
const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);
const three = path.join(__dirname, "node_modules/three");
const r3f = path.join(__dirname, "node_modules/@react-three/fiber");
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName === "three" || moduleName === "three/webgpu") return { type: "sourceFile", filePath: path.join(three, "build/three.webgpu.js") };
  if (moduleName === "three/tsl") return { type: "sourceFile", filePath: path.join(three, "build/three.tsl.js") };
  if (moduleName.startsWith("three/addons/")) {
    const f = moduleName.replace("three/addons/", "");
    return { type: "sourceFile", filePath: path.join(three, "examples/jsm", f.endsWith(".js") ? f : f + ".js") };
  }
  if (moduleName === "@react-three/fiber") return { type: "sourceFile", filePath: path.join(r3f, "dist/react-three-fiber.esm.js") };
  return context.resolveRequest(context, moduleName, platform);
};
config.resolver.assetExts.push("glb", "hdr");
module.exports = config;
