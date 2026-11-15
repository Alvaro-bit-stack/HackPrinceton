# How to animate signs on the glasses signer

A handoff for whoever (person or AI) animates the next signs. **Done already:** all 19 vocabulary signs and `FS_A` … `FS_Z` are in `signer_glasses.glb` (section 0). The rest of this file records the rig's conventions and the method, so new signs match.

Everything here was done in Blender 5.2 through the Blender MCP server (`execute_blender_code`, which runs Python inside the open Blender). If you work another way, the Python still applies: paste it into Blender's Text Editor and run it.

---

## 0. What's built and how to rebuild it

All of it is driven by Text blocks inside the .blend (Text Editor), run in this order:

| Text block | What it does |
|---|---|
| `sign_lib` | Helpers (`arm`, `fingers`, handshape table `HS` named like ASL-LEX codes, face landmarks `LM`) and `solve()`, which finds arm angles that put a hand point (palm, fingertip, thumb tip, knuckles) on a 3D target with a given finger and palm direction. It runs in about 0.5 s per pose. |
| `signs_words` | One entry per sign: key frames with hand targets, mouthing and head motion, written from that sign's ASL-LEX coding (handshape, location, movement, repetition) and the ASL-LEX reference videos. |
| `signs_solved` | The solved arm angles (JSON), so rebuilding doesn't re-solve. Re-solve a sign after changing its targets. |
| `signs_letters` | The A–Z table actually used (handshapes, four arm orientations, J/Z motion). |
| `build_sign_clips` | Keys every clip as its own action and puts it on an NLA track named exactly like the clip (`MILK`, `FS_A`), for the bones and the face. Run it, then export. |

**Rules every clip follows:**
- **Word clips:** start and end in `READY` (both hands relaxed in front of the belly). The first key comes 8 frames in (11 for signs at face height), and the clip ends 7 frames after the last key.
- **Letter clips:** hold their handshape at the right shoulder, with the left hand in `READY`.
- **Brows and head tilt:** grammar brows and the question head tilt are not in clips; the player adds them. Clips carry mouthing (jaw, funnel, pucker, smile) and blinks only.
- **Bones:** key all 43 bones on every key, so a crossfade never blends toward the glTF bind pose (a T-pose).

**Export (tested):** the snippet in section 7 with `export_animation_mode='NLA_TRACKS'` gives one glTF animation per track name, with bone and morph channels merged. Unassign the active actions first. The first animation in the file must be a word clip, because the player builds its rest pose from the first non-`FS_` clip.

**Testing in three.js:** the clips were played through the real `SignPlayer` functions in headless Chrome with three.js r170. The harness measures wrist speed per frame and checks the wrists never drift toward the T-pose. Peak hand speed was about 3 m/s, at sign-to-sign crossfades.

---

## 1. What exists and where

| Thing | Where |
|---|---|
| Working file | `C:\Users\alvar\Documents\Pip_signing_model\signer.blend` (save often: it holds the scripts below) |
| Scene | `MeshyTPose` (the file also has `Sample`, `Scene`, `Signer` scenes; ignore them) |
| Mesh | `SK_Meshy` (body + five-finger hands + face shape keys) |
| Armature | `ARM_Meshy` (43 bones, hidden in the viewport; unhide to see it) |
| Original import | `SRC_MeshyTPose` (hidden, untouched) |
| Clips | NLA tracks on `ARM_Meshy` and on `SK_Meshy`'s shape keys, one per clip name; actions `<CLIP>` and `<CLIP>_face` (the old `AN_Meshy_YouWantMilk` actions are unused) |
| Scripts inside the .blend (Text Editor) | `anim_meshy_you_want_milk` (the example, regenerates both actions), `build_meshy` (rebuilds the whole rig), `meshy_rig_notes` |
| Exported model in the repo | `frontend/public/models/signer_glasses.glb` (branch `add-glasses-signer`) |
| App requirements | `handoff/3d-signer.md` (Part 1 lists the face shapes for each grammar face and emotion) |

**Do not run `build_meshy` unless you mean to rebuild the rig.** It deletes `SK_Meshy` and `ARM_Meshy` and recreates them; actions survive as data but get unassigned.

**World axes:** Blender Z is up. The character faces **−Y** (a camera at `(0, -4, z)` looking along +Y sees his front). His right side is **−X**. He is about 1.9 units tall; the head bone sits at z ≈ 0.47, the right shoulder at (−0.22, 0.02, 0.34). The rest pose is a **T-pose**.

---

## 2. Rig reference

All pose bones use **XYZ Euler** rotation. All values below are degrees.

**Bones (43):** `Hips`, `Spine`, `Chest`, `Neck`, `Head`; per side (`Left`/`Right`): `Shoulder`, `UpperArm`, `LowerArm`, `Hand`; per side and finger (`Index`, `Middle`, `Ring`, `Little`, `Thumb`): `Proximal`, `Intermediate`, `Distal`. Example: `RightIndexIntermediate`. Same names as `pip.glb` and `signer_tshirt.glb`.

**Axis conventions (verified on this rig):**

| Bone | Axis | Effect |
|---|---|---|
| Finger (any joint) | local X negative | curl toward the palm, same sign on both hands |
| Finger `Proximal` | local Z | spread sideways |
| Thumb `Proximal` (CMC) | local X negative | swing toward the fingers, in the palm plane |
| Thumb `Proximal` | local Z | opposition (Left negative / Right positive = toward the palm) |
| Thumb `Intermediate`, `Distal` | local X negative | bend |
| `UpperArm` | local X negative | lower the arm from the T-pose (both sides) |
| `LowerArm` | local Z | bend the elbow (Right +, Left −) |
| `LowerArm` | local Y | forearm twist |
| `Head`, `Chest` | local X positive | nod / lean forward |

Use the helpers in section 3 instead of setting these by hand; they hide the side-dependent signs.

**Face shape keys (20)** on `SK_Meshy`: `browInnerUp`, `browOuterUpLeft`, `browOuterUpRight`, `browDownLeft`, `browDownRight`, `eyeBlinkLeft`, `eyeBlinkRight`, `eyeSquintLeft`, `eyeSquintRight`, `eyeWideLeft`, `eyeWideRight`, `jawOpen`, `mouthFunnel`, `mouthPucker`, `mouthSmileLeft`, `mouthSmileRight`, `mouthFrownLeft`, `mouthFrownRight`, `cheekPuffLeft`, `cheekPuffRight`. Values 0–1.

Face limits: the eyelids and the mouth interior are small patches that sit collapsed at rest and only appear through the keys. The eyelids sit behind the glasses. Smile and frown bend a painted lip line, so keep them modest. There are no tongue, teeth or eye-gaze controls.

---

## 3. The helpers

This is the code the example animation uses, with one addition: `arm()` now also takes wrist `flex` and `dev` (needed for some letters). Put it at the top of each animation script.

```python
import bpy, math
scn = bpy.data.scenes["MeshyTPose"]; ob = bpy.data.objects["SK_Meshy"]; aob = bpy.data.objects["ARM_Meshy"]
P = aob.pose.bones; KB = ob.data.shape_keys.key_blocks; R = math.radians
SEG = ["Proximal", "Intermediate", "Distal"]; FN = ["Index", "Middle", "Ring", "Little"]

def key(f, *poses):
    """Set and keyframe bone rotations at frame f. Each pose is {bone_name: (x, y, z) degrees}."""
    for pose in poses:
        for b, e in pose.items():
            P[b].rotation_euler = [R(x) for x in e]; P[b].keyframe_insert("rotation_euler", frame=f)

def arm(side, down, fwd, elbow, twist=0, inward=0, flex=0, dev=0):
    """down: lower from T-pose; fwd: swing forward; elbow: bend; twist: forearm roll;
    inward: swing across the chest; flex/dev: wrist bend / side tilt."""
    s = 1 if side == "Right" else -1
    return {side + "UpperArm": (-down, s * fwd, s * inward),
            side + "LowerArm": (0, s * twist, s * elbow),
            side + "Hand": (-flex, 0, s * dev)}

def fingers(side, curls, spread=(0, 0, 0, 0), thumb=((0, 0, 0), 0)):
    """curls: (MCP, PIP, DIP) flexion for Index, Middle, Ring, Little.
    spread: degrees per finger, positive = away from the middle finger.
    thumb: ((CMC, MCP, IP) swing/bend toward the fingers, opposition toward the palm)."""
    L = 1 if side == "Left" else -1; d = {}
    for f_, cu, sp, sgn in zip(FN, curls, spread, (-1, -1, 1, 1)):
        for i, (sg, a) in enumerate(zip(SEG, cu)):
            d[side + f_ + sg] = (-a, 0, sp * sgn * L if i == 0 else 0)
    (c0, c1, c2), opp = thumb
    d[side + "ThumbProximal"] = (-c0, 0, -opp * L)
    d[side + "ThumbIntermediate"] = (-c1, 0, 0); d[side + "ThumbDistal"] = (-c2, 0, 0)
    return d

def face(f, **v):
    for n, val in v.items(): KB[n].value = val; KB[n].keyframe_insert("value", frame=f)
def mouth(f, jaw=0, funnel=0, pucker=0, smile=0):
    face(f, jawOpen=jaw, mouthFunnel=funnel, mouthPucker=pucker, mouthSmileLeft=smile, mouthSmileRight=smile)
def brows(f, v, wide=0):
    face(f, browInnerUp=v, browOuterUpLeft=v, browOuterUpRight=v, eyeWideLeft=wide, eyeWideRight=wide)
def blink(f):
    for ff, v in ((f - 2, 0), (f, 1), (f + 3, 0)): face(ff, eyeBlinkLeft=v, eyeBlinkRight=v)

FIST = (85, 95, 60); OPEN = (0, 0, 0)
RELAX = dict(curls=[(15, 20, 10)] * 4, thumb=((5, 5, 5), 10))
REST = lambda side: {**arm(side, 78, 0, 12), **fingers(side, **RELAX)}   # arm hanging at the side
body = lambda tilt, lean: {"Head": (tilt, 0, 0), "Chest": (lean, 0, 0)}
```

Fixed hand shapes used so far: `ONE = dict(curls=[OPEN, FIST, FIST, FIST], thumb=((30, 25, 45), 55))`, `C_HAND = dict(curls=[(30, 45, 30)] * 4, thumb=((0, 15, 25), 45))`, `S_HAND = dict(curls=[FIST] * 4, thumb=((30, 25, 45), 55))`.

---

## 4. How a sign was animated (the method)

1. **Write the animation as a script** saved as a Text block in the .blend (for example `anim_fs_a`). Start it with the helpers, then clear old animation if you are regenerating: `aob.animation_data_clear(); ob.data.shape_keys.animation_data_clear()`, zero every bone and every shape key.
2. **Key whole poses, not single bones.** At each frame call `key(frame, arm(...), fingers(...), REST("Left"), ...)`. Key every bone the pose touches on every key frame, or Blender will interpolate from somewhere unexpected.
3. **24 fps.** The example runs 100 frames: rest at 1, each sign 10–20 frames, a held final sign, back to rest by the end.
4. **Right hand is dominant.** The non-dominant hand goes to `REST("Left")` whenever it isn't part of the sign.
5. **Face goes in the same script** with `face`/`mouth`/`brows`/`blink`. A yes/no question uses brows up from the first sign through the held last sign, plus a forward head tilt (`body(10, 3)`). See `handoff/3d-signer.md` Part 1 for the other faces and emotions.
6. **Mouthing** is a few `mouth()` keys per word, at roughly a syllable every 6 frames, returning to closed between words.
7. **Name the actions** after keying (`aob.animation_data.action.name = ...`).
8. **Verify by rendering stills** (section 6) before exporting, and fix anything that looks wrong. Every pose in the example was checked from the front and from a three-quarter angle.

Open the existing `anim_meshy_you_want_milk` script to see all of this in one place.

---

## 5. Fingerspelling the alphabet

The app needs **one clip per letter** (`handoff/3d-signer.md` 1a). It plays them in sequence for `FS:WORD` glosses. The player looks for `FS_A` … `FS_Z` (WIRING.md section 5); those clips now exist.

### 5a. Where the hand goes

Fingerspelling is done with the right hand raised in front of the right shoulder. These arm poses were found by a search on this rig and checked by rendering (the measured finger and palm directions are in world space; −Y is toward the viewer):

| Orientation | `arm("Right", ...)` | Measured fingers / palm direction | Used for |
|---|---|---|---|
| `FWD` | `arm("Right", 70, 60, 105, twist=-90, inward=20)` | fingers (0.17, −0.23, 0.96) up; palm (0.01, −0.97, −0.23) toward viewer | most letters |
| `PROFILE` | `arm("Right", 75, 60, 100, twist=0, inward=20)` | fingers up; palm (0.99, 0.12, −0.12) toward the body midline | C, O |
| `SIDE` | `arm("Right", 55, 40, 100, twist=45, inward=40, flex=40, dev=-30)` | fingers (0.96, 0.04, 0.28) point to the signer's left; palm toward the signer | G, H |
| `DOWN` | `arm("Right", 55, 20, 80, twist=0, inward=40, flex=40, dev=-30)` | fingers (0.72, −0.47, −0.52) point down and inward | P, Q |

`DOWN` is the weakest of the four (fingers point diagonally, not straight down); improve it if P and Q look wrong to a signer.

### 5b. Handshapes (tested starting values)

Use as `fingers("Right", **LETTERS["A"])`. "Quality" is how the letter read in a test render on this rig, not a signer's judgement.

```python
TUCK = ((30, 25, 45), 55)   # thumb wrapped across the front of curled fingers
LETTERS = {
 "A": dict(curls=[FIST] * 4, thumb=((40, 0, 0), 0)),
 "B": dict(curls=[OPEN] * 4, thumb=((35, 30, 40), 35)),
 "C": dict(curls=[(30, 45, 30)] * 4, thumb=((0, 15, 25), 45)),
 "D": dict(curls=[OPEN, (55, 70, 40), (60, 70, 40), (65, 70, 40)], thumb=((25, 25, 25), 50)),
 "E": dict(curls=[(45, 100, 75)] * 4, thumb=((50, 30, 20), 75)),
 "F": dict(curls=[(45, 60, 40), OPEN, OPEN, OPEN], spread=(0, 4, 8, 14), thumb=((15, 25, 25), 45)),
 "G": dict(curls=[OPEN, FIST, FIST, FIST], thumb=((15, 0, 0), 0)),
 "H": dict(curls=[OPEN, OPEN, FIST, FIST], thumb=TUCK),
 "I": dict(curls=[FIST, FIST, FIST, OPEN], thumb=TUCK),
 "J": dict(curls=[FIST, FIST, FIST, OPEN], thumb=TUCK),
 "K": dict(curls=[OPEN, (45, 0, 0), FIST, FIST], spread=(6, 0, 0, 0), thumb=((10, 10, 0), 35)),
 "L": dict(curls=[OPEN, FIST, FIST, FIST], thumb=((-45, 0, 0), 0)),
 "M": dict(curls=[(70, 80, 40), (70, 80, 40), (70, 80, 40), FIST], thumb=((60, 10, 0), 75)),
 "N": dict(curls=[(70, 80, 40), (70, 80, 40), FIST, FIST], thumb=((45, 10, 0), 70)),
 "O": dict(curls=[(45, 60, 45)] * 4, thumb=((15, 25, 30), 60)),
 "P": dict(curls=[OPEN, (45, 0, 0), FIST, FIST], spread=(6, 0, 0, 0), thumb=((10, 10, 0), 35)),
 "Q": dict(curls=[OPEN, FIST, FIST, FIST], thumb=((15, 0, 0), 0)),
 "R": dict(curls=[OPEN, (12, 0, 0), FIST, FIST], spread=(-10, 16, 0, 0), thumb=TUCK),
 "S": dict(curls=[FIST] * 4, thumb=TUCK),
 "T": dict(curls=[(65, 85, 45), FIST, FIST, FIST], thumb=((25, 10, 0), 60)),
 "U": dict(curls=[OPEN, OPEN, FIST, FIST], thumb=TUCK),
 "V": dict(curls=[OPEN, OPEN, FIST, FIST], spread=(12, 10, 0, 0), thumb=TUCK),
 "W": dict(curls=[OPEN, OPEN, OPEN, FIST], spread=(12, 0, 10, 0), thumb=((40, 30, 45), 60)),
 "X": dict(curls=[(10, 90, 70), FIST, FIST, FIST], thumb=TUCK),
 "Y": dict(curls=[FIST, FIST, FIST, OPEN], spread=(0, 0, 0, 10), thumb=((-35, 0, 0), 0)),
 "Z": dict(curls=[OPEN, FIST, FIST, FIST], thumb=TUCK),
}
ORIENT = {k: "FWD" for k in LETTERS}; ORIENT.update(C="PROFILE", O="PROFILE", G="SIDE", H="SIDE", P="DOWN", Q="DOWN")
```

| Letter | Shape | Orientation | Quality in test |
|---|---|---|---|
| A | fist, thumb straight up beside the index | FWD | good |
| B | four fingers up together, thumb folded across the palm | FWD | good |
| C | curved hand like holding a cup | PROFILE | good |
| D | index up, other fingertips curve to meet the thumb | FWD | good |
| E | fingers bent down, tips resting on the tucked thumb | FWD | ok (fixed) |
| F | index and thumb touch in a circle, other three up and spread | FWD | good |
| G | index and thumb point sideways, parallel | SIDE | good |
| H | index and middle point sideways together | SIDE | good |
| I | little finger up, fist | FWD | good |
| J | I-hand, then the little finger draws a J | FWD | good, motion built |
| K | index up, middle angled forward, thumb between them | FWD | ok |
| L | index up, thumb out at a right angle | FWD | good |
| M | three fingers folded over the thumb | FWD | **rough**: looks like S; the thumb tip should peek out between ring and little |
| N | two fingers folded over the thumb | FWD | **rough**: looks like S; the thumb tip should peek out between middle and ring |
| O | all fingertips meet the thumb in a round O | PROFILE | good |
| P | K-hand pointing down | DOWN | ok (diagonal) |
| Q | G-hand pointing down | DOWN | ok (diagonal) |
| R | index and middle up and crossed | FWD | good (fixed) |
| S | fist, thumb across the front | FWD | good |
| T | thumb tucked between index and middle | FWD | **rough**: looks like S; the thumb tip should show between index and middle |
| U | index and middle up together | FWD | good |
| V | index and middle up and spread | FWD | good |
| W | index, middle, ring up and spread; thumb holds the little finger | FWD | good |
| X | index hooked, fist | FWD | good |
| Y | thumb and little finger out | FWD | good |
| Z | index draws a Z | FWD | good, motion built |

E and R are fixed; M, N and T are still rough. For M, N and T, the thumb needs more opposition and less CMC swing, so its tip pokes between the right fingers, and the fingers over it should curl a little less. For R, give the middle finger a small extra rotation on its local Z (beyond what `fingers()` sets) so it visibly crosses in front of the index.

### 5c. Clip structure (suggested, not yet tested in the app)

- **Static letters:** 12 frames. Key the letter pose at frames 1 and 12 (arm + fingers + `REST("Left")`). Don't go back to the hanging rest pose inside a clip; the player chains letters, and the hand stays raised between them.
- **J:** about 18 frames. Start with the I-hand at `FWD`. Over the clip, roll the forearm (`twist` from −90 toward 0) while lowering the hand slightly (`down` +5) and moving it inward (`inward` +10), so the little fingertip draws a J and the palm ends facing the signer.
- **Z:** about 20 frames. Z-hand at `FWD`; move the hand with `fwd`/`inward`/`down` changes to draw a Z (a stroke to the signer's left, a diagonal back down to the right, another stroke left) as seen by the signer, so it looks mirrored to the viewer.
- **Face:** neutral, maybe `mouthSmileLeft/Right` 0.2 for a friendly look, a blink every few seconds. Don't mouth letter names. When a whole word is fingerspelled, signers usually mouth the word, which belongs to the word-level player, not the letter clips. Confirm both with a signer.

Have a fluent ASL signer review the alphabet before it ships; these values come from standard handshape descriptions, not from a signer.

---

## 6. Verifying (do this for every letter)

Render stills with the fast Workbench engine and look at them. This is the function used throughout (it returns base64 JPEGs):

```python
import os, base64, tempfile, math
def snap(views, res=300):
    """views: list of (camera location, rotation in degrees, ortho scale). Returns base64 JPEG strings."""
    cam = bpy.data.objects["CAM_MeshyTPose"]; scn.camera = cam; cam.data.type = 'ORTHO'
    r = scn.render; old = (r.engine, r.resolution_x, r.resolution_y, r.filepath, r.image_settings.file_format)
    r.engine = 'BLENDER_WORKBENCH'; r.resolution_x = r.resolution_y = res
    r.image_settings.file_format = 'JPEG'
    scn.display.shading.light = 'STUDIO'; scn.display.shading.color_type = 'TEXTURE'
    out = []
    for i, (loc, rot, sc) in enumerate(views):
        cam.location = loc; cam.rotation_euler = [math.radians(a) for a in rot]; cam.data.ortho_scale = sc
        p = os.path.join(tempfile.gettempdir(), f"snap_{i}.jpg"); r.filepath = p
        bpy.ops.render.render(write_still=True)
        out.append(base64.b64encode(open(p, "rb").read()).decode()); os.remove(p)
    r.engine, r.resolution_x, r.resolution_y, r.filepath, r.image_settings.file_format = old
    return out
# hand close-up, front and three-quarter:
# c = P["RightMiddleProximal"].matrix.translation
# snap([((c.x, -4, c.z), (90, 0, 0), .2), ((c.x - 2.83, c.y - 2.83, c.z), (90, 0, -45), .2)])
```

Notes from doing this:
- **The MCP may refuse a large result.** Twenty-odd JPEGs exceed the size limit, and the result gets saved to a file instead; decode the base64 from that file and tile the images into one contact sheet. One sheet of all 26 letters at 200 px each worked well.
- **Check orientation with numbers, not just pictures.** After `bpy.context.view_layer.update()`, `M = P["RightHand"].matrix`: `M.to_3x3().col[1]` is the finger direction and `-M.to_3x3().col[2]` is the palm normal, in world space.
- **To pose freely without wrecking the clip,** detach the action first (`aob.animation_data.action = None`), pose and render, then zero the bones and reattach it. Otherwise the action overwrites your pose on the next frame change.
- Look at each letter from the front (how a viewer sees it) and from three-quarter (to catch fingers hidden behind others).

---

## 7. Exporting to the app

The single-clip export used for `signer_glasses.glb` (tested):

```python
scn.frame_set(1); aob.hide_set(False)
bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); aob.select_set(True)
bpy.context.view_layer.objects.active = aob
bpy.ops.export_scene.gltf(filepath=PATH, export_format='GLB', use_selection=True, use_active_scene=True,
    export_yup=True, export_skins=True, export_morph=True, export_animations=True,
    export_animation_mode='ACTIVE_ACTIONS', export_image_format='JPEG', export_jpeg_quality=88)
aob.hide_set(True)
```

- `use_active_scene=True` matters: without it the exporter pulled in the rigs from the other scenes in the file.
- JPEG textures keep the file around 5.8 MB; PNG made it about 30 MB.
- The exporter names the clip "Animation". It was renamed afterwards by editing the GLB's JSON chunk (`animations[0].name`), then rewriting the chunk lengths. A Blender-side way to get correct names is the NLA route below.
- After exporting, check the GLB: 43 joints in `skins[0].joints`, 20 names in `meshes[0].extras.targetNames`, and the clip duration (`max` of the animation sampler inputs).

**Several clips in one GLB (tested):** `build_sign_clips` puts each bone action and its face action on NLA tracks with the same name; export with `export_animation_mode='NLA_TRACKS'`. The result has one animation per clip, each driving the bones and (for word clips) the morph weights.

**Optional MP4 preview:** Workbench engine, 720×720, FFmpeg `MPEG4`/`H264`, perspective camera with a 35 mm lens at about `(-0.018, -1.22, 0.47)` looking along +Y frames him from the waist up with the hands large.
