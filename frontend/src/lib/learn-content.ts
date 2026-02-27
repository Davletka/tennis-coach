/**
 * Learning track — sport-agnostic content registry.
 *
 * Activity IDs match ActivityConfig.id keys ("tennis", "gym", …).
 * Lesson IDs are dot-separated paths used as DB keys:
 *   tennis.forehand.eastern.flat-forehand
 *   gym.chest.barbell.bench-press
 *   gym.plans.ppl.push-day-a   (plan day progress)
 */

// ---------------------------------------------------------------------------
// Content schema
// ---------------------------------------------------------------------------

export interface ContentBlock {
  type: "text" | "key-points" | "tip" | "svg" | "section-header" | "3d-scene";
  text?: string;       // for text | tip | section-header
  points?: string[];   // for key-points
  svg?: string;        // raw SVG string (rendered via dangerouslySetInnerHTML)
  caption?: string;    // optional caption shown below svg or 3d-scene
  sceneId?: string;    // which 3D scene to render (for type "3d-scene")
}

export interface Lesson {
  id: string;
  title: string;
  description: string;
  difficulty: "beginner" | "intermediate" | "advanced";
  content: ContentBlock[];
}

export interface Variant {
  id: string;
  title: string;
  subtitle: string;
  svg?: string; // illustrates the variant (grip, equipment, etc.)
  lessons: Lesson[];
}

export interface VariantGroup {
  prompt: string; // e.g. "Choose your grip"
  variants: Variant[];
}

export interface PlanExercise {
  lessonRef: string; // full dot-path "gym.chest.barbell.bench-press"
  sets: string;      // e.g. "4 × 8–10"
  rest?: string;     // e.g. "90 s"
  notes?: string;
}

export interface PlanDay {
  id: string;
  title: string;
  focus: string; // e.g. "Push — chest, shoulders, triceps"
  exercises: PlanExercise[];
}

export interface WorkoutPlan {
  id: string;
  title: string;
  description: string;
  level: "beginner" | "intermediate" | "advanced";
  frequency: string; // e.g. "6 days / week"
  days: PlanDay[];
}

export type LearnModule =
  | {
      type: "variant-select";
      id: string;
      title: string;
      description: string;
      icon: string;
      variantGroup: VariantGroup;
    }
  | {
      type: "lessons";
      id: string;
      title: string;
      description: string;
      icon: string;
      lessons: Lesson[];
    }
  | {
      type: "plans";
      id: string;
      title: string;
      description: string;
      icon: string;
      plans: WorkoutPlan[];
    };

export interface LearnActivity {
  id: string; // matches ActivityConfig.id
  title: string;
  description: string;
  icon: string; // emoji used in module grid
  color: string; // Tailwind bg color class for the sport card
  modules: LearnModule[];
}

// ---------------------------------------------------------------------------
// SVG helpers — shared colour tokens
// ---------------------------------------------------------------------------

const C = {
  bg: "#f8fafc",
  surface: "#e2e8f0",
  outline: "#334155",
  accent: "#f97316",
  blue: "#3b82f6",
  green: "#22c55e",
  text: "#1e293b",
  muted: "#64748b",
  white: "#ffffff",
};

// ---------------------------------------------------------------------------
// Tennis — Grip SVGs (octagonal handle viewed from butt end)
// Each SVG highlights the bevel where the index-finger knuckle rests.
//
// Octagon vertices (r=60, center=200,140, flat-top):
//   v0(256,117)  v1(223,85)  v2(177,85)  v3(145,117)
//   v4(145,163)  v5(177,196) v6(223,196) v7(256,163)
//
// Bevels (face → vertices):
//   B1(NE): v0→v1   B2(Top): v1→v2   B3(NW): v2→v3
//   B4(W):  v3→v4   B5(SW):  v4→v5   B6(Bot): v5→v6
//   B7(SE): v6→v7   B8(E):   v7→v0
// ---------------------------------------------------------------------------

const OCT_PATH = "M 256,117 L 223,85 L 177,85 L 145,117 L 145,163 L 177,196 L 223,196 L 256,163 Z";

function gripSvg(
  highlightLine: string,   // <line .../> string for the highlighted bevel
  knuckleX: number,
  knuckleY: number,
  gripName: string,
  knuckleLabel: string,
): string {
  return `<svg viewBox="0 0 400 260" xmlns="http://www.w3.org/2000/svg">
  <rect width="400" height="260" fill="${C.bg}" rx="12"/>
  <text x="200" y="26" font-family="system-ui,sans-serif" font-size="12" font-weight="600" fill="${C.muted}" text-anchor="middle" letter-spacing="1">HANDLE END-ON VIEW</text>
  <path d="${OCT_PATH}" fill="${C.surface}" stroke="${C.outline}" stroke-width="2.5"/>
  ${highlightLine}
  <circle cx="${knuckleX}" cy="${knuckleY}" r="10" fill="${C.accent}" stroke="${C.white}" stroke-width="2.5"/>
  <text x="${knuckleX + 18}" y="${knuckleY + 4}" font-family="system-ui,sans-serif" font-size="10" fill="${C.accent}" font-weight="700">knuckle</text>
  <text x="200" y="228" font-family="system-ui,sans-serif" font-size="15" font-weight="700" fill="${C.text}" text-anchor="middle">${gripName}</text>
  <text x="200" y="248" font-family="system-ui,sans-serif" font-size="11" fill="${C.muted}" text-anchor="middle">${knuckleLabel}</text>
</svg>`;
}

const CONTINENTAL_SVG = gripSvg(
  `<line x1="223" y1="85" x2="177" y2="85" stroke="${C.accent}" stroke-width="9" stroke-linecap="round"/>`,
  200, 85,
  "Continental Grip",
  "Index knuckle on top-flat bevel (B2) — like holding a hammer",
);

const EASTERN_SVG = gripSvg(
  `<line x1="256" y1="117" x2="223" y2="85" stroke="${C.accent}" stroke-width="9" stroke-linecap="round"/>`,
  240, 101,
  "Eastern Forehand Grip",
  "Index knuckle on top-right bevel (B1) — natural handshake position",
);

const WESTERN_SVG = gripSvg(
  `<line x1="145" y1="163" x2="177" y2="196" stroke="${C.accent}" stroke-width="9" stroke-linecap="round"/>`,
  160, 180,
  "Western Grip",
  "Index knuckle on bottom-left bevel (B5) — palm under the handle",
);

const SEMI_WESTERN_SVG = gripSvg(
  `<line x1="145" y1="117" x2="145" y2="163" stroke="${C.accent}" stroke-width="9" stroke-linecap="round"/>`,
  145, 140,
  "Semi-Western Grip",
  "Index knuckle on left-flat bevel (B4) — popular modern grip",
);

// ---------------------------------------------------------------------------
// Tennis — Shot trajectory SVGs (side view of half-court)
// ---------------------------------------------------------------------------

function shotSvg(title: string, ballPath: string, annotations: string): string {
  return `<svg viewBox="0 0 400 220" xmlns="http://www.w3.org/2000/svg">
  <rect width="400" height="220" fill="${C.bg}" rx="12"/>
  <!-- Court surface -->
  <rect x="20" y="160" width="360" height="8" fill="#6ee7b7" stroke="${C.outline}" stroke-width="1"/>
  <!-- Baseline (left) -->
  <line x1="20" y1="110" x2="20" y2="168" stroke="${C.outline}" stroke-width="2"/>
  <!-- Net -->
  <rect x="195" y="128" width="10" height="32" fill="${C.outline}" rx="2"/>
  <line x1="195" y1="128" x2="205" y2="128" stroke="${C.outline}" stroke-width="3"/>
  <!-- Opponent baseline (right) -->
  <line x1="380" y1="110" x2="380" y2="168" stroke="${C.outline}" stroke-width="2"/>
  <!-- Ball path -->
  ${ballPath}
  <!-- Annotations -->
  ${annotations}
  <!-- Title -->
  <text x="200" y="200" font-family="system-ui,sans-serif" font-size="14" font-weight="700" fill="${C.text}" text-anchor="middle">${title}</text>
</svg>`;
}

const FLAT_FOREHAND_SVG = shotSvg(
  "Flat Forehand — Low arc, high pace",
  `<path d="M 30,148 Q 200,100 370,148" fill="none" stroke="${C.blue}" stroke-width="2.5" stroke-dasharray="6,3"/>
   <circle cx="30" cy="148" r="7" fill="${C.accent}"/>
   <circle cx="370" cy="148" r="7" fill="${C.blue}" opacity="0.6"/>`,
  `<text x="200" y="115" font-family="system-ui,sans-serif" font-size="10" fill="${C.blue}" text-anchor="middle">low arc</text>`,
);

const TOPSPIN_SVG = shotSvg(
  "Topspin Forehand — High arc, heavy spin",
  `<path d="M 30,148 Q 180,60 370,138" fill="none" stroke="${C.green}" stroke-width="2.5" stroke-dasharray="6,3"/>
   <circle cx="30" cy="148" r="7" fill="${C.accent}"/>
   <circle cx="370" cy="138" r="7" fill="${C.green}" opacity="0.6"/>
   <!-- Spin arrows -->
   <path d="M 200,100 A 12,12 0 1,1 212,110" fill="none" stroke="${C.green}" stroke-width="2" marker-end="url(#spin)"/>
   <defs><marker id="spin" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="${C.green}"/></marker></defs>`,
  `<text x="190" y="78" font-family="system-ui,sans-serif" font-size="10" fill="${C.green}" text-anchor="middle">high arc + topspin</text>`,
);

const LOB_SVG = shotSvg(
  "Lob — Very high arc over opponent",
  `<path d="M 30,148 Q 160,30 370,140" fill="none" stroke="#a855f7" stroke-width="2.5" stroke-dasharray="6,3"/>
   <circle cx="30" cy="148" r="7" fill="${C.accent}"/>
   <circle cx="370" cy="140" r="7" fill="#a855f7" opacity="0.6"/>`,
  `<text x="160" y="48" font-family="system-ui,sans-serif" font-size="10" fill="#a855f7" text-anchor="middle">clears opponent at net</text>`,
);

const INSIDE_OUT_SVG = shotSvg(
  "Inside-Out Forehand — Cross-court from backhand side",
  `<path d="M 30,148 Q 150,95 370,148" fill="none" stroke="${C.accent}" stroke-width="2.5" stroke-dasharray="6,3"/>
   <!-- Footwork indicator: player runs around backhand -->
   <circle cx="45" cy="158" r="6" fill="${C.muted}" opacity="0.5"/>
   <path d="M 55,155 Q 70,148 80,152" fill="none" stroke="${C.muted}" stroke-width="1.5" stroke-dasharray="3,2"/>`,
  `<text x="50" y="148" font-family="system-ui,sans-serif" font-size="9" fill="${C.muted}">run around BH</text>
   <text x="210" y="108" font-family="system-ui,sans-serif" font-size="10" fill="${C.accent}" text-anchor="middle">diagonal to opponent's BH</text>`,
);

// Body-movement SVGs — full stick-figure diagrams showing wrist, shoulder & body positions


const DROP_SHOT_SVG = `<svg viewBox="0 0 400 290" xmlns="http://www.w3.org/2000/svg">
  <rect width="400" height="290" fill="${C.bg}" rx="12"/>
  <!-- Court surface -->
  <rect x="20" y="232" width="360" height="8" fill="#6ee7b7" stroke="${C.outline}" stroke-width="1" opacity="0.7"/>
  <line x1="20" y1="240" x2="380" y2="240" stroke="${C.outline}" stroke-width="2"/>
  <!-- Net -->
  <rect x="190" y="202" width="8" height="30" fill="${C.outline}" rx="2" opacity="0.6"/>
  <line x1="188" y1="202" x2="200" y2="202" stroke="${C.outline}" stroke-width="2.5"/>
  <text x="194" y="198" font-family="system-ui,sans-serif" font-size="8" fill="${C.muted}" text-anchor="middle">net</text>
  <!-- Head -->
  <circle cx="165" cy="62" r="15" fill="#fde8d8" stroke="${C.outline}" stroke-width="2"/>
  <!-- Torso (upright — drop shot needs less body lean) -->
  <line x1="165" y1="77" x2="167" y2="150" stroke="${C.outline}" stroke-width="5" stroke-linecap="round"/>
  <!-- Shoulder line (modest rotation — disguise prep looks normal) -->
  <line x1="148" y1="97" x2="193" y2="92" stroke="${C.outline}" stroke-width="3.5" stroke-linecap="round"/>
  <circle cx="148" cy="97" r="5" fill="${C.muted}" opacity="0.6"/>
  <circle cx="193" cy="92" r="5" fill="${C.muted}" opacity="0.6"/>
  <!-- Hips -->
  <line x1="157" y1="150" x2="188" y2="150" stroke="${C.outline}" stroke-width="4" stroke-linecap="round"/>
  <!-- Left leg -->
  <line x1="160" y1="150" x2="145" y2="197" stroke="${C.outline}" stroke-width="4" stroke-linecap="round"/>
  <line x1="145" y1="197" x2="133" y2="240" stroke="${C.outline}" stroke-width="4" stroke-linecap="round"/>
  <!-- Right leg -->
  <line x1="185" y1="150" x2="202" y2="192" stroke="${C.outline}" stroke-width="4" stroke-linecap="round"/>
  <line x1="202" y1="192" x2="212" y2="240" stroke="${C.outline}" stroke-width="4" stroke-linecap="round"/>
  <!-- Left arm (forward, relaxed guidance) -->
  <line x1="148" y1="97" x2="126" y2="114" stroke="${C.outline}" stroke-width="3" stroke-linecap="round"/>
  <line x1="126" y1="114" x2="110" y2="110" stroke="${C.outline}" stroke-width="3" stroke-linecap="round"/>
  <!-- Right upper arm -->
  <line x1="193" y1="92" x2="234" y2="100" stroke="${C.outline}" stroke-width="3.5" stroke-linecap="round"/>
  <!-- Right forearm — contact at waist height, arm relaxed (not locked out) -->
  <line x1="234" y1="100" x2="262" y2="126" stroke="${C.outline}" stroke-width="3.5" stroke-linecap="round"/>
  <!-- Wrist (soft wrist — highlighted) -->
  <circle cx="262" cy="126" r="8" fill="${C.accent}" stroke="${C.white}" stroke-width="2.5"/>
  <text x="274" y="120" font-family="system-ui,sans-serif" font-size="9" fill="${C.accent}" font-weight="700">soft wrist</text>
  <!-- Racket handle -->
  <line x1="262" y1="126" x2="286" y2="150" stroke="#64748b" stroke-width="3.5" stroke-linecap="round"/>
  <!-- Racket head — open face (more horizontal, tilted skyward) -->
  <ellipse cx="300" cy="164" rx="17" ry="11" fill="none" stroke="${C.outline}" stroke-width="2" transform="rotate(15 300 164)"/>
  <line x1="285" y1="160" x2="315" y2="168" stroke="${C.outline}" stroke-width="1" opacity="0.35"/>
  <line x1="300" y1="153" x2="300" y2="175" stroke="${C.outline}" stroke-width="1" opacity="0.35"/>
  <!-- Open face annotation -->
  <text x="320" y="152" font-family="system-ui,sans-serif" font-size="9" fill="${C.blue}" font-weight="600">open</text>
  <text x="320" y="164" font-family="system-ui,sans-serif" font-size="9" fill="${C.blue}" font-weight="600">face</text>
  <defs>
    <marker id="arr-ds-face" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="${C.blue}"/></marker>
    <marker id="arr-ds-ft" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="${C.muted}"/></marker>
  </defs>
  <line x1="318" y1="157" x2="308" y2="163" stroke="${C.blue}" stroke-width="1.5" marker-end="url(#arr-ds-face)"/>
  <!-- Ball at contact -->
  <circle cx="290" cy="150" r="7" fill="${C.accent}" opacity="0.72"/>
  <!-- Short follow-through (decelerate at contact) -->
  <path d="M 265,130 Q 272,148 278,168" fill="none" stroke="${C.muted}" stroke-width="1.5" stroke-dasharray="4,3" opacity="0.75" marker-end="url(#arr-ds-ft)"/>
  <text x="228" y="155" font-family="system-ui,sans-serif" font-size="9" fill="${C.muted}">short</text>
  <text x="220" y="166" font-family="system-ui,sans-serif" font-size="9" fill="${C.muted}">follow-thru</text>
  <!-- Ball path (barely clears net, lands short) -->
  <path d="M 290,150 Q 242,188 202,198" fill="none" stroke="${C.muted}" stroke-width="1.5" stroke-dasharray="4,3" opacity="0.5"/>
  <!-- Disguise note -->
  <text x="62" y="54" font-family="system-ui,sans-serif" font-size="9" fill="${C.muted}" font-style="italic">same prep as normal forehand</text>
  <path d="M 105,57 Q 120,72 148,92" fill="none" stroke="${C.muted}" stroke-width="1" stroke-dasharray="3,2" opacity="0.45"/>
  <!-- Labels -->
  <text x="200" y="262" font-family="system-ui,sans-serif" font-size="13" font-weight="700" fill="${C.text}" text-anchor="middle">Drop Shot — Soft Wrist, Open Face</text>
  <text x="200" y="279" font-family="system-ui,sans-serif" font-size="10" fill="${C.muted}" text-anchor="middle">Disguise with normal prep, decelerate at contact, open face adds backspin</text>
</svg>`;

const SLICE_SVG = shotSvg(
  "Slice Forehand — Backspin, stays low",
  `<path d="M 30,148 Q 200,120 370,155" fill="none" stroke="#06b6d4" stroke-width="2.5" stroke-dasharray="6,3"/>
   <circle cx="30" cy="148" r="7" fill="${C.accent}"/>
   <circle cx="370" cy="155" r="7" fill="#06b6d4" opacity="0.6"/>
   <!-- Backspin arrows -->
   <path d="M 200,126 A 10,10 0 1,0 190,132" fill="none" stroke="#06b6d4" stroke-width="2" marker-end="url(#bspin)"/>
   <defs><marker id="bspin" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="#06b6d4"/></marker></defs>`,
  `<text x="200" y="145" font-family="system-ui,sans-serif" font-size="10" fill="#06b6d4" text-anchor="middle">stays low after bounce</text>`,
);

// ---------------------------------------------------------------------------
// Gym — Exercise form SVGs (side-view stick figures)
// ---------------------------------------------------------------------------

const BENCH_PRESS_SVG = `<svg viewBox="0 0 400 240" xmlns="http://www.w3.org/2000/svg">
  <rect width="400" height="240" fill="${C.bg}" rx="12"/>
  <!-- Bench -->
  <rect x="60" y="140" width="260" height="18" fill="#94a3b8" stroke="${C.outline}" stroke-width="1.5" rx="4"/>
  <rect x="80" y="158" width="12" height="30" fill="#94a3b8" stroke="${C.outline}" stroke-width="1"/>
  <rect x="295" y="158" width="12" height="30" fill="#94a3b8" stroke="${C.outline}" stroke-width="1"/>
  <!-- Body (lying) -->
  <line x1="100" y1="138" x2="310" y2="138" stroke="${C.outline}" stroke-width="4" stroke-linecap="round"/>
  <!-- Head -->
  <circle cx="95" cy="130" r="14" fill="#fde8d8" stroke="${C.outline}" stroke-width="2"/>
  <!-- Bar -->
  <rect x="130" y="95" width="140" height="8" fill="#64748b" stroke="${C.outline}" stroke-width="1.5" rx="3"/>
  <!-- Weight plates -->
  <rect x="120" y="88" width="12" height="22" fill="#334155" stroke="${C.outline}" stroke-width="1" rx="2"/>
  <rect x="268" y="88" width="12" height="22" fill="#334155" stroke="${C.outline}" stroke-width="1" rx="2"/>
  <!-- Arms (45° elbow flare) -->
  <line x1="200" y1="138" x2="185" y2="105" stroke="${C.outline}" stroke-width="3.5" stroke-linecap="round"/>
  <line x1="200" y1="138" x2="215" y2="105" stroke="${C.outline}" stroke-width="3.5" stroke-linecap="round"/>
  <!-- Key angle annotation -->
  <path d="M 188,120 A 20,20 0 0,1 200,138" fill="none" stroke="${C.accent}" stroke-width="1.5" stroke-dasharray="3,2"/>
  <text x="172" y="128" font-family="system-ui,sans-serif" font-size="10" fill="${C.accent}">45–75°</text>
  <!-- Labels -->
  <text x="200" y="210" font-family="system-ui,sans-serif" font-size="14" font-weight="700" fill="${C.text}" text-anchor="middle">Bench Press — Starting Position</text>
  <text x="200" y="228" font-family="system-ui,sans-serif" font-size="11" fill="${C.muted}" text-anchor="middle">Bar over lower chest, elbows at 45–75° from torso</text>
</svg>`;

const PUSHUP_SVG = `<svg viewBox="0 0 400 220" xmlns="http://www.w3.org/2000/svg">
  <rect width="400" height="220" fill="${C.bg}" rx="12"/>
  <!-- Floor -->
  <line x1="20" y1="170" x2="380" y2="170" stroke="${C.outline}" stroke-width="2"/>
  <!-- Body (plank line) -->
  <line x1="80" y1="120" x2="320" y2="158" stroke="${C.outline}" stroke-width="5" stroke-linecap="round"/>
  <!-- Head -->
  <circle cx="72" cy="112" r="13" fill="#fde8d8" stroke="${C.outline}" stroke-width="2"/>
  <!-- Arms (bent, down position) -->
  <line x1="120" y1="128" x2="110" y2="168" stroke="${C.outline}" stroke-width="3.5" stroke-linecap="round"/>
  <line x1="230" y1="144" x2="220" y2="168" stroke="${C.outline}" stroke-width="3.5" stroke-linecap="round"/>
  <!-- Feet -->
  <rect x="312" y="155" width="18" height="14" fill="${C.outline}" rx="3"/>
  <!-- Straight-body alignment indicator -->
  <line x1="72" y1="112" x2="320" y2="158" stroke="${C.accent}" stroke-width="1.5" stroke-dasharray="5,4" opacity="0.7"/>
  <text x="200" y="100" font-family="system-ui,sans-serif" font-size="10" fill="${C.accent}" text-anchor="middle">straight line head→heels</text>
  <!-- Labels -->
  <text x="200" y="196" font-family="system-ui,sans-serif" font-size="14" font-weight="700" fill="${C.text}" text-anchor="middle">Push-Up — Down Position</text>
  <text x="200" y="214" font-family="system-ui,sans-serif" font-size="11" fill="${C.muted}" text-anchor="middle">Core tight, body in one straight line</text>
</svg>`;

const SQUAT_SVG = `<svg viewBox="0 0 400 240" xmlns="http://www.w3.org/2000/svg">
  <rect width="400" height="240" fill="${C.bg}" rx="12"/>
  <!-- Floor -->
  <line x1="20" y1="200" x2="380" y2="200" stroke="${C.outline}" stroke-width="2"/>
  <!-- Torso -->
  <line x1="200" y1="80" x2="200" y2="155" stroke="${C.outline}" stroke-width="5" stroke-linecap="round"/>
  <!-- Head -->
  <circle cx="200" cy="68" r="14" fill="#fde8d8" stroke="${C.outline}" stroke-width="2"/>
  <!-- Bar across shoulders -->
  <rect x="155" y="85" width="90" height="8" fill="#64748b" stroke="${C.outline}" stroke-width="1.5" rx="3"/>
  <rect x="145" y="82" width="12" height="14" fill="#334155" rx="2" stroke="${C.outline}" stroke-width="1"/>
  <rect x="243" y="82" width="12" height="14" fill="#334155" rx="2" stroke="${C.outline}" stroke-width="1"/>
  <!-- Hips -->
  <circle cx="200" cy="155" r="8" fill="${C.outline}"/>
  <!-- Thighs (parallel to floor) -->
  <line x1="200" y1="155" x2="155" y2="175" stroke="${C.outline}" stroke-width="4" stroke-linecap="round"/>
  <line x1="200" y1="155" x2="245" y2="175" stroke="${C.outline}" stroke-width="4" stroke-linecap="round"/>
  <!-- Shins -->
  <line x1="155" y1="175" x2="145" y2="200" stroke="${C.outline}" stroke-width="4" stroke-linecap="round"/>
  <line x1="245" y1="175" x2="255" y2="200" stroke="${C.outline}" stroke-width="4" stroke-linecap="round"/>
  <!-- Knees annotation -->
  <path d="M 155,175 A 18,18 0 0,0 145,200" fill="none" stroke="${C.accent}" stroke-width="1.5" stroke-dasharray="3,2"/>
  <text x="125" y="190" font-family="system-ui,sans-serif" font-size="10" fill="${C.accent}">90°+</text>
  <!-- Parallel indicator -->
  <line x1="140" y1="165" x2="260" y2="165" stroke="${C.accent}" stroke-width="1" stroke-dasharray="4,3" opacity="0.6"/>
  <text x="270" y="169" font-family="system-ui,sans-serif" font-size="9" fill="${C.accent}">parallel</text>
  <!-- Labels -->
  <text x="200" y="220" font-family="system-ui,sans-serif" font-size="14" font-weight="700" fill="${C.text}" text-anchor="middle">Back Squat — Bottom Position</text>
  <text x="200" y="236" font-family="system-ui,sans-serif" font-size="11" fill="${C.muted}" text-anchor="middle">Thighs at least parallel, knees tracking toes</text>
</svg>`;

// ---------------------------------------------------------------------------
// Tennis content
// ---------------------------------------------------------------------------

const TENNIS: LearnActivity = {
  id: "tennis",
  title: "Tennis",
  description: "Master strokes, movement, and strategy on the court.",
  icon: "🎾",
  color: "from-green-500 to-emerald-600",
  modules: [
    {
      type: "variant-select",
      id: "forehand",
      title: "Forehand",
      description: "The most-used stroke in tennis. Grip choice shapes every other aspect of your forehand.",
      icon: "🤚",
      variantGroup: {
        prompt: "Choose your grip",
        variants: [
          {
            id: "eastern",
            title: "Eastern Grip",
            subtitle: "Flat power & versatility — great all-round choice",
            svg: EASTERN_SVG,
            lessons: [
              {
                id: "flat-forehand",
                title: "Flat Forehand",
                description: "A fast, penetrating shot with a low, straight trajectory.",
                difficulty: "beginner",
                content: [
                  { type: "svg", svg: FLAT_FOREHAND_SVG, caption: "Ball travels low and fast over the net — ideal when you have an open court." },
                  { type: "section-header", text: "The Setup" },
                  { type: "text", text: "Start with a shoulder-turn and a compact backswing. Your non-dominant hand guides the racket back and primes the unit turn. Weight should be on the back foot as the ball approaches." },
                  { type: "key-points", points: [
                    "Shoulder turn: 90° rotation before the ball bounces",
                    "Backswing: racket head level with or above the wrist",
                    "Contact point: slightly in front of the front hip",
                    "Swing path: low-to-high at roughly 15–20°",
                  ]},
                  { type: "section-header", text: "The Swing" },
                  { type: "text", text: "Drive forward and up through the ball. For a flat shot, the swing path is relatively horizontal — your racket strings should be nearly perpendicular to the ball at contact. Snap the wrist slightly at impact to maximise pace, then follow through to the opposite shoulder." },
                  { type: "tip", text: "Think 'brush the outside of the ball' — a slight upward clip adds just enough spin for net clearance without sacrificing pace." },
                  { type: "key-points", points: [
                    "Elbow leads the swing (kinetic chain: legs → hips → shoulder → elbow → wrist)",
                    "Contact: strings face target, arm nearly fully extended",
                    "Follow-through: racket finishes over the left shoulder",
                    "Weight transfers front as you make contact",
                  ]},
                ],
              },
              {
                id: "topspin",
                title: "Topspin Forehand",
                description: "Heavy topspin for a high net clearance and a kicking bounce.",
                difficulty: "intermediate",
                content: [
                  { type: "svg", svg: TOPSPIN_SVG, caption: "High arc clears the net safely; topspin pulls the ball down sharply in the opponent's court." },
                  { type: "section-header", text: "Why Topspin?" },
                  { type: "text", text: "Topspin lets you hit the ball hard while keeping it in — the forward spin creates additional downward pressure, so the ball drops faster into the court. It also produces a higher, kicking bounce that pushes your opponent back." },
                  { type: "key-points", points: [
                    "Swing path: steep low-to-high (45–60°) — 'brush up the back of the ball'",
                    "Racket-head speed is more important than raw power",
                    "Drop the racket head below the ball on the backswing",
                    "Accelerate aggressively from low to high through contact",
                  ]},
                  { type: "tip", text: "Feel like you're 'windshield-wiping' the ball — the racket face swipes from low-to-high and rolls over the top of the ball at contact." },
                ],
              },
              {
                id: "inside-out",
                title: "Inside-Out Forehand",
                description: "Running around a backhand to hit a forehand cross-court.",
                difficulty: "intermediate",
                content: [
                  { type: "svg", svg: INSIDE_OUT_SVG, caption: "Player repositions to the backhand corner and redirects cross-court to the opponent's backhand." },
                  { type: "section-header", text: "When to Use It" },
                  { type: "text", text: "The inside-out forehand is a weapon used to put pressure on the opponent's backhand when the ball lands in your backhand corner. By running around the ball, you convert a potential weakness into a point-winning forehand." },
                  { type: "key-points", points: [
                    "Read the incoming ball early — start moving before it bounces",
                    "Position: arrive behind the ball, square your stance to the target",
                    "Aim cross-court toward the opponent's backhand side",
                    "Recover quickly after the shot — you've left the court open",
                  ]},
                  { type: "tip", text: "Only run around the backhand when you have time. If the ball is fast or deep, use a reliable backhand instead." },
                ],
              },
            ],
          },
          {
            id: "western",
            title: "Western Grip",
            subtitle: "Maximum topspin — ideal for high balls & clay",
            svg: WESTERN_SVG,
            lessons: [
              {
                id: "heavy-topspin",
                title: "Heavy Topspin Rally Ball",
                description: "Grind opponents back with looping, high-bouncing topspin.",
                difficulty: "intermediate",
                content: [
                  { type: "svg", svg: TOPSPIN_SVG, caption: "Ball kicks high off the bounce, forcing opponents to strike at shoulder height." },
                  { type: "section-header", text: "The Western Difference" },
                  { type: "text", text: "The Western grip naturally closes the racket face, making extreme topspin the default swing pattern. This produces a ball that bounces higher than with an Eastern grip — an especially potent weapon on slower surfaces like clay." },
                  { type: "key-points", points: [
                    "Swing path: near-vertical (60–75° low-to-high)",
                    "Contact: racket face slightly closed at impact",
                    "Target: 2–3 feet above the net at the apex of your shot",
                    "Aim for depth — landing the ball 1–2 m inside the baseline",
                  ]},
                  { type: "tip", text: "The Western grip makes it harder to hit flat or slice. Focus on playing to high, looping balls and construct points to receive a ball at a comfortable height before attacking." },
                ],
              },
              {
                id: "high-bounce",
                title: "High-Bouncing Ball to the Backhand",
                description: "Exploit the high kick to push opponents off the court.",
                difficulty: "advanced",
                content: [
                  { type: "3d-scene", sceneId: "high-bounce-forehand", caption: "Open stance with full shoulder rotation — meet the ball at shoulder height with an aggressive upswing. Drag to orbit." },
                  { type: "section-header", text: "Targeting the Shoulder" },
                  { type: "text", text: "A heavy topspin ball directed at the opponent's backhand shoulder forces them to hit an awkward, defensive shot. When the ball kicks above shoulder height, most players can't generate power — turning a neutral rally into an attacking opportunity for you." },
                  { type: "key-points", points: [
                    "Aim for the opponent's weaker side (usually backhand)",
                    "Hit crosscourt to maximise court angles",
                    "The ball should bounce between waist and shoulder height",
                    "Move into the court after the shot to be ready to finish the point",
                  ]},
                  { type: "tip", text: "On slower surfaces, add extra spin to amplify the bounce effect. On fast surfaces, flatten out slightly to prevent the ball from sitting up." },
                ],
              },
            ],
          },
          {
            id: "continental",
            title: "Continental Grip",
            subtitle: "Slice & drop shots — serve and volley foundation",
            svg: CONTINENTAL_SVG,
            lessons: [
              {
                id: "slice",
                title: "Slice Forehand",
                description: "Low, skidding ball that stays low through the bounce.",
                difficulty: "intermediate",
                content: [
                  { type: "svg", svg: SLICE_SVG, caption: "Backspin keeps the ball low and slides through the court, making it awkward to attack." },
                  { type: "section-header", text: "What Makes a Slice" },
                  { type: "text", text: "The continental grip opens the racket face so you can swing down and through the ball, imparting backspin. The ball floats lower over the net and skids through the court — an effective change-of-pace that disrupts rhythm." },
                  { type: "key-points", points: [
                    "Backswing: racket above the ball, face slightly open",
                    "Swing: high-to-low, 'cutting' under the ball",
                    "Contact: strings face slightly skyward, push forward at impact",
                    "Follow-through: long and low, finishing past the front hip",
                  ]},
                  { type: "tip", text: "Use slice as an approach shot — its low bounce forces the opponent to hit up, giving you time to come to the net and volley." },
                ],
              },
              {
                id: "drop-shot",
                title: "Drop Shot",
                description: "Delicate touch shot that barely clears the net.",
                difficulty: "advanced",
                content: [
                  { type: "svg", svg: DROP_SHOT_SVG, caption: "Soft wrist and open racket face at waist-height contact — disguise the prep, decelerate at impact." },
                  { type: "section-header", text: "The Art of Disguise" },
                  { type: "text", text: "A drop shot is only effective when the opponent doesn't read it early. Disguise it by using the same preparation as a regular groundstroke, then dramatically reduce swing speed at the last moment and 'catch' the ball on the strings." },
                  { type: "key-points", points: [
                    "Same prep as a normal forehand — don't telegraph",
                    "Decelerate the racket just before contact",
                    "Open the face slightly to add backspin",
                    "Ball should land within 1 m of the net and bounce twice before the service line",
                  ]},
                  { type: "tip", text: "Best used when the opponent is behind the baseline. If they're inside the baseline, don't attempt a drop shot — it'll be retrieved easily." },
                ],
              },
            ],
          },
          {
            id: "semi-western",
            title: "Semi-Western Grip",
            subtitle: "Most popular modern grip — versatile topspin",
            svg: SEMI_WESTERN_SVG,
            lessons: [
              {
                id: "topspin-crosscourt",
                title: "Topspin Cross-Court",
                description: "The bread-and-butter rally ball of modern tennis.",
                difficulty: "beginner",
                content: [
                  { type: "svg", svg: TOPSPIN_SVG, caption: "Cross-court topspin exploits the longest part of the court, giving maximum margin for error." },
                  { type: "section-header", text: "Why Cross-Court?" },
                  { type: "text", text: "The cross-court forehand is the highest-percentage shot in tennis. The net is 6 inches lower in the middle, and you have the full diagonal length of the court — giving you more room in both dimensions compared to a down-the-line shot." },
                  { type: "key-points", points: [
                    "Aim for a target 3–4 feet inside the sideline",
                    "Net clearance: aim 2–3 feet above the net tape",
                    "Swing path: low-to-high (45°) with full hip and shoulder rotation",
                    "Weight transfer: front foot carries your weight through contact",
                  ]},
                ],
              },
              {
                id: "down-the-line",
                title: "Down-the-Line Winner",
                description: "Aggressive finishing shot along the sideline.",
                difficulty: "intermediate",
                content: [
                  { type: "svg", svg: FLAT_FOREHAND_SVG, caption: "Down-the-line shot takes the shortest path — less time for the opponent to react." },
                  { type: "section-header", text: "When to Go Down the Line" },
                  { type: "text", text: "The down-the-line forehand is a high-risk, high-reward shot. It requires redirecting the ball against its natural momentum. Use it when you've pushed the opponent wide and have an open court, or to wrong-foot an opponent who has been anticipating cross-court." },
                  { type: "key-points", points: [
                    "Best on a short or mid-court ball — don't go for it from behind the baseline",
                    "Adjust your swing path: point the strings slightly left of target earlier",
                    "Firm wrist at contact — less 'wiping' than a cross-court",
                    "Recover toward the centre after the shot",
                  ]},
                  { type: "tip", text: "Practice this shot from a comfortable position first, then gradually move it earlier and earlier in the rally so you can deploy it as a surprise weapon." },
                ],
              },
            ],
          },
        ],
      },
    },
    {
      type: "variant-select",
      id: "backhand",
      title: "Backhand",
      description: "One-handed slice or two-handed topspin — find what works for your game.",
      icon: "🤜",
      variantGroup: {
        prompt: "Choose your backhand style",
        variants: [
          {
            id: "two-handed",
            title: "Two-Handed Backhand",
            subtitle: "More stability and topspin — preferred by most modern players",
            lessons: [
              {
                id: "topspin-backhand",
                title: "Topspin Two-Handed Backhand",
                description: "The most reliable backhand for club-level players.",
                difficulty: "beginner",
                content: [
                  { type: "section-header", text: "Grip & Setup" },
                  { type: "text", text: "The dominant hand uses a continental or eastern backhand grip; the non-dominant hand wraps above it with a semi-western forehand grip. Think of it as hitting a left-hand forehand (for right-handers) with the dominant hand guiding direction." },
                  { type: "key-points", points: [
                    "Dominant hand: Eastern backhand (knuckle on top bevel)",
                    "Non-dominant hand: Semi-western (drives the shot)",
                    "Shoulder turn: rotate fully so your back faces the net",
                    "Contact: in front of the body, arms extended but not locked",
                  ]},
                  { type: "tip", text: "Most power on the two-hander comes from the non-dominant hand. If your backhand feels weak, focus on driving through with that hand." },
                ],
              },
            ],
          },
          {
            id: "one-handed",
            title: "One-Handed Backhand",
            subtitle: "Greater reach and disguise — a beautiful, classic stroke",
            lessons: [
              {
                id: "slice-backhand",
                title: "One-Handed Slice",
                description: "A defensive and approach weapon that keeps the ball low.",
                difficulty: "beginner",
                content: [
                  { type: "section-header", text: "The Foundation Shot" },
                  { type: "text", text: "The one-handed slice is often learned before the topspin one-hander. It's reliable, consistent, and invaluable as an approach shot or when in a defensive position." },
                  { type: "key-points", points: [
                    "Continental grip — essential for the slice",
                    "High backswing, swing high-to-low through the ball",
                    "Support the racket with the non-dominant hand until the swing starts",
                    "Follow through long and low, extending toward the target",
                  ]},
                ],
              },
            ],
          },
        ],
      },
    },
    {
      type: "lessons",
      id: "serve",
      title: "Serve",
      description: "The only shot you fully control — learn to weaponise it.",
      icon: "💥",
      lessons: [
        {
          id: "flat-serve",
          title: "Flat Serve",
          description: "Maximum pace down the T or out wide.",
          difficulty: "intermediate",
          content: [
            { type: "section-header", text: "The Flat Serve" },
            { type: "text", text: "The flat serve is a weapon serve aimed at the 'T' (centre line) or out wide. It has minimal spin, so it stays low through the court — making it hard to attack — but also has a lower margin than kick or slice serves." },
            { type: "key-points", points: [
              "Grip: Continental (essential — not Eastern)",
              "Toss: slightly in front and to the right (for right-handers)",
              "Trophy position: both arms up, weight balanced on back foot",
              "Contact: at full extension, strings driving through the ball",
              "Pronation: forearm rotates so palm faces away at finish",
            ]},
            { type: "tip", text: "Aim for a target only 6–8 inches above the net on a flat serve. Any higher and the ball will land long; any lower and it clips the tape." },
          ],
        },
        {
          id: "kick-serve",
          title: "Kick Serve",
          description: "Safe second serve with high bounce into the body.",
          difficulty: "advanced",
          content: [
            { type: "section-header", text: "Why Kick?" },
            { type: "text", text: "The kick serve is the gold standard second serve. By brushing up and over the ball (toward 11 o'clock for right-handers), you generate topspin that pulls the ball down into the box — giving you much more net clearance and a much larger target than the flat serve." },
            { type: "key-points", points: [
              "Toss: slightly behind the head and to the left (right-handers)",
              "Back arch: coil the body so you can 'unwind' upward",
              "Brushing motion: racket swings from 7 o'clock to 1 o'clock",
              "The ball kicks high and into the body on the T",
            ]},
          ],
        },
      ],
    },
  ],
};

// ---------------------------------------------------------------------------
// Gym content
// ---------------------------------------------------------------------------

const GYM: LearnActivity = {
  id: "gym",
  title: "Gym Workout",
  description: "Build strength, mobility, and muscle with structured exercise lessons.",
  icon: "🏋️",
  color: "from-blue-500 to-indigo-600",
  modules: [
    {
      type: "variant-select",
      id: "chest",
      title: "Chest",
      description: "Build pressing strength and chest development from multiple angles.",
      icon: "💪",
      variantGroup: {
        prompt: "Choose your equipment",
        variants: [
          {
            id: "barbell",
            title: "Barbell",
            subtitle: "Maximum load potential — the classic strength builder",
            lessons: [
              {
                id: "bench-press",
                title: "Barbell Bench Press",
                description: "The foundational chest pressing movement.",
                difficulty: "beginner",
                content: [
                  { type: "svg", svg: BENCH_PRESS_SVG, caption: "Bar lowers to the lower chest with elbows at 45–75° from the torso." },
                  { type: "section-header", text: "Setup" },
                  { type: "text", text: "Lie flat on the bench with eyes directly under the bar. Set your feet flat on the floor. Create an arch in your lower back — not an extreme powerlifting arch, but enough to keep your upper back tight. Grip the bar slightly wider than shoulder-width." },
                  { type: "key-points", points: [
                    "Grip: just outside shoulder width, thumbs wrapped (not suicide grip)",
                    "Arch: natural lower-back curve, upper back pressed into bench",
                    "Elbow angle: 45–75° from torso — not flared to 90°",
                    "Unrack with arms fully extended, then lower under control",
                  ]},
                  { type: "section-header", text: "The Lift" },
                  { type: "text", text: "Lower the bar to your lower chest in a straight vertical line. Touch lightly — don't bounce. Press back up in a slight arc (bar moves slightly back toward the rack at the top). Lock out fully at the top." },
                  { type: "tip", text: "Leg drive matters: press your feet into the floor and drive through your entire body. A bench press is a full-body movement, not just a chest exercise." },
                  { type: "key-points", points: [
                    "Tempo: 2–3 s down, pause 1 s, press up",
                    "Breathing: inhale on the way down, exhale on the way up",
                    "Spotter: always use one when going heavy",
                  ]},
                ],
              },
              {
                id: "incline-press",
                title: "Incline Barbell Press",
                description: "Targets the upper chest and front deltoids.",
                difficulty: "beginner",
                content: [
                  { type: "section-header", text: "Incline Setup" },
                  { type: "text", text: "Set the bench to 30–45°. Higher angles shift emphasis from upper chest to front deltoid — 30–35° is optimal for upper chest development. Everything else mirrors the flat bench setup." },
                  { type: "key-points", points: [
                    "Bench angle: 30–45° (30° = more chest, 45° = more shoulder)",
                    "Bar path: lower to upper chest / collarbone area",
                    "Expect to use 10–20% less weight than flat bench",
                    "Full range: touch the upper chest at the bottom, lock out at top",
                  ]},
                ],
              },
              {
                id: "decline-press",
                title: "Decline Barbell Press",
                description: "Emphasises the lower chest fibres.",
                difficulty: "intermediate",
                content: [
                  { type: "section-header", text: "Decline Press" },
                  { type: "text", text: "Set the bench to –15 to –30°. Most people are stronger in the decline position because the bar travels a shorter distance. Lock your feet into the holders securely." },
                  { type: "key-points", points: [
                    "Decline: –15 to –30° for lower chest focus",
                    "Bar lowers to the bottom of the chest / sternum",
                    "Often slightly stronger than flat due to shorter ROM",
                    "Ensure feet are secured before lifting off",
                  ]},
                ],
              },
            ],
          },
          {
            id: "dumbbell",
            title: "Dumbbell",
            subtitle: "Greater range of motion — catch muscle imbalances",
            lessons: [
              {
                id: "db-flat-press",
                title: "Dumbbell Flat Press",
                description: "More range of motion than barbell, exposes imbalances.",
                difficulty: "beginner",
                content: [
                  { type: "section-header", text: "Why Dumbbells?" },
                  { type: "text", text: "Dumbbells allow each arm to move independently, exposing and correcting strength imbalances. They also allow a greater range of motion — the dumbbells can drop below chest level on the way down, stretching the pec more fully." },
                  { type: "key-points", points: [
                    "Hold dumbbells with a neutral or pronated grip (palms forward)",
                    "Lower until your upper arm is parallel to the floor or slightly below",
                    "Press up and bring dumbbells slightly together at the top (don't clank them)",
                    "Control the descent — the stretch at the bottom builds strength",
                  ]},
                  { type: "tip", text: "To get heavy dumbbells into position: sit on the bench, rest the dumbbells on your thighs, then use a 'kick and lay back' motion as you lie down." },
                ],
              },
              {
                id: "db-flyes",
                title: "Dumbbell Flyes",
                description: "Isolation movement — feels the chest through its full range.",
                difficulty: "beginner",
                content: [
                  { type: "section-header", text: "Isolation vs Compound" },
                  { type: "text", text: "Flyes are an isolation exercise — they take the triceps and shoulders mostly out of the movement. This lets you 'feel' the chest more. They're best used after compound pressing movements, not as a replacement for them." },
                  { type: "key-points", points: [
                    "Slight bend in the elbows — keep this angle throughout (it protects the shoulder)",
                    "Lower in a wide arc until you feel a stretch in the pec",
                    "Bring dumbbells back up in the same arc, squeezing the chest at the top",
                    "Light to moderate weight only — don't ego-lift on flyes",
                  ]},
                  { type: "tip", text: "Think 'hugging a barrel' — the movement is an arc, not a press. The elbows should barely change angle throughout." },
                ],
              },
            ],
          },
          {
            id: "bodyweight",
            title: "Bodyweight",
            subtitle: "No equipment required — master your own weight first",
            lessons: [
              {
                id: "push-up",
                title: "Push-Up",
                description: "The foundation of upper-body pushing strength.",
                difficulty: "beginner",
                content: [
                  { type: "svg", svg: PUSHUP_SVG, caption: "Straight line from head to heels — don't let the hips sag or pike." },
                  { type: "section-header", text: "Perfect Form" },
                  { type: "text", text: "The push-up is a full-body movement. Set a rigid plank from head to heels before you start. Hands slightly wider than shoulder-width, fingers pointing forward or slightly out. Lower your chest to the floor with elbows at roughly 45° from the torso." },
                  { type: "key-points", points: [
                    "Body: straight line from ankles through knees, hips, and shoulders",
                    "Core: braced — imagine someone is about to punch your stomach",
                    "Elbows: 45° from torso (not flared to 90°)",
                    "Full range: chest touches or nearly touches the floor",
                  ]},
                  { type: "tip", text: "Can't do a full push-up yet? Start on your knees, or elevate your hands on a box. The movement pattern is what matters — build up gradually." },
                ],
              },
              {
                id: "dips",
                title: "Chest Dips",
                description: "Compound bodyweight movement for lower chest and triceps.",
                difficulty: "intermediate",
                content: [
                  { type: "section-header", text: "Chest vs Tricep Dips" },
                  { type: "text", text: "To target the chest, lean your torso forward at about 30–45° and allow your elbows to flare slightly outward. Upright torso and tucked elbows shifts emphasis to triceps." },
                  { type: "key-points", points: [
                    "Lean forward: 30–45° for chest focus",
                    "Lower until upper arms are parallel to the floor (full range)",
                    "Press back up to full lockout",
                    "Add weight with a dipping belt once bodyweight becomes easy",
                  ]},
                  { type: "tip", text: "If dips cause shoulder pain, stop. They can be hard on the anterior shoulder. Ensure full warm-up and don't go deeper than parallel." },
                ],
              },
            ],
          },
        ],
      },
    },
    {
      type: "variant-select",
      id: "legs",
      title: "Legs",
      description: "Build powerful quads, hamstrings, glutes, and calves.",
      icon: "🦵",
      variantGroup: {
        prompt: "Choose your equipment",
        variants: [
          {
            id: "barbell",
            title: "Barbell",
            subtitle: "Squat and deadlift — the kings of leg development",
            lessons: [
              {
                id: "back-squat",
                title: "Barbell Back Squat",
                description: "The king of lower-body exercises.",
                difficulty: "intermediate",
                content: [
                  { type: "svg", svg: SQUAT_SVG, caption: "Thighs reach at least parallel to the floor; knees track in line with toes." },
                  { type: "section-header", text: "Setup & Bracing" },
                  { type: "text", text: "Set the bar on your upper traps (high bar) or across the rear delts (low bar). Before unracking, take a big breath into your belly, brace your core as if about to take a punch, and squeeze the bar hard to engage your lats. Step back in two steps and set your stance." },
                  { type: "key-points", points: [
                    "Stance: shoulder-width or slightly wider, toes 15–30° out",
                    "Brace: 360° tension through the core before each rep",
                    "Descent: hips back and down, knees push out over toes",
                    "Depth: at minimum parallel — hip crease below the knee",
                    "Ascent: drive through the full foot, keep chest up",
                  ]},
                  { type: "tip", text: "Record yourself from the side on your first session. Most beginners are surprised how shallow their squat depth actually is compared to how it feels." },
                ],
              },
            ],
          },
          {
            id: "bodyweight",
            title: "Bodyweight",
            subtitle: "Lunges and bodyweight squats for mobility and conditioning",
            lessons: [
              {
                id: "bodyweight-squat",
                title: "Bodyweight Squat",
                description: "Learn the squat pattern before loading.",
                difficulty: "beginner",
                content: [
                  { type: "section-header", text: "Master the Pattern" },
                  { type: "text", text: "Before loading a squat with a barbell or dumbbells, you need to own the movement pattern. The bodyweight squat teaches hip hinge, knee tracking, and depth without the added complexity of managing a load." },
                  { type: "key-points", points: [
                    "Arms out in front for counterbalance — helps you sit back",
                    "Sit back and down — don't just bend the knees forward",
                    "Keep your chest up and your spine neutral",
                    "Goal: thighs parallel or below parallel to the floor",
                  ]},
                ],
              },
            ],
          },
        ],
      },
    },
    {
      type: "plans",
      id: "plans",
      title: "Workout Plans",
      description: "Structured multi-day programs that combine exercises into a complete routine.",
      icon: "📋",
      plans: [
        {
          id: "ppl",
          title: "Push / Pull / Legs (PPL)",
          description: "A classic 6-day split that trains each muscle group twice per week. Push day hits chest, shoulders, and triceps; pull day targets back and biceps; legs covers quads, hamstrings, glutes, and calves.",
          level: "intermediate",
          frequency: "6 days / week",
          days: [
            {
              id: "push-a",
              title: "Push Day A",
              focus: "Chest, front delts, triceps",
              exercises: [
                { lessonRef: "gym.chest.barbell.bench-press", sets: "4 × 5", rest: "3 min", notes: "Work up to a heavy top set" },
                { lessonRef: "gym.chest.barbell.incline-press", sets: "3 × 8–10", rest: "2 min" },
                { lessonRef: "gym.chest.dumbbell.db-flyes", sets: "3 × 12–15", rest: "90 s", notes: "Light weight, focus on the stretch" },
                { lessonRef: "gym.chest.bodyweight.dips", sets: "3 × max", rest: "90 s", notes: "Add weight if 15+ reps per set" },
              ],
            },
            {
              id: "push-b",
              title: "Push Day B",
              focus: "Shoulders, upper chest, triceps",
              exercises: [
                { lessonRef: "gym.chest.barbell.incline-press", sets: "4 × 6–8", rest: "2 min", notes: "Main strength movement for this day" },
                { lessonRef: "gym.chest.dumbbell.db-flat-press", sets: "3 × 10–12", rest: "90 s" },
                { lessonRef: "gym.chest.bodyweight.push-up", sets: "3 × max", rest: "60 s", notes: "Use as finisher — max reps each set" },
              ],
            },
          ],
        },
        {
          id: "beginner-full-body",
          title: "Beginner Full-Body",
          description: "3 days per week, every muscle group each session. Ideal for newcomers who want to build a strength base before moving to a split program.",
          level: "beginner",
          frequency: "3 days / week (Mon / Wed / Fri)",
          days: [
            {
              id: "full-body-a",
              title: "Day A",
              focus: "Full body — squat pattern, press, pull",
              exercises: [
                { lessonRef: "gym.legs.bodyweight.bodyweight-squat", sets: "3 × 10", rest: "90 s", notes: "Focus on depth and form" },
                { lessonRef: "gym.chest.bodyweight.push-up", sets: "3 × 8–12", rest: "90 s" },
                { lessonRef: "gym.chest.dumbbell.db-flat-press", sets: "2 × 10", rest: "90 s", notes: "Light dumbbells to start" },
              ],
            },
          ],
        },
      ],
    },
  ],
};

// ---------------------------------------------------------------------------
// Registry & helpers
// ---------------------------------------------------------------------------

export const LEARN_CONTENT: LearnActivity[] = [TENNIS, GYM];

/** Resolve a dot-path lessonRef → Lesson (or null if not found). */
export function getLessonByRef(ref: string): Lesson | null {
  const parts = ref.split(".");
  if (parts.length < 3) return null;
  const [activityId, moduleId, ...rest] = parts;

  const activity = LEARN_CONTENT.find((a) => a.id === activityId);
  if (!activity) return null;
  const mod = activity.modules.find((m) => m.id === moduleId);
  if (!mod) return null;

  if (mod.type === "variant-select" && rest.length >= 2) {
    const [variantId, lessonId] = rest;
    const variant = mod.variantGroup.variants.find((v) => v.id === variantId);
    return variant?.lessons.find((l) => l.id === lessonId) ?? null;
  }
  if (mod.type === "lessons" && rest.length >= 1) {
    return mod.lessons.find((l) => l.id === rest[0]) ?? null;
  }
  return null;
}

/** Count all lessons in an activity (for overall progress %). */
export function countLessons(activity: LearnActivity): number {
  let n = 0;
  for (const mod of activity.modules) {
    if (mod.type === "variant-select") {
      for (const v of mod.variantGroup.variants) n += v.lessons.length;
    } else if (mod.type === "lessons") {
      n += mod.lessons.length;
    }
    // plans: progress is tracked at the plan-day level, not as lesson counts
  }
  return n;
}

/** Build the full lesson ID for a lesson inside a variant. */
export function variantLessonId(activityId: string, moduleId: string, variantId: string, lessonId: string): string {
  return `${activityId}.${moduleId}.${variantId}.${lessonId}`;
}

/** Build the full lesson ID for a direct lesson (no variant). */
export function directLessonId(activityId: string, moduleId: string, lessonId: string): string {
  return `${activityId}.${moduleId}.${lessonId}`;
}

/** Build the plan-day progress ID. */
export function planDayId(activityId: string, moduleId: string, planId: string, dayId: string): string {
  return `${activityId}.${moduleId}.${planId}.${dayId}`;
}
