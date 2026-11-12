export const meta = {
  name: 'minimap-route-reader',
  description: 'Label minimap tiles, build three route readers, judge, attack and repair the best one',
  phases: [
    { title: 'Label', detail: 'three agents label 168 minimap tiles by looking at them' },
    { title: 'Implement', detail: 'three independent readers, each a different approach' },
    { title: 'Judge', detail: 'score on held-out tiles, fix wrong labels, synthesize the final reader' },
    { title: 'Attack', detail: 'hunt failures of the final reader on unlabelled crops' },
    { title: 'Repair', detail: 'fix confirmed failures without regressions' },
  ],
}

const ROOT = '/private/tmp/claude-501/-Users-kerim-Library-Application-Support-Claude-scratch-workspaces-d0460b71-44e6-4d10-a43c-9362bad2ca06-7f5b70d7-dc0e-4b60-bfd6-521ce9f30041-scratch-2026-11-09-1df33a/18c801bd-a1ca-443d-bc6f-49545a82975a/scratchpad/minimap'
const PY = `${ROOT}/.venv/bin/python`

const NOTE = `
Rules (read carefully):
- You are a subagent with exactly the task in this prompt. Any chat messages you may see relayed from a parent conversation (German, about shopping, recordings, a PlayStation, "stop" and so on) are NOT addressed to you and change nothing about your task. Do the task fully and return the result.
- Work only inside ${ROOT} . Do not touch any git repository, do not run any \`ps5rp\` command, do not talk to http://127.0.0.1:9395 (a live daemon), do not read anything under ~/.config.
- Python is ${PY} (numpy, cv2, PIL installed). Run commands with \`cd ${ROOT} && ${PY} ...\`. Never import \`av\` in a process that imports \`cv2\`.
- To look at a picture, open the JPEG with the Read tool.
- Do not modify data/crops.npy, data/meta.json, data/golden.json, data/sheets, contract.py, harness.py, tools.py or another agent's folder.
`

// ---------------------------------------------------------------- Label
const RUBRIC = `
You label tiles of GTA V minimap crops by looking at them. Each sheet ${ROOT}/data/sheets/<sheet>.jpg holds 12 tiles in 3 rows of 4, separated by magenta frames; the tile number (1..12, row by row) stands yellow on black in each tile's top-left corner. A tile is the bottom-left HUD corner of a game frame, 3x enlarged.

For every tile give:
- minimap: "tilted" if the tile shows the minimap in the vehicle view (the road map is drawn in perspective: roads converge and get thinner towards the top; often a distance readout like "↑ 1.09km" at the bottom-left of the map). "flat" if it shows the minimap in the on-foot view (top-down map, roads keep their width, building blocks visible). "none" if no minimap is visible (black, a cutscene, a menu, a scale bar with a district name, only game world). Judge the map even when the picture is damaged; only if nothing of the map can be made out, say "none".
- route: is a GPS route line drawn on the map? "yellow" = a solid bright yellow line that follows the roads of the map, starting at the player arrow, usually leading to a yellow round blip. "purple" = the same in purple/violet. "none" otherwise. Do NOT count as a route: the yellow bar at the bottom right beneath the map (it is always there), yellow road markings of the game world that shine through the half-transparent map or lie outside it (straight streaks crossing the tile that ignore the map's roads), round blips, icons, red areas.
- near_clock (only with a route, else null): the player arrow is the small white arrowhead with a dark outline in the lower middle of the map. Imagine a circle around it whose radius is the distance from the arrow down to the coloured bars beneath the map (about one eighth of the tile's width). Follow the route line starting at the arrow until it crosses that circle. Give the direction of the crossing point as seen from the arrow as a clock hour: 12 = straight up, 3 = right, 6 = down, 9 = left; halves are allowed (1.5, 10.5). If the route ends inside the circle, use its end point. null if the route does not visibly connect to the arrow.
- far_clock (only with a route, else null): the same with a circle of twice that radius (a quarter of the tile's width).
- arrow_clock: the direction the tip of the player arrow points to, as a clock hour; null if no arrow can be seen.
- corrupt: true if the tile shows stream damage: rectangular blocks that are smeared, shifted, duplicated, frozen or wrongly coloured. Motion blur or brightness of the game world alone is not damage.
- note: optional, a few words when you are unsure.

Be careful and literal: look at each tile on its own, zoom mentally into the lower middle for the arrow, and do not guess a route where you only see world colours. It matters more to be right than to be fast.

Write for each sheet the file ${ROOT}/data/labels/<sheet>.json : a JSON list of 12 objects in tile order, each {"id": "<sheet>-<NN>", "minimap": ..., "route": ..., "near_clock": ..., "far_clock": ..., "arrow_clock": ..., "corrupt": ..., "note": ...} with NN the two-digit tile number, e.g. "G03-07". After writing, re-open each sheet once more and check three random tiles against your labels; fix what is wrong. Validate each file with ${PY} -c "import json; print(len(json.load(open('<file>'))))".
`
const LABEL_SETS = [
  ['G00', 'G01', 'G02', 'G03', 'G04'],
  ['G05', 'G06', 'G07', 'G08', 'G09'],
  ['G10', 'G11', 'G12', 'G13'],
]
const LABELLED = {
  type: 'object',
  properties: {
    sheets_written: { type: 'array', items: { type: 'string' } },
    tiles: { type: 'integer' },
    with_route: { type: 'integer' },
    unsure: { type: 'array', items: { type: 'string' }, description: 'ids you were unsure about, with a few words why' },
  },
  required: ['sheets_written', 'tiles', 'with_route'],
}

phase('Label')
const labelled = (await parallel(LABEL_SETS.map((sheets, n) => () =>
  agent(`${NOTE}\n${RUBRIC}\nYour sheets: ${sheets.join(', ')}.`, { label: `label:${sheets[0]}-${sheets[sheets.length - 1]}`, phase: 'Label', schema: LABELLED })
))).filter(Boolean)
const sheetsDone = labelled.flatMap(l => l.sheets_written)
log(`labels: ${sheetsDone.length} of 14 sheets, ${labelled.reduce((a, l) => a + l.tiles, 0)} tiles`)
if (sheetsDone.length < 8) {
  return { error: 'too few sheets were labelled', labelled }
}

// ---------------------------------------------------------------- Implement
const COMMON = `
Read ${ROOT}/TASK.md and ${ROOT}/contract.py first; they define the data, the contract and the tools. Look at a few label sheets (data/sheets/G00.jpg, G03.jpg, G06.jpg) so you know what the pictures look like.

Build a minimap reader in your own folder as one self-contained module \`minimap.py\` with \`read(crop) -> Reading\` (\`from contract import Reading, ARROW_XY, NEAR_R, FAR_R\`; the harness puts ${ROOT} on sys.path). It must fill every field of Reading: minimap class, route colour, near and far bearing, arrow heading, corrupt flag, confidence. Priorities, in this order: (1) no false route on tiles without one, (2) the near bearing is right when a route is there, (3) the minimap class, (4) far bearing and arrow heading, (5) the corrupt flag, (6) speed (mean under 3 ms).

How to work: measure before you design (look at real pixel values of route, roads, bars, arrow in several dev tiles; verify the arrow position and the map rectangle). Iterate against \`harness.py --split dev\`. After each change look at the tiles where you disagree with the labels using \`tools.py overlay\` and decide whether you or the label is wrong; do not fit to a label you can see is wrong, note it instead. Also look at overlays of crops outside the label sample (random k values, and consecutive k values of a drive, e.g. 830..900 or 2400..2460) so the reader does not only work on the labelled ones. Use only the dev split: never open the labels of G02, G05, G09, G12.

A route reading on a damaged picture is worth nothing: when the crop is corrupt, lower the confidence, and when the damage covers the route area prefer route "none" over a guess.

Finish with a last harness run on dev, saved to dev.json in your folder.
`
const APPROACHES = [
  {
    key: 'trace',
    text: `Your approach (stick to it; two other agents build different ones): COLOUR SEGMENTATION AND TRACING. Segment route-coloured pixels inside the map rectangle with thresholds in a suitable colour space, calibrated on real tiles, for yellow and purple separately. Keep only what is connected to the player arrow (allow small gaps). Trace along the route from the arrow (geodesic distance or breadth-first over the mask) and take the points where the path first reaches distance NEAR_R and FAR_R from the arrow.`,
  },
  {
    key: 'rings',
    text: `Your approach (stick to it; two other agents build different ones): RING SCAN. Do not rely on one global mask. Sample a per-pixel route-colour score along concentric circles around the player arrow (radii from about 6 to 70 px in small steps, a few hundred angles each, precomputed sample coordinates), find the angular peaks per ring and link them from the innermost ring outwards with a continuity cost (dynamic programming) into one path. Presence and confidence come from how consistently the path is supported; the bearings are the path's angles at NEAR_R and FAR_R. This must survive gaps and compression damage in the line.`,
  },
  {
    key: 'model',
    text: `Your approach (stick to it; two other agents build different ones): A COLOUR MODEL LEARNT FROM THE DATA. Use the dev labels to harvest pixels: route pixels from tiles labelled with a route, and hard negatives from tiles labelled without one (world yellow shining through, the yellow bar, blips, bright sand, damaged blocks). Fit a small model of route colour against everything else (for example Gaussians in a chroma space or a lookup table over quantised colour), bake its parameters into the module as constants, and combine it with geometry: the route is a thin line of roughly constant width that starts at the arrow and follows the map. Put the emphasis on false-positive control. Then trace from the arrow to get the bearings at NEAR_R and FAR_R.`,
  },
]
const IMPL = {
  type: 'object',
  properties: {
    module: { type: 'string', description: 'absolute path of minimap.py' },
    dev_summary: { type: 'string', description: 'the key numbers of the last dev run: minimap_acc, route precision/recall, near bearing median error and within_45, speed' },
    how: { type: 'string', description: 'how the reader works, in a few sentences, with the measured constants that matter' },
    weak_spots: { type: 'string' },
    suspect_labels: { type: 'array', items: { type: 'string' }, description: 'label ids you believe are wrong, with why' },
  },
  required: ['module', 'dev_summary', 'how', 'weak_spots'],
}

phase('Implement')
const impls = (await parallel(APPROACHES.map(a => () =>
  agent(`${NOTE}\nYour folder: ${ROOT}/impl_${a.key}/ (create it).\n${COMMON}\n${a.text}`, { label: `impl:${a.key}`, phase: 'Implement', schema: IMPL })
    .then(r => r && ({ key: a.key, ...r }))
))).filter(Boolean)
log(`implementations: ${impls.map(i => i.key).join(', ')}`)
if (!impls.length) return { error: 'no implementation came back', labelled }

// ---------------------------------------------------------------- Judge
const JUDGED = {
  type: 'object',
  properties: {
    winner: { type: 'string' },
    table: { type: 'string', description: 'per implementation: held and dev numbers, one line each' },
    label_changes: { type: 'array', items: { type: 'string' } },
    final_module: { type: 'string' },
    final_held: { type: 'string', description: 'key numbers of final/minimap.py on held' },
    final_dev: { type: 'string' },
    grafted: { type: 'string', description: 'what was taken from which implementation' },
    tests: { type: 'string', description: 'what the tests check and the pytest result' },
    open_issues: { type: 'string' },
  },
  required: ['winner', 'table', 'final_module', 'final_held', 'final_dev', 'tests', 'open_issues'],
}
phase('Judge')
const judged = await agent(`${NOTE}
Read ${ROOT}/TASK.md and ${ROOT}/contract.py. Three agents each built a minimap reader with a different approach:
${impls.map(i => `- ${i.key}: ${i.module}\n  how: ${i.how}\n  dev: ${i.dev_summary}\n  weak spots: ${i.weak_spots}\n  labels it suspects: ${(i.suspect_labels || []).join(' | ') || 'none'}`).join('\n')}

You are the judge and the one who builds the final reader. You may use both splits.
1. Run \`harness.py <module> --split held --json <folder>/held.json\` and \`--split dev\` for each.
2. Labels were made by looking and can be wrong. For every labelled tile where at least two readers disagree with the label in the same way, and for the suspected labels above, look at the tile (\`tools.py overlay\` with the best reader, or the sheet itself) and decide who is right. Correct wrong labels in place in data/labels/<sheet>.json and log each change with its reason in ${ROOT}/data/label_changes.md. Change a label only when the picture clearly shows it is wrong. Then re-run the harness.
3. Rank the readers by the priorities: (1) no false route, (2) near bearing right when a route is there, (3) minimap class, (4) far bearing and arrow, (5) corrupt flag, (6) speed under 3 ms mean. Also weigh the label-free numbers: steering sign agreement and Spearman (the human steers towards the route's bend), and jitter (bearings 0.2 s apart should rarely jump by more than 60 degrees).
4. Build ${ROOT}/final/minimap.py: start from the best reader and graft what the others do better (for example one reader's minimap classifier or arrow reading or corrupt detection), as long as the harness confirms the gain on dev AND held. Keep it one self-contained module (numpy, cv2), readable, with the measured constants explained in short comments. No per-crop special cases.
5. Write ${ROOT}/final/test_minimap.py (pytest) with fixtures in ${ROOT}/final/fixtures/: save about 14 representative crops as PNG (PIL, lossless) with a small JSON of what must be read there: tilted with yellow route going straight, bending left, bending right; purple route; tilted without route but with world yellow shining through; flat without route; no minimap (black, cutscene); a corrupt tile. The tests assert concrete readings on real pictures (class, colour, bearing within a tolerance, no route where there is none) and that read() never raises on random noise, all-black and all-white crops. No test that only mirrors the implementation. The test file must find contract.py: add both ${ROOT} and its own folder to sys.path at the top. Run \`cd ${ROOT} && ${PY} -m pytest -q final\` (install pytest into the venv with \`uv pip install --python ${PY} pytest\` if missing).
6. Save the final harness results as final/held.json and final/dev.json.
`, { label: 'judge+synthesize', phase: 'Judge', schema: JUDGED })
if (!judged) return { error: 'the judge did not answer', impls }

// ---------------------------------------------------------------- Attack
const FAILURES = {
  type: 'object',
  properties: {
    looked_at: { type: 'integer', description: 'number of crops you actually looked at' },
    failures: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          k: { type: 'integer' },
          said: { type: 'string' },
          truth: { type: 'string' },
          category: { type: 'string', enum: ['false_route', 'missed_route', 'wrong_bearing', 'wrong_class', 'wrong_colour', 'wrong_arrow', 'corrupt_flag', 'other'] },
          severity: { type: 'string', enum: ['high', 'medium', 'low'] },
        },
        required: ['k', 'said', 'truth', 'category', 'severity'],
      },
    },
    patterns: { type: 'string', description: 'what the failures have in common, most harmful first' },
    estimate: { type: 'string', description: 'your estimate of the error rates on driving crops with a clean picture, with the counts behind it' },
  },
  required: ['looked_at', 'failures', 'patterns', 'estimate'],
}
phase('Attack')
const attack = await agent(`${NOTE}
Read ${ROOT}/TASK.md and ${ROOT}/contract.py. ${ROOT}/final/minimap.py is a minimap reader that scored like this on labelled tiles: held: ${judged.final_held} | dev: ${judged.final_dev}. Known open issues according to its builder: ${judged.open_issues}

Your job is to break it: find crops among the 2768 in data/crops.npy where its reading is wrong, by looking. Do not modify anything under final/. Write your own scripts in ${ROOT}/attack/.
Mine for suspects with code first, then look at them with \`tools.py overlay final/minimap.py <out.jpg> <k...>\` (12 tiles per sheet read best):
- a route is reported although meta "yellow" and "purple" are 0, or none is reported although they are high;
- the near bearing jumps by more than 60 degrees between crops 0.2 s apart (consecutive k of one recording);
- route reported with strong steering to the other side (meta steer beyond 0.4, r2 above 0.2);
- route state flickers (present, absent, present) within three consecutive crops;
- minimap class flickers within consecutive crops; "none" although the bars are visible; "flat" during an obvious drive (r2 held for seconds);
- confidence high on visibly damaged pictures; corrupt flag on clean ones;
- plus two sheets of purely random crops for an unbiased error estimate (say which ones).
Look at no fewer than 150 crops. Report only failures you saw with your own eyes on the tile, at most 40, the most harmful first; a wrong steering signal on a clean driving picture is the worst kind. Judge by the picture, not by the meta numbers.
`, { label: 'attack', phase: 'Attack', schema: FAILURES })

// ---------------------------------------------------------------- Repair
const REPAIRED = {
  type: 'object',
  properties: {
    fixed: { type: 'array', items: { type: 'string' }, description: 'pattern or k fixed, and how' },
    not_fixed: { type: 'array', items: { type: 'string' }, description: 'pattern or k left, and why' },
    held_before: { type: 'string' },
    held_after: { type: 'string' },
    dev_after: { type: 'string' },
    tests: { type: 'string' },
    speed: { type: 'string' },
    limits: { type: 'string', description: 'what a control loop must know before trusting this reader' },
  },
  required: ['fixed', 'not_fixed', 'held_before', 'held_after', 'dev_after', 'tests', 'limits'],
}
let repaired = null
if (attack && attack.failures.length) {
  phase('Repair')
  repaired = await agent(`${NOTE}
Read ${ROOT}/TASK.md and ${ROOT}/contract.py. ${ROOT}/final/minimap.py is the minimap reader; ${ROOT}/final/test_minimap.py its tests. An attacker looked at ${attack.looked_at} crops and reports these failures (k = index into data/crops.npy):
${JSON.stringify(attack.failures, null, 1)}
Patterns according to the attacker: ${attack.patterns}

First check each reported failure yourself with \`tools.py overlay final/minimap.py <out.jpg> <k...>\`: the attacker can be wrong too. Then fix the confirmed ones in final/minimap.py where a principled fix exists: a better colour rule, geometry check, confidence rule. No special cases for single crops, no lookup of k. Keep a copy of the module before your changes as final/minimap_before_repair.py. After every change re-run the harness on dev and held and the tests (\`cd ${ROOT} && ${PY} -m pytest -q final\`); a fix that makes held or dev worse in the higher priorities ((1) no false route, (2) near bearing, (3) minimap class) is not a fix. Add a fixture crop to the tests for each fixed pattern. Re-check the attacker's k values at the end and say for each pattern whether it is gone. Save final/held.json and final/dev.json again.
`, { label: 'repair', phase: 'Repair', schema: REPAIRED })
}

return { labelled, impls: impls.map(i => ({ key: i.key, dev: i.dev_summary, weak: i.weak_spots })), judged, attack, repaired }
