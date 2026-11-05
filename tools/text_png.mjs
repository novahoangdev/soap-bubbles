// text_png.mjs: render one line of text to a transparent PNG with CanvasKit (Skia), for video overlays (this ffmpeg build has
// no drawtext).   node tools/text_png.mjs "<text>" <size px> <#rrggbb> out.png [font file]
import fs from "fs";
import path from "path";
import { createRequire } from "module";
const here = path.dirname(new URL(import.meta.url).pathname);
const app = path.resolve(here, "../app");
const require = createRequire(path.join(app, "package.json"));
const CanvasKitInit = require("canvaskit-wasm/bin/full/canvaskit.js");
const CK = await CanvasKitInit({ locateFile: (f) => path.join(app, "node_modules/canvaskit-wasm/bin/full", f) });
const [text, sizeS, color, out, fontArg] = process.argv.slice(2);
const size = Number(sizeS);
const fontFile = fontArg || [
  `${process.env.HOME}/Library/Fonts/SFProDisplay-Semibold.otf`,
  `${process.env.HOME}/Library/Fonts/SFProDisplay-Medium.otf`,
  "/System/Library/Fonts/Supplemental/Arial.ttf",
].find((f) => fs.existsSync(f));
const tf = CK.Typeface.MakeFreeTypeFaceFromData(fs.readFileSync(fontFile).buffer);
const font = new CK.Font(tf, size);
const ids = font.getGlyphIDs(text);
const widths = font.getGlyphWidths(ids);
const w = Math.ceil(widths.reduce((a, b) => a + b, 0) + size * 0.4);
const h = Math.ceil(size * 1.45);
const surf = CK.MakeSurface(w, h);
const c = surf.getCanvas();
c.clear(CK.TRANSPARENT);
const p = new CK.Paint();
p.setAntiAlias(true);
p.setColor(CK.parseColorString(color));
c.drawText(text, size * 0.2, size * 1.08, p, font);
const img = surf.makeImageSnapshot();
fs.writeFileSync(out, Buffer.from(img.encodeToBytes()));
console.log(out, w, h);
