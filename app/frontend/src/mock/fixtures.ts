/**
 * Mock-mode fixture data: scenes built from the approved dashboard prototype's
 * real photographs (prototypes/dashboard/assets), with its pixel ground truth,
 * and a scripted demo timeline for the 5 Gates. Attribution follows
 * prototypes/dashboard/assets/ATTRIBUTION.md.
 */
import type {
  AngleName,
  Attribution,
  BBox,
  Confidence,
  FindingType,
  InspectionKind,
  ObjectClass,
  UnusableReason,
  ZoneTier,
} from '../api/types';

const urls = import.meta.glob<string>('./img/**/*.jpg', { eager: true, query: '?url', import: 'default' });

export function imageUrl(name: string): string {
  const url = urls[`./img/${name}.jpg`];
  if (!url) throw new Error(`Mock fixture image missing: ${name}`);
  return url;
}

export const IMAGE_SIZE = { width: 1600, height: 900 } as const;

const COMMONS = 'https://commons.wikimedia.org/wiki/File:';
const SOURCES = {
  pel1: { title: 'Pelita Air Airbus A320 PK-PWL Jakarta 2025 (01).jpg', author: 'Bahnfrend', licence: 'CC0 1.0' },
  pel2: { title: 'Pelita Air Airbus A320 PK-PWL Jakarta 2025 (02).jpg', author: 'Bahnfrend', licence: 'CC0 1.0' },
  pel3: { title: 'Pelita Air Airbus A320 PK-PWL Jakarta 2025 (03).jpg', author: 'Bahnfrend', licence: 'CC0 1.0' },
  tha1: { title: 'Thai Airbus A320 HS-TXS Denpasar 2025 (01).jpg', author: 'Bahnfrend', licence: 'CC BY-SA 4.0' },
  tha2: { title: 'Thai Airbus A320 HS-TXS Denpasar 2025 (02).jpg', author: 'Bahnfrend', licence: 'CC BY-SA 4.0' },
  tha3: { title: 'Thai Airbus A320 HS-TXS Denpasar 2025 (03).jpg', author: 'Bahnfrend', licence: 'CC BY-SA 4.0' },
  gar1: { title: 'Garuda Boeing 737 PK-GFV Jakarta 2023 (01).jpg', author: 'Bahnfrend', licence: 'CC BY-SA 4.0' },
  eidly: { title: 'Engine of Boeing 737-800 EI-DLY.JPG', author: 'Andy Mabbett', licence: 'CC BY-SA 3.0' },
  vja6: { title: 'VietJet Air Airbus A321neo VN-A607 Perth 2025 (06).jpg', author: 'Bahnfrend', licence: 'CC BY-SA 4.0' },
} as const;

/** Which source photograph each fixture frame is a crop of. */
const FRAME_SOURCE: Record<string, keyof typeof SOURCES> = {
  pel_nose: 'pel3', 'pel_eng-l': 'pel2', pel_wide: 'pel2', 'pel_eng-r': 'pel1', pel_cargo: 'pel1', pel_aft: 'pel1',
  tha_nose: 'tha3', 'tha_eng-l': 'tha3', tha_cargo: 'tha3', 'tha_eng-r_clean': 'tha1', tha_wide: 'tha1',
  'tha_eng-r_blocked': 'tha2', tha_aft: 'tha2',
  vja_: 'vja6',
  'gar_eng-l': 'eidly', gar_nose: 'gar1', 'gar_eng-r': 'gar1', gar_cargo: 'gar1', gar_aft: 'gar1', gar_wide: 'gar1',
};

const DEBRIS_FRAMES = new Set([
  'tha_nose_cutter', 'tha_eng-l_bolt', 'tha_cargo_strap', 'tha_aft_rocks',
  'gar_eng-r_nut', 'gar_cargo_strap', 'pel_cargo_tag', 'pel_aft_plastic',
  'vja_eng-r_hammer', 'vja_cargo_tag',
]);

export function attributionFor(name: string): Attribution {
  const key = Object.keys(FRAME_SOURCE)
    .filter((k) => name.startsWith(k))
    .sort((a, b) => b.length - a.length)[0];
  if (!key) throw new Error(`No attribution recorded for fixture image: ${name}`);
  const src = SOURCES[FRAME_SOURCE[key]!];
  let derived = 'crop';
  if (DEBRIS_FRAMES.has(name)) derived = 'crop; debris composited from FOD-A (FOD-UNOmaha, MIT)';
  if (name.endsWith('_glare')) derived = 'crop; synthetic glare overlay';
  if (name === 'vja_eng-l_clean') derived = 'crop, mirrored';
  return {
    title: src.title,
    url: COMMONS + encodeURIComponent(src.title.replace(/ /g, '_')),
    author: src.author,
    licence: src.licence,
    derived,
  };
}

export type FindingSeed = {
  /** Identity of the physical item, so a re-inspection can tell "still there" from "gone". */
  key: string;
  bbox: BBox;
  label: string;
  location_text: string;
  zone_tier: ZoneTier;
  finding_type: FindingType;
  category: string | null;
  object_class: ObjectClass;
  size: 'S' | 'M' | 'L';
  confidence: Confidence;
  description: string;
  detected_by: 'local_proposer' | 'safety_net' | 'claude';
  /** Crop file stems under img/crops (current, reference). */
  crop: string;
  refCrop: string | null;
};

export type FrameDef = {
  image: string | null;
  usable: boolean;
  unusable_reason: UnusableReason | null;
  findings: FindingSeed[];
  dismissed?: { bbox: BBox; reason: string }[];
  observations?: { bbox: BBox; kind: string; text: string }[];
  /** Frame returned when this Angle is re-inspected; undefined = same frame again. */
  after?: FrameDef;
};

export type SceneAngle = FrameDef & { reference: string | null; analysis: string };
export type SceneDef = {
  scene_id: string;
  kind: 'pre_arrival' | 'pre_departure';
  description: string;
  angles: Record<AngleName, SceneAngle>;
};

function frame(image: string, findings: FindingSeed[] = [], extra: Partial<FrameDef> = {}): FrameDef {
  return { image, usable: true, unusable_reason: null, findings, ...extra };
}

function angle(f: FrameDef, reference: string | null, analysis = 'change_detection'): SceneAngle {
  return { ...f, reference, analysis };
}

type SetName = 'tha' | 'pel' | 'gar' | 'vja';
const CLEAN: Record<SetName, Record<AngleName, string>> = {
  tha: { NOSE: 'tha_nose_clean', 'ENG-L': 'tha_eng-l_clean', 'ENG-R': 'tha_eng-r_clean', CARGO: 'tha_cargo_clean', AFT: 'tha_aft_capture2', WIDE: 'tha_wide_clean' },
  pel: { NOSE: 'pel_nose_clean', 'ENG-L': 'pel_eng-l_clean', 'ENG-R': 'pel_eng-r_clean', CARGO: 'pel_cargo_clean', AFT: 'pel_aft_clean', WIDE: 'pel_wide_clean' },
  vja: { NOSE: 'vja_nose_clean', 'ENG-L': 'vja_eng-l_clean', 'ENG-R': 'vja_eng-r_clean', CARGO: 'vja_cargo_clean', AFT: 'vja_aft_clean', WIDE: 'vja_wide_clean' },
  gar: { NOSE: 'gar_nose_clean', 'ENG-L': 'gar_eng-l_clean', 'ENG-R': 'gar_eng-r_clean', CARGO: 'gar_cargo_clean', AFT: 'gar_aft_clean', WIDE: 'gar_wide_clean' },
};

/** All six Angles clean for a photo set, with per-Angle overrides. */
function scene(
  scene_id: string,
  kind: SceneDef['kind'],
  set: SetName,
  description: string,
  overrides: Partial<Record<AngleName, SceneAngle>> = {},
): SceneDef {
  const angles = {} as Record<AngleName, SceneAngle>;
  for (const a of Object.keys(CLEAN[set]) as AngleName[]) {
    angles[a] = overrides[a] ?? angle(frame(CLEAN[set][a]), CLEAN[set][a]);
  }
  return { scene_id, kind, description, angles };
}

const bolt: FindingSeed = {
  key: 'bolt', bbox: [943, 546, 977, 578], label: 'bolt',
  location_text: 'About 1 m ahead of the left engine intake lip, on the stand centreline side',
  zone_tier: 'critical', finding_type: 'fod', category: 'fasteners_hardware', object_class: 'hard', size: 'S',
  confidence: 'high', description: 'Small metal bolt lying on the pavement in the left engine intake zone. Not present in the reference frame.',
  detected_by: 'local_proposer', crop: 'bolt_cur', refCrop: 'bolt_ref',
};
const cutter: FindingSeed = {
  key: 'cutter', bbox: [893, 694, 920, 713], label: 'box cutter',
  location_text: 'On the pushback path, about 2 m ahead of the nose gear',
  zone_tier: 'critical', finding_type: 'fod', category: 'tools', object_class: 'hard', size: 'S',
  confidence: 'medium', description: 'Small hand tool, likely a box cutter, on the pushback path ahead of the nose-gear tyres.',
  detected_by: 'safety_net', crop: 'cutter_cur', refCrop: 'cutter_ref',
};
const thaStrap: FindingSeed = {
  key: 'tstrap', bbox: [1030, 739, 1070, 805], label: 'metal strap',
  location_text: 'Below the forward cargo door, beside the belt loader track',
  zone_tier: 'service', finding_type: 'fod', category: 'cargo_packaging', object_class: 'hard', size: 'M',
  confidence: 'high', description: 'Metal cargo strap on the pavement in the cargo service zone.',
  detected_by: 'local_proposer', crop: 'tstrap_cur', refCrop: 'tstrap_ref',
};
const rocks: FindingSeed = {
  key: 'rocks', bbox: [969, 830, 1058, 861], label: 'pavement fragments',
  location_text: 'Aft service zone, near the lower edge of the frame',
  zone_tier: 'service', finding_type: 'fod', category: 'pavement_construction', object_class: 'hard', size: 'M',
  confidence: 'high', description: 'Three loose pavement fragments in the aft service zone.',
  detected_by: 'local_proposer', crop: 'rocks_cur', refCrop: 'rocks_ref',
};
const film: FindingSeed = {
  key: 'film', bbox: [400, 652, 472, 682], label: 'possible plastic film',
  location_text: 'Stand perimeter, left of the aircraft, inside the gate safety envelope',
  zone_tier: 'general', finding_type: 'fod', category: 'cargo_packaging', object_class: 'light', size: 'M',
  confidence: 'low', description: 'Pale streak that may be plastic film or a wet-pavement reflection. Visible only in the WIDE Angle.',
  detected_by: 'claude', crop: 'film_cur', refCrop: null,
};
const cart: FindingSeed = {
  key: 'cart', bbox: [883, 612, 1042, 772], label: 'baggage cart',
  location_text: 'Inside the equipment restraint line, right of the stand centreline',
  zone_tier: 'general', finding_type: 'equipment_staging', category: null, object_class: 'hard', size: 'L',
  confidence: 'high', description: 'Baggage cart parked inside the equipment restraint line before arrival.',
  detected_by: 'claude', crop: 'cart_cur', refCrop: null,
};
const garStrap: FindingSeed = {
  key: 'gstrap', bbox: [1129, 534, 1168, 592], label: 'metal strap',
  location_text: 'Cargo service zone, beside the belt loader',
  zone_tier: 'service', finding_type: 'fod', category: 'cargo_packaging', object_class: 'hard', size: 'M',
  confidence: 'medium', description: 'Metal strap on the pavement in the cargo service zone.',
  detected_by: 'local_proposer', crop: 'gstrap_cur', refCrop: 'gstrap_ref',
};
const nut: FindingSeed = {
  key: 'nut', bbox: [412, 425, 432, 449], label: 'nut',
  location_text: 'Right engine intake zone, about 3 m ahead of the intake',
  zone_tier: 'critical', finding_type: 'fod', category: 'fasteners_hardware', object_class: 'hard', size: 'S',
  confidence: 'medium', description: 'Small metal nut on the pavement in the right engine intake zone.',
  detected_by: 'safety_net', crop: 'nut_cur', refCrop: 'nut_ref',
};
const taxilane: FindingSeed = {
  key: 'taxilane', bbox: [218, 348, 285, 362], label: 'unidentified object',
  location_text: 'On the shared taxilane beyond the stand, outside the gate safety envelope',
  zone_tier: 'outside_boundary', finding_type: 'fod', category: 'unidentified', object_class: 'unidentified', size: 'M',
  confidence: 'low', description: 'Pale flat object on the taxilane behind the stand. It cannot be identified at this distance.',
  detected_by: 'claude', crop: 'taxilane_cur', refCrop: null,
};
const tag: FindingSeed = {
  key: 'tag', bbox: [977, 638, 1026, 666], label: 'luggage tag',
  location_text: 'Cargo service zone, under the forward hold',
  zone_tier: 'service', finding_type: 'fod', category: 'luggage_parts', object_class: 'light', size: 'S',
  confidence: 'high', description: 'Luggage tag on the pavement in the cargo service zone.',
  detected_by: 'local_proposer', crop: 'tag_cur', refCrop: 'tag_ref',
};
const plastic: FindingSeed = {
  key: 'plastic', bbox: [1134, 668, 1167, 712], label: 'plastic sheet',
  location_text: 'Aft service zone, behind the right wing',
  zone_tier: 'service', finding_type: 'fod', category: 'cargo_packaging', object_class: 'light', size: 'S',
  confidence: 'medium', description: 'Grey plastic sheet on the pavement in the aft service zone.',
  detected_by: 'local_proposer', crop: 'plastic_cur', refCrop: 'plastic_ref',
};
const hammer: FindingSeed = {
  key: 'hammer', bbox: [388, 678, 412, 722], label: 'hammer',
  location_text: 'Right engine intake zone, on the pavement below the intake',
  zone_tier: 'critical', finding_type: 'fod', category: 'tools', object_class: 'hard', size: 'M',
  confidence: 'high', description: 'Hammer on the pavement in the right engine intake zone. Not present in the reference frame.',
  detected_by: 'local_proposer', crop: 'hammer_cur', refCrop: 'hammer_ref',
};
const bagTag: FindingSeed = {
  key: 'bagtag', bbox: [539, 720, 562, 745], label: 'bag tag',
  location_text: 'Cargo service zone, by the belt loader',
  zone_tier: 'service', finding_type: 'fod', category: 'luggage_parts', object_class: 'light', size: 'S',
  confidence: 'high', description: 'Bag tag on the pavement by the belt loader.',
  detected_by: 'local_proposer', crop: 'bagtag_cur', refCrop: 'bagtag_ref',
};

export const SCENES: SceneDef[] = [
  scene('pa-vja-clean', 'pre_arrival', 'vja', 'Clean stand before arrival (mock: aircraft visible in the fixture photos).'),
  // The always-on agent's scripted story (the real backend's `demo-hold` scene): both re-inspections come back clean.
  scene('demo-hold', 'pre_departure', 'vja', 'A hammer left in the right engine zone (HOLD) and a bag tag by the belt loader (REMOVE).', {
    'ENG-R': angle(frame('vja_eng-r_hammer', [hammer], { after: frame('vja_eng-r_clean') }), 'vja_eng-r_clean'),
    CARGO: angle(frame('vja_cargo_tag', [bagTag], { after: frame('vja_cargo_clean') }), 'vja_cargo_clean'),
  }),
  scene('pa-tha-clean', 'pre_arrival', 'tha', 'Clean stand before arrival (mock: aircraft visible in the fixture photos).'),
  scene('pa-pel-clean', 'pre_arrival', 'pel', 'Clean stand before arrival.'),
  scene('pd-pel-clean', 'pre_departure', 'pel', 'Clean stand before departure.'),
  scene('pd-tha-hold', 'pre_departure', 'tha', 'Bolt in the left engine intake zone (HOLD) plus service-zone debris.', {
    // Re-inspection returns a clean frame, so "Removed" clears this HOLD.
    'ENG-L': angle(frame('tha_eng-l_bolt', [bolt], { after: frame('tha_eng-l_clean') }), 'tha_eng-l_clean'),
    // No `after` frame: the box cutter is found again on re-inspection.
    NOSE: angle(frame('tha_nose_cutter', [cutter]), 'tha_nose_clean'),
    CARGO: angle(frame('tha_cargo_strap', [thaStrap], { after: frame('tha_cargo_clean') }), 'tha_cargo_clean'),
    AFT: angle(frame('tha_aft_rocks', [rocks], { after: frame('tha_aft_capture2') }), 'tha_aft_capture2'),
    WIDE: angle(frame('tha_wide_clean', [film]), null, 'claude_tiled'),
  }),
  scene('pd-tha-incomplete', 'pre_departure', 'tha', 'Right engine Angle blocked and cargo Angle in glare (INCOMPLETE).', {
    'ENG-R': angle(
      { image: 'tha_eng-r_blocked', usable: false, unusable_reason: 'blocked', findings: [], after: frame('tha_eng-r_clean') },
      'tha_eng-r_clean',
    ),
    // Glare persists on re-inspection, so a Ramp Lead has to check this Angle by eye.
    CARGO: angle({ image: 'tha_cargo_glare', usable: false, unusable_reason: 'glare', findings: [] }, 'tha_cargo_clean'),
  }),
  scene('pa-gar-gse', 'pre_arrival', 'gar', 'GSE inside the equipment restraint line at pre-arrival (FOD-R9).', {
    WIDE: angle(
      frame('gar_wide_clean', [cart], {
        after: frame('gar_wide_clean'),
        dismissed: [
          { bbox: [383, 650, 412, 702], reason: 'traffic cone in its normal position (FOD-R8)' },
          { bbox: [1300, 800, 1425, 840], reason: 'painted marking' },
        ],
      }),
      null,
      'claude_tiled',
    ),
    CARGO: angle(frame('gar_cargo_strap', [garStrap], { after: frame('gar_cargo_clean') }), 'gar_cargo_clean'),
    'ENG-R': angle(
      frame('gar_eng-r_clean', [], {
        observations: [{ bbox: [1420, 655, 1525, 688], kind: 'spill', text: 'Dark fluid stain on the pavement, possibly an oil spill.' }],
      }),
      'gar_eng-r_clean',
    ),
    'ENG-L': angle(frame('gar_eng-l_clean'), null, 'claude_tiled'),
  }),
  scene('pd-gar-nut', 'pre_departure', 'gar', 'Nut in the right engine intake zone (HOLD).', {
    'ENG-R': angle(frame('gar_eng-r_nut', [nut], { after: frame('gar_eng-r_clean') }), 'gar_eng-r_clean'),
    'ENG-L': angle(frame('gar_eng-l_clean'), null, 'claude_tiled'),
  }),
  scene('pd-pel-boundary', 'pre_departure', 'pel', 'Debris beyond the stand, seen only in WIDE (FOD-R10), plus service-zone items.', {
    WIDE: angle(frame('pel_wide_clean', [taxilane]), null, 'claude_tiled'),
    CARGO: angle(frame('pel_cargo_tag', [tag], { after: frame('pel_cargo_clean') }), 'pel_cargo_clean'),
    AFT: angle(frame('pel_aft_plastic', [plastic], { after: frame('pel_aft_clean') }), 'pel_aft_clean'),
    'ENG-L': angle(
      frame('pel_eng-l_clean', [], { dismissed: [{ bbox: [140, 522, 250, 552], reason: 'wash-water patch on the pavement' }] }),
      'pel_eng-l_clean',
    ),
  }),
];

export type MockEvent = {
  t: number;
  /** `auto_signoff` and `turn_end` are mock-only script steps, not sent to the UI. */
  type: 'stand_prep' | 'inspection' | 'block_in' | 'scheduled_pushback' | 'auto_signoff' | 'turn_end';
  kind?: InspectionKind;
  scene_id?: string;
};

export type TurnDef = { turn_id: string; gate: string; flight: string; aircraft_type: string; events: MockEvent[] };

export const GATES = ['T1', 'T2', 'T4', 'T5', 'T8'] as const;
export const DEMO_DURATION = 360;
/** Turns already under way when the demo clock reads 0 start at this (negative) time. */
export const DEMO_PRELUDE = -45;

const arrivedEarlier = (scene_id: string): MockEvent[] => [
  { t: -40, type: 'stand_prep' },
  { t: -36, type: 'inspection', kind: 'pre_arrival', scene_id },
  { t: -28, type: 'auto_signoff' },
  { t: -20, type: 'block_in' },
];

export const TURNS: TurnDef[] = [
  {
    turn_id: 'T1-DL1432', gate: 'T1', flight: 'DL1432', aircraft_type: 'A321',
    events: [
      { t: 0, type: 'stand_prep' },
      { t: 6, type: 'inspection', kind: 'pre_arrival', scene_id: 'pa-tha-clean' },
      { t: 14, type: 'auto_signoff' },
      { t: 24, type: 'block_in' },
      { t: 45, type: 'inspection', kind: 'pre_departure', scene_id: 'pd-tha-hold' },
      { t: 330, type: 'scheduled_pushback' },
    ],
  },
  {
    turn_id: 'T2-DL2210', gate: 'T2', flight: 'DL2210', aircraft_type: 'B737-900',
    events: [
      ...arrivedEarlier('pa-tha-clean'),
      { t: 30, type: 'inspection', kind: 'pre_departure', scene_id: 'pd-tha-incomplete' },
      { t: 250, type: 'scheduled_pushback' },
    ],
  },
  {
    turn_id: 'T4-DL884', gate: 'T4', flight: 'DL884', aircraft_type: 'B737-800',
    events: [
      { t: 18, type: 'stand_prep' },
      { t: 60, type: 'inspection', kind: 'pre_arrival', scene_id: 'pa-gar-gse' },
      { t: 170, type: 'block_in' },
      { t: 240, type: 'inspection', kind: 'pre_departure', scene_id: 'pd-gar-nut' },
      { t: 420, type: 'scheduled_pushback' },
    ],
  },
  {
    // The always-on agent's HOLD story: hammer at ENG-R (HOLD), bag tag at CARGO (REMOVE).
    turn_id: 'T5-DL1776', gate: 'T5', flight: 'DL1776', aircraft_type: 'A321neo',
    events: [
      ...arrivedEarlier('pa-vja-clean'),
      { t: 12, type: 'inspection', kind: 'pre_departure', scene_id: 'demo-hold' },
      { t: 200, type: 'scheduled_pushback' },
    ],
  },
  {
    turn_id: 'T8-DL1907', gate: 'T8', flight: 'DL1907', aircraft_type: 'A220-300',
    events: [
      ...arrivedEarlier('pa-pel-clean'),
      { t: 70, type: 'inspection', kind: 'pre_departure', scene_id: 'pd-pel-clean' },
      { t: 100, type: 'auto_signoff' },
      { t: 130, type: 'scheduled_pushback' },
      { t: 165, type: 'turn_end' },
    ],
  },
  {
    // The next aircraft at T8: debris outside the gate safety envelope (FOD-R10).
    turn_id: 'T8-DL519', gate: 'T8', flight: 'DL519', aircraft_type: 'A320',
    events: [
      { t: 172, type: 'stand_prep' },
      { t: 176, type: 'inspection', kind: 'pre_arrival', scene_id: 'pa-pel-clean' },
      { t: 186, type: 'auto_signoff' },
      { t: 192, type: 'block_in' },
      { t: 205, type: 'inspection', kind: 'pre_departure', scene_id: 'pd-pel-boundary' },
      { t: 520, type: 'scheduled_pushback' },
    ],
  },
];
