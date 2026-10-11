#!/usr/bin/env node
/* CPU-only startup benchmark for the self-contained Three.js field model.

   It uses the real Three.js geometry classes and a minimal DOM/WebGL renderer
   shim, so it measures scene construction and routing without requiring a GUI
   browser in CI. Usage:

     node tools/benchmark_3d_model.mjs public/avt4_3d_model_v7.html
*/

import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { performance } from 'node:perf_hooks';

const input = path.resolve(process.argv[2] ?? 'public/avt4_3d_model_v7.html');
const html = fs.readFileSync(input, 'utf8');
const scriptSources = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
  .map((match) => match[1])
  .filter((source) => source.includes('function modelReady'));
if (scriptSources.length !== 1) throw new Error(`modelReady script not found in ${input}`);

class FakeElement {
  constructor(tagName = 'div') {
    this.tagName = tagName.toUpperCase();
    this.style = {};
    this.children = [];
    this.className = '';
    this.classList = { toggle() {}, add() {}, remove() {} };
    this.textContent = '';
    this.innerHTML = '';
    this.checked = true;
    this.disabled = false;
  }
  appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
  replaceChildren(...children) { this.children = children; }
  addEventListener() {}
  removeEventListener() {}
  setAttribute(name, value) { this[name] = value; }
  setPointerCapture() {}
  querySelector(selector) {
    const tag = selector === 'input' ? 'input' : selector.startsWith('button') ? 'button' : 'div';
    const element = new FakeElement(tag);
    this.appendChild(element);
    return element;
  }
}

const elements = new Map();
for (const id of [
  'cv', 'labels', 'loading', 'zones', 'layers', 'legend', 'reset', 'info',
  'i-tag', 'i-name', 'i-zone', 'i-tbl', 'i-fde', 'err',
]) elements.set(id, new FakeElement(id === 'cv' ? 'canvas' : 'div'));

const context = {
  console,
  performance,
  URLSearchParams,
  Float32Array,
  Int32Array,
  Uint8Array,
  Uint32Array,
  Math,
  Date,
  innerWidth: 1440,
  innerHeight: 900,
  devicePixelRatio: 2,
  location: { search: '?theme=light' },
  document: {
    hidden: false,
    documentElement: new FakeElement('html'),
    getElementById: (id) => elements.get(id) ?? new FakeElement(),
    createElement: (tag) => new FakeElement(tag),
  },
  addEventListener() {},
  removeEventListener() {},
  requestAnimationFrame(callback) { context.__nextFrame = callback; return 1; },
};
context.window = context;
context.self = context;
context.globalThis = context;
context.parent = context;
vm.createContext(context);

const threeSource = fs.readFileSync(path.resolve(path.dirname(input), 'three/three.min.js'), 'utf8');
vm.runInContext(threeSource, context, { filename: 'three.min.js' });
let sceneMetrics = null;
context.THREE.WebGLRenderer = class {
  setPixelRatio() {}
  setSize() {}
  render(scene) {
    const geometries = new Set();
    const materials = new Set();
    let objects = 0;
    scene.traverse((object) => {
      objects += 1;
      if (object.geometry) geometries.add(object.geometry);
      if (Array.isArray(object.material)) object.material.forEach((item) => materials.add(item));
      else if (object.material) materials.add(object.material);
    });
    sceneMetrics = { objects, unique_geometries: geometries.size, unique_materials: materials.size };
  }
};
vm.runInContext(scriptSources[0], context, { filename: input });

const beforeHeap = process.memoryUsage().heapUsed;
const startedAt = performance.now();
context.modelReady();
if (typeof context.__nextFrame === 'function') context.__nextFrame(performance.now() + 1000);
const durationMs = performance.now() - startedAt;
const heapDeltaMb = (process.memoryUsage().heapUsed - beforeHeap) / 1024 / 1024;
console.log(JSON.stringify({
  file: input,
  duration_ms: Number(durationMs.toFixed(1)),
  heap_delta_mb: Number(heapDeltaMb.toFixed(1)),
  ...sceneMetrics,
}));
