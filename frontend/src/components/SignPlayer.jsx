import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";

// The 3D signer (WIRING.md section 5, handoff/3d-signer.md). Plays one clip per gloss, named exactly like the
// gloss (letters are FS_A..FS_Z); a run of glosses joined by "_" may also have one clip (YOU_WANT_MORE_MILK).
// A sign with no clip yet is shown as a text card while the avatar holds its rest pose, so the sentence still reads.
// The face is set live from the translation: grammar brows from `face`, feeling from `emotion`, scaled by `intensity`.

const DEFAULT_AVATAR = "signer_tshirt";
const SIGN_SECONDS = 1.0; // a text card for a sign with no clip
const LETTER_SECONDS = 0.45; // one fingerspelled letter with no clip
const CROSSFADE = 0.2;
const LONG_FADE = 0.3; // into or out of fingerspelling: the hand travels between the ready pose and the shoulder
const TRIM = 5 / 24; // word clips walk to and from the ready pose; between two clips skip most of that walk and let the crossfade bridge sign to sign
const EASE = 0.05; // face eases with this time constant (~150 ms to settle)
const HEAD_TILT = 0.12; // radians, slight forward tilt on questions

const EMOTIONS = {
  neutral: { face: {}, speed: 1, size: 1 },
  happy: { face: { mouthSmileLeft: 0.7, mouthSmileRight: 0.7 }, speed: 1, size: 1.1 },
  sad: { face: { mouthFrownLeft: 0.6, mouthFrownRight: 0.6, browInnerUp: 0.5 }, speed: 0.85, size: 0.9 },
  angry: { face: { browDownLeft: 0.8, browDownRight: 0.8, mouthFrownLeft: 0.3, mouthFrownRight: 0.3 }, speed: 1.15, size: 1.1 },
  surprised: {
    face: { browInnerUp: 0.8, browOuterUpLeft: 0.8, browOuterUpRight: 0.8, eyeWideLeft: 0.7, eyeWideRight: 0.7, jawOpen: 0.25 },
    speed: 1.1, size: 1.15,
  },
  worried: {
    face: { browInnerUp: 0.7, mouthFrownLeft: 0.3, mouthFrownRight: 0.3, eyeWideLeft: 0.3, eyeWideRight: 0.3 },
    speed: 0.9, size: 0.95,
  },
};
const GRAMMAR = {
  "yes-no-question": { browInnerUp: 1, browOuterUpLeft: 1, browOuterUpRight: 1 },
  "wh-question": { browDownLeft: 1, browDownRight: 1 },
};
const BROWS = ["browInnerUp", "browOuterUpLeft", "browOuterUpRight", "browDownLeft", "browDownRight"];
const SIZE_BONES = ["LeftUpperArm", "LeftLowerArm", "LeftHand", "RightUpperArm", "RightLowerArm", "RightHand"];
const FACE_CUE = {
  "yes-no-question": "Eyebrows up: it's a yes/no question.",
  "wh-question": "Eyebrows down and together: it's a what/where/who question.",
};

// The table values are for intensity 0.5; intensity scales them (weights capped at 1).
const level = (intensity) => (typeof intensity === "number" ? intensity : 0.5) / 0.5;
const scaled = (v, intensity) => 1 + (v - 1) * level(intensity);

function faceTargets(face, emotion, intensity) {
  const t = {};
  for (const [name, w] of Object.entries((EMOTIONS[emotion] || EMOTIONS.neutral).face)) t[name] = Math.min(1, w * level(intensity));
  const grammar = GRAMMAR[face];
  if (grammar) {
    for (const b of BROWS) delete t[b]; // grammar brows win on questions
    Object.assign(t, grammar);
  }
  return t;
}

// Turns the glosses into playable steps: the longest run that has a clip, else a card (letters for fingerspelling).
function buildSteps(signs, clips) {
  const steps = [];
  let i = 0;
  while (i < signs.length) {
    let used = 0;
    for (let j = signs.length; j > i && !used; j--) {
      const clip = clips.get(signs.slice(i, j).map((s) => s.gloss).join("_"));
      if (clip) {
        steps.push({ kind: "clip", clip, from: i, to: j - 1, duration: clip.duration });
        used = j - i;
      }
    }
    if (used) { i += used; continue; }
    const s = signs[i];
    const letters = s.known ? [] : s.gloss.toUpperCase().replace(/[^A-Z]/g, "").split("");
    if (!letters.length) steps.push({ kind: "card", text: s.gloss, from: i, to: i, duration: SIGN_SECONDS });
    letters.forEach((letter, n) => {
      const clip = clips.get(`FS_${letter}`);
      steps.push(clip
        ? { kind: "clip", clip, from: i, to: i, letter, n, duration: clip.duration }
        : { kind: "card", text: letter, from: i, to: i, letter, n, duration: LETTER_SECONDS });
    });
    i++;
  }
  steps.forEach((s, k) => {
    if (s.kind !== "clip" || s.letter) return; // letter clips are short holds, played whole
    const trim = Math.min(TRIM, s.clip.duration / 4);
    s.start = steps[k - 1]?.kind === "clip" ? trim : 0;
    s.duration = s.clip.duration - s.start - (steps[k + 1]?.kind === "clip" ? trim : 0);
  });
  return steps;
}

const gltfCache = new Map();
function loadGltf(url) {
  if (!gltfCache.has(url)) {
    const p = new Promise((resolve, reject) => new GLTFLoader().load(url, resolve, undefined, reject));
    gltfCache.set(url, p.catch((e) => { gltfCache.delete(url); throw e; }));
  }
  return gltfCache.get(url);
}

function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return Boolean(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch {
    return false;
  }
}

// A one-key clip holding each track's first value, so the rest pose doesn't depend on where the first key sits.
function restPoseClip(clip) {
  const tracks = clip.tracks.map((t) => new t.constructor(t.name, [0], Array.from(t.values.slice(0, t.getValueSize()))));
  return new THREE.AnimationClip("IDLE", 1, tracks);
}

const POSED = [...SIZE_BONES, "Head"];
function saveBase(e) {
  e.base = {
    quats: POSED.filter((n) => e.bones[n]).map((n) => [e.bones[n], e.bones[n].quaternion.clone()]),
    morphs: e.meshes.map((m) => Float32Array.from(m.morphTargetInfluences)),
  };
}
function restoreBase(e) {
  if (!e.base) return;
  for (const [bone, q] of e.base.quats) bone.quaternion.copy(q);
  e.meshes.forEach((m, i) => { for (let k = 0; k < m.morphTargetInfluences.length; k++) m.morphTargetInfluences[k] = e.base.morphs[i][k]; });
}

const tmpQ = new THREE.Quaternion(), tmpQ2 = new THREE.Quaternion(), tmpV = new THREE.Vector3();

// Scales how far a bone has turned away from its rest pose (bigger or smaller signing).
function scaleRotation(q, rest, k) {
  tmpQ.copy(rest).invert().multiply(q);
  if (tmpQ.w < 0) tmpQ.set(-tmpQ.x, -tmpQ.y, -tmpQ.z, -tmpQ.w);
  const w = Math.min(1, tmpQ.w); // rounding can push w just past 1 for a bone at rest; unclamped, sqrt gives NaN and the arm vanishes
  const s = Math.sqrt(1 - w * w);
  if (s < 1e-4) return;
  const angle = 2 * Math.acos(w);
  tmpV.set(tmpQ.x / s, tmpQ.y / s, tmpQ.z / s);
  tmpQ.setFromAxisAngle(tmpV, angle * k);
  q.copy(rest).multiply(tmpQ);
}

export default function SignPlayer({
  signs = [], face = "statement", emotion = "neutral", intensity = 0.5, avatar = DEFAULT_AVATAR,
  newSigns = [], playing = true, speed = 1, playKey = 0, onStep, onDone, compact = false,
}) {
  const stageRef = useRef(null);
  const eng = useRef({ steps: [], stepIdx: 0, elapsed: 0, done: true, clips: new Map(), faceCur: {}, tilt: 0 });
  const props = useRef({});
  props.current = { signs, face, emotion, intensity, playing, speed, onStep, onDone };
  const [status, setStatus] = useState("loading"); // loading | ready | cards
  const [step, setStep] = useState(-1);

  // Renderer and the animation loop live for the whole mount.
  useEffect(() => {
    const e = eng.current;
    const stage = stageRef.current;
    let raf = 0;
    if (webglAvailable()) {
      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      stage.prepend(renderer.domElement);
      renderer.domElement.setAttribute("aria-hidden", "true");
      const scene = new THREE.Scene();
      scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 2.2));
      const key = new THREE.DirectionalLight(0xffffff, 2.2);
      key.position.set(1, 2, 3);
      scene.add(key);
      const camera = new THREE.PerspectiveCamera(30, 1, 0.01, 100);
      Object.assign(e, { renderer, scene, camera });
      const fit = () => {
        const w = stage.clientWidth, h = stage.clientHeight;
        if (!w || !h) return;
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
      };
      e.resize = new ResizeObserver(fit);
      e.resize.observe(stage);
      fit();
    }
    const clock = new THREE.Clock();
    const frame = () => {
      raf = requestAnimationFrame(frame);
      tick(Math.min(clock.getDelta(), 0.1));
    };
    frame();
    return () => {
      cancelAnimationFrame(raf);
      e.resize?.disconnect();
      e.mixer?.stopAllAction();
      e.renderer?.dispose();
      e.renderer?.domElement.remove();
      Object.assign(e, { renderer: null, scene: null, camera: null, mixer: null, model: null });
    };
  }, []);

  // Load (or switch) the avatar; fall back to the default avatar, then to cards only.
  useEffect(() => {
    const e = eng.current;
    let cancelled = false;
    setStatus("loading");
    if (!e.scene) { e.clips = new Map(); setStatus("cards"); return; }
    (async () => {
      let gltf = null;
      for (const name of [...new Set([avatar || DEFAULT_AVATAR, DEFAULT_AVATAR])]) {
        try { gltf = await loadGltf(`/models/${name}.glb`); break; } catch { /* try the next one */ }
      }
      if (cancelled) return;
      if (e.model) { e.mixer.stopAllAction(); e.scene.remove(e.model); e.model = null; }
      if (!gltf || !gltf.animations.length) { e.clips = new Map(); setStatus("cards"); return; }
      const model = cloneSkinned(gltf.scene);
      const mixer = new THREE.AnimationMixer(model);
      const clips = new Map(gltf.animations.map((c) => [c.name, c]));
      // Rest pose: the first frame of the first word clip (some exports rest in a T-pose; letter clips start with the hand raised).
      const idle = mixer.clipAction(restPoseClip(gltf.animations.find((c) => !c.name.startsWith("FS_")) || gltf.animations[0]));
      idle.play();
      mixer.update(0);
      model.updateMatrixWorld(true);
      const meshes = [];
      model.traverse((o) => { if (o.morphTargetDictionary && o.morphTargetInfluences) meshes.push(o); });
      const bones = {};
      for (const n of [...SIZE_BONES, "Head", "Hips", "LeftShoulder", "RightShoulder"]) bones[n] = model.getObjectByName(n);
      const rest = Object.fromEntries(SIZE_BONES.filter((n) => bones[n]).map((n) => [n, bones[n].quaternion.clone()]));
      // The character's left shoulder is on the viewer's right when it faces the camera.
      const facing = bones.LeftShoulder && bones.RightShoulder
        && bones.LeftShoulder.getWorldPosition(new THREE.Vector3()).x < bones.RightShoulder.getWorldPosition(new THREE.Vector3()).x ? -1 : 1;
      e.scene.add(model);
      frameCamera(e.camera, bones, model, facing);
      Object.assign(e, { model, mixer, clips, idle, current: idle, meshes, bones, rest, facing, base: null });      setStatus("ready");
    })();
    return () => { cancelled = true; };
  }, [avatar]);

  // A new sentence (or a replay) starts from the first sign once the avatar is ready.
  useEffect(() => {
    if (status === "loading") return;
    const e = eng.current;
    e.steps = buildSteps(signs, e.clips);
    e.stepsFor = signs;
    e.elapsed = 0;
    e.done = !e.steps.length;
    if (e.done) { toIdle(e); setStep(-1); return; }
    enter(0);
  }, [signs, playKey, status]);

  function toIdle(e) {
    if (!e.mixer || e.current === e.idle) return;
    e.idle.reset().play();
    e.current.crossFadeTo(e.idle, e.spelling ? LONG_FADE : CROSSFADE, false);
    e.current = e.idle;
    e.spelling = false;
  }

  function enter(idx) {
    const e = eng.current;
    const s = e.steps[idx];
    e.stepIdx = idx;
    e.elapsed = 0;
    setStep(idx);
    props.current.onStep?.(s.from, s.to);
    if (!e.mixer) return;
    if (s.kind === "card") return toIdle(e);
    const action = e.mixer.clipAction(s.clip);
    action.reset();
    action.time = s.start || 0;
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    action.play();
    const spelling = Boolean(s.letter);
    if (e.current !== action) e.current.crossFadeTo(action, spelling !== Boolean(e.spelling) ? LONG_FADE : CROSSFADE, false);
    e.current = action;
    e.spelling = spelling;
  }

  function tick(dt) {
    const e = eng.current;
    const p = props.current;
    const emo = EMOTIONS[p.emotion] || EMOTIONS.neutral;
    const rate = scaled(emo.speed, p.intensity) * (p.speed || 1);
    const advancing = p.playing && !e.done && e.steps.length > 0;
    if (advancing) {
      e.elapsed += dt * rate;
      if (e.elapsed >= e.steps[e.stepIdx].duration) {
        if (e.stepIdx + 1 < e.steps.length) enter(e.stepIdx + 1);
        else { e.done = true; toIdle(e); setStep(-1); p.onStep?.(-1, -1); p.onDone?.(); }
      }
    }
    if (!e.mixer) return;
    // The mixer only writes values that changed, so put back its own pose before updating;
    // otherwise the face/size/tilt layers below would build up frame after frame.
    restoreBase(e);
    e.mixer.update(advancing || e.done ? dt * (e.done ? 1 : rate) : 0);
    saveBase(e);

    const active = !e.done && e.steps.length > 0;
    const targets = active ? faceTargets(p.face, p.emotion, p.intensity) : {};
    const a = 1 - Math.exp(-dt / EASE);
    const question = active && Boolean(GRAMMAR[p.face]);
    for (const m of e.meshes) {
      for (const [name, idx] of Object.entries(m.morphTargetDictionary)) {
        if (m === e.meshes[0]) e.faceCur[name] = (e.faceCur[name] || 0) + ((targets[name] || 0) - (e.faceCur[name] || 0)) * a;
        const ours = e.faceCur[name] || 0;
        m.morphTargetInfluences[idx] = question && BROWS.includes(name) ? ours : Math.max(m.morphTargetInfluences[idx], ours);
      }
    }
    const k = scaled(emo.size, p.intensity);
    if (active && e.current !== e.idle && Math.abs(k - 1) > 0.01) {
      for (const [n, q] of Object.entries(e.rest)) scaleRotation(e.bones[n].quaternion, q, k);
    }
    e.tilt += ((question ? HEAD_TILT : 0) - e.tilt) * a;
    const head = e.bones.Head;
    if (head && Math.abs(e.tilt) > 1e-3) {
      head.parent.getWorldQuaternion(tmpQ2);
      tmpQ.setFromAxisAngle(tmpV.set(e.facing, 0, 0), e.tilt);
      head.quaternion.premultiply(tmpQ2.clone().invert().multiply(tmpQ).multiply(tmpQ2));
    }
    e.renderer.render(e.scene, e.camera);
  }

  const e = eng.current;
  const cur = step >= 0 && e.stepsFor === signs ? e.steps[step] : null;
  const fresh = new Set(newSigns);
  const showCard = cur && (cur.kind === "card" || status === "cards");
  const word = cur && cur.letter ? signs[cur.from]?.gloss : null;

  return (
    <div className={`signer${compact ? " compact" : ""}`}>
      <div className="stage" ref={stageRef}>
        {status === "loading" && <div className="stage-note">Waking up the signer…</div>}
        {status === "cards" && !cur && <div className="stage-note">{signs.length ? "Press play to sign again." : "Signs will show here."}</div>}
        {status === "ready" && !signs.length && <div className="stage-note bottom">Say or type something and I'll sign it.</div>}
        {showCard && (
          <div className="sign-card" aria-hidden="true">
            {word ? (
              <span className="spell">
                {word.toUpperCase().replace(/[^A-Z]/g, "").split("").map((L, n) => <b key={n} className={n === cur.n ? "on" : ""}>{L}</b>)}
              </span>
            ) : cur.kind === "card" ? cur.text : signs.slice(cur.from, cur.to + 1).map((s) => s.gloss).join(" ")}
            {cur.kind === "card" && !cur.letter && <small>no animation yet</small>}
            {cur.letter && <small>fingerspell</small>}
          </div>
        )}
      </div>
      <p className="sr-only" aria-live="polite">{cur ? signs.slice(cur.from, cur.to + 1).map((s) => s.gloss).join(" ") : ""}</p>
      {signs.length > 0 && (
        <div className="gloss-row" aria-label="Signs in this sentence">
          {signs.map((s, n) => (
            <span
              key={n}
              className={["gloss", cur && n >= cur.from && n <= cur.to ? "on" : "", s.known ? "" : "fs", fresh.has(s.gloss) ? "new" : ""].join(" ")}
              title={s.known ? "has a sign" : "fingerspelled"}
            >
              {s.gloss}{fresh.has(s.gloss) && <em> new!</em>}
            </span>
          ))}
        </div>
      )}
      {!compact && signs.length > 0 && FACE_CUE[face] && <p className="cue">{FACE_CUE[face]}</p>}
      {!compact && signs.length > 0 && emotion && emotion !== "neutral" && (
        <p className="cue">Feeling: {emotion}. Show it on your face and in how big you sign.</p>
      )}
    </div>
  );
}

// Frames the signing space: from a bit below the hips to just above the top of the head.
function frameCamera(camera, bones, model, facing) {
  const box = new THREE.Box3().setFromObject(model, true); // precise: measures the skinned, posed vertices
  const hips = bones.Hips ? bones.Hips.getWorldPosition(new THREE.Vector3()) : null;
  const top = box.max.y;
  const bottom = hips && hips.y < top ? hips.y : box.min.y;
  const span = top - bottom;
  const height = span * 1.4;
  const mid = box.getCenter(new THREE.Vector3());
  const center = new THREE.Vector3(mid.x, (top + bottom) / 2 - span * 0.04, mid.z);
  const dist = height / 2 / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  camera.position.set(center.x, center.y, center.z + facing * dist);
  camera.lookAt(center);
}
