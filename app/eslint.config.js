// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*'],
  },
  {
    // React Three Fiber mutates three.js objects (camera, meshes, uniforms, the scene) inside useFrame by design, and its
    // JSX elements take three.js props (args, object, material…) that the DOM-prop rule doesn't know
    files: ['src/garden3d/**'],
    rules: { 'react-hooks/immutability': 'off', 'react/no-unknown-property': 'off' },
  },
]);
