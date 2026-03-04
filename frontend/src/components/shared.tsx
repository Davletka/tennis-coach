"use client";

import { useState, useRef, useCallback } from "react";
import type { AngleStatResult, MetricsResult } from "@/lib/api";

// ---------------------------------------------------------------------------
// Spinner
// ---------------------------------------------------------------------------

export function Spinner() {
  return (
    <div className="flex justify-center py-12">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-600 border-t-green-500" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// ErrorBanner
// ---------------------------------------------------------------------------

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-700 bg-red-950/40 px-4 py-3 text-sm text-red-300">
      <strong>Error:</strong> {message}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SignInPrompt
// ---------------------------------------------------------------------------

export function SignInPrompt({
  label,
  onSignIn,
}: {
  label: string;
  onSignIn: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-gray-700 bg-gray-900/50 py-16 text-center">
      <svg
        className="mb-3 h-10 w-10 text-gray-600"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z"
        />
      </svg>
      <p className="mb-1 text-sm font-medium text-gray-300">{label}</p>
      <p className="mb-4 text-xs text-gray-500">
        Sign in to access your personal session data
      </p>
      <button
        onClick={onSignIn}
        className="rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-500 transition-colors"
      >
        Sign in with Google
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DetectionBadge
// ---------------------------------------------------------------------------

export function DetectionBadge({ rate }: { rate: number }) {
  const pct = (rate * 100).toFixed(0) + "%";
  if (rate >= 0.7) {
    return (
      <span className="rounded-full bg-green-900/50 px-2 py-0.5 text-xs font-medium text-green-400">
        {pct} detected
      </span>
    );
  } else if (rate >= 0.4) {
    return (
      <span className="rounded-full bg-yellow-900/50 px-2 py-0.5 text-xs font-medium text-yellow-400">
        {pct} detected
      </span>
    );
  } else {
    return (
      <span className="rounded-full bg-red-900/50 px-2 py-0.5 text-xs font-medium text-red-400">
        {pct} detected
      </span>
    );
  }
}

// ---------------------------------------------------------------------------
// Coaching panel constants + helpers
// ---------------------------------------------------------------------------

export const DEFAULT_COACHING_LABELS: Record<string, string> = {
  swing_mechanics: "Swing",
  footwork_movement: "Footwork",
  stance_posture: "Stance",
  shot_selection_tactics: "Tactics",
};

export const COACHING_KEYS = [
  "swing_mechanics",
  "footwork_movement",
  "stance_posture",
  "shot_selection_tactics",
] as const;

export type CoachingKey = (typeof COACHING_KEYS)[number];

export function normalizeCoachingReport(report: {
  swing_mechanics: string;
  footwork_movement: string;
  stance_posture: string;
  shot_selection_tactics: string;
  top_3_priorities: string[];
}) {
  const raw = report.swing_mechanics ?? "";
  if (!raw.trimStart().startsWith("{")) return report;
  try {
    const start = raw.indexOf("{");
    const end = raw.lastIndexOf("}") + 1;
    const parsed = JSON.parse(raw.slice(start, end));
    if (parsed && typeof parsed === "object" && "swing_mechanics" in parsed) {
      return { ...report, ...parsed };
    }
  } catch {
    // not valid JSON — leave as-is
  }
  return report;
}

// ---------------------------------------------------------------------------
// CoachingPanel
// ---------------------------------------------------------------------------

export function CoachingPanel({
  report,
  labels = {},
}: {
  report: {
    swing_mechanics: string;
    footwork_movement: string;
    stance_posture: string;
    shot_selection_tactics: string;
    top_3_priorities: string[];
  };
  labels?: Record<string, string>;
}) {
  const [activeTab, setActiveTab] = useState<CoachingKey>("swing_mechanics");
  report = normalizeCoachingReport(report);
  const resolvedLabels = { ...DEFAULT_COACHING_LABELS, ...labels };

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-700">
      <div className="flex border-b border-gray-700">
        {COACHING_KEYS.map((key) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={[
              "flex-1 py-2.5 text-sm font-medium transition-colors",
              activeTab === key
                ? "border-b-2 border-green-500 text-green-400"
                : "text-gray-400 hover:text-gray-200",
            ].join(" ")}
          >
            {resolvedLabels[key]}
          </button>
        ))}
      </div>

      <div className="p-4 text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">
        {report[activeTab] || <span className="text-gray-500 italic">No data.</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AngleRow + MetricsTable
// ---------------------------------------------------------------------------

function fmt(v: number | null, decimals = 1): string {
  return v === null ? "—" : v.toFixed(decimals);
}

export function AngleRow({
  label,
  stat,
}: {
  label: string;
  stat: AngleStatResult;
}) {
  return (
    <tr className="border-t border-gray-700">
      <td className="py-1.5 pr-4 text-gray-300">{label}</td>
      <td className="py-1.5 px-3 text-right tabular-nums">{fmt(stat.mean)}°</td>
      <td className="py-1.5 px-3 text-right tabular-nums">{fmt(stat.min)}°</td>
      <td className="py-1.5 px-3 text-right tabular-nums">{fmt(stat.max)}°</td>
      <td className="py-1.5 pl-3 text-right tabular-nums">{fmt(stat.std)}°</td>
    </tr>
  );
}

export function MetricsTable({ metrics }: { metrics: MetricsResult }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-gray-300 hover:text-white"
      >
        <span>Raw Metrics</span>
        <svg
          className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="border-t border-gray-700 px-4 pb-4 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500">
                <th className="py-2 pr-4 text-left font-medium">Joint</th>
                <th className="py-2 px-3 text-right font-medium">Mean</th>
                <th className="py-2 px-3 text-right font-medium">Min</th>
                <th className="py-2 px-3 text-right font-medium">Max</th>
                <th className="py-2 pl-3 text-right font-medium">Std</th>
              </tr>
            </thead>
            <tbody>
              <AngleRow label="Right Elbow" stat={metrics.right_elbow} />
              <AngleRow label="Left Elbow" stat={metrics.left_elbow} />
              <AngleRow label="Right Shoulder" stat={metrics.right_shoulder} />
              <AngleRow label="Left Shoulder" stat={metrics.left_shoulder} />
              <AngleRow label="Right Knee" stat={metrics.right_knee} />
              <AngleRow label="Left Knee" stat={metrics.left_knee} />
            </tbody>
          </table>

          <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3">
            {[
              ["Torso Rotation (mean)", fmt(metrics.torso_rotation_mean) + "°"],
              ["Torso Rotation (max)", fmt(metrics.torso_rotation_max) + "°"],
              ["Stance Width (mean)", fmt(metrics.stance_width_mean)],
              ["CoM X Range", fmt(metrics.com_x_range)],
              ["Swing Count", String(metrics.swing_count)],
              ["Frames Analyzed", String(metrics.frames_analyzed)],
              ["Pose Detected", String(metrics.pose_detected_frames)],
              ["Detection Rate", (metrics.detection_rate * 100).toFixed(1) + "%"],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-gray-500">{k}</dt>
                <dd className="font-medium text-gray-200">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SwingCard
// ---------------------------------------------------------------------------

export type SwingCoachingKey = CoachingKey;

import type { PerSwingAnalysis } from "@/lib/api";

export function SwingCard({
  analysis,
  swingNumber,
  fps,
  onSeek,
  labels = {},
  videoUrl,
}: {
  analysis: PerSwingAnalysis;
  swingNumber: number;
  fps: number;
  onSeek: (t: number) => void;
  labels?: Record<string, string>;
  videoUrl?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<SwingCoachingKey>("swing_mechanics");
  const resolvedLabels = { ...DEFAULT_COACHING_LABELS, ...labels };
  const clipRef = useRef<HTMLVideoElement>(null);

  const peakTimeSecs = analysis.peak_frame / Math.max(fps, 1);
  const windowStartSecs = analysis.window_start_frame / Math.max(fps, 1);
  const windowEndSecs = analysis.window_end_frame / Math.max(fps, 1);
  const m = analysis.metrics;

  // When the clip video loads (or expanded changes), seek to the window start
  const handleClipLoaded = useCallback(() => {
    const v = clipRef.current;
    if (!v) return;
    v.currentTime = windowStartSecs;
  }, [windowStartSecs]);

  // Loop within the window
  const handleClipTimeUpdate = useCallback(() => {
    const v = clipRef.current;
    if (!v) return;
    if (v.currentTime >= windowEndSecs) {
      v.currentTime = windowStartSecs;
    }
  }, [windowStartSecs, windowEndSecs]);

  function fmtAngle(stat: { mean: number | null; min: number | null; max: number | null }): string {
    if (stat.mean === null) return "—";
    const mean = stat.mean.toFixed(0);
    if (stat.min !== null && stat.max !== null) {
      return `${mean}° (${stat.min.toFixed(0)}–${stat.max.toFixed(0)})`;
    }
    return `${mean}°`;
  }

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3">
        <span className="flex-shrink-0 rounded-full bg-green-900/60 px-2.5 py-0.5 text-xs font-bold text-green-400">
          #{swingNumber}
        </span>
        {m.motion_type && m.motion_type !== "unknown" && (
          <span className="flex-shrink-0 rounded-full bg-blue-900/50 px-2 py-0.5 text-xs font-medium text-blue-300 capitalize">
            {m.motion_type}
          </span>
        )}
        <button
          onClick={() => onSeek(peakTimeSecs)}
          className="flex-shrink-0 rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-300 hover:bg-gray-700 hover:text-white transition-colors tabular-nums"
          title="Seek to this swing"
        >
          {peakTimeSecs < 60
            ? `${peakTimeSecs.toFixed(1)}s`
            : `${Math.floor(peakTimeSecs / 60)}:${(peakTimeSecs % 60).toFixed(0).padStart(2, "0")}`}
          {" ↗"}
        </button>
        <p className="flex-1 truncate text-xs italic text-gray-400">
          {analysis.coaching.quick_note || "—"}
        </p>
        <button
          onClick={() => setExpanded((o) => !o)}
          className="flex-shrink-0 text-gray-500 hover:text-gray-300 transition-colors"
          aria-label={expanded ? "Collapse" : "Expand"}
        >
          <svg
            className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {/* Expanded body */}
      {expanded && (
        <div className="border-t border-gray-700 p-4 space-y-4">
          {/* Clip player */}
          {videoUrl && (
            <video
              ref={clipRef}
              src={videoUrl}
              className="w-full rounded-lg bg-black"
              style={{ maxHeight: "240px" }}
              controls
              muted
              playsInline
              onLoadedMetadata={handleClipLoaded}
              onTimeUpdate={handleClipTimeUpdate}
            />
          )}

          {/* Quick note */}
          {analysis.coaching.quick_note && (
            <p className="text-sm italic text-gray-300">{analysis.coaching.quick_note}</p>
          )}

          {/* Compact metrics grid */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
              Swing Metrics (mean, min–max)
            </p>
            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
              {[
                ["Right Elbow", fmtAngle(m.right_elbow)],
                ["Left Elbow", fmtAngle(m.left_elbow)],
                ["Right Shoulder", fmtAngle(m.right_shoulder)],
                ["Left Shoulder", fmtAngle(m.left_shoulder)],
                ["Right Knee", fmtAngle(m.right_knee)],
                ["Left Knee", fmtAngle(m.left_knee)],
                ["Peak Speed", m.peak_wrist_speed.toFixed(4)],
                ["Torso Rot.", m.torso_rotation_mean !== null ? `${m.torso_rotation_mean.toFixed(1)}°` : "—"],
                ["Stance Width", m.stance_width_mean !== null ? m.stance_width_mean.toFixed(2) : "—"],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt className="text-gray-500">{k}</dt>
                  <dd className="font-medium text-gray-200 tabular-nums">{v}</dd>
                </div>
              ))}
            </div>
          </div>

          {/* Tabbed coaching breakdown */}
          <div className="rounded-lg border border-gray-700">
            <div className="flex border-b border-gray-700">
              {COACHING_KEYS.map((key) => (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  className={[
                    "flex-1 py-2 text-xs font-medium transition-colors",
                    activeTab === key
                      ? "border-b-2 border-green-500 text-green-400"
                      : "text-gray-400 hover:text-gray-200",
                  ].join(" ")}
                >
                  {resolvedLabels[key]}
                </button>
              ))}
            </div>
            <div className="p-3 text-xs text-gray-200 whitespace-pre-wrap leading-relaxed min-h-[3rem]">
              {analysis.coaching[activeTab] || <span className="text-gray-500 italic">No data.</span>}
            </div>
          </div>

          {/* Per-swing priorities */}
          {analysis.coaching.top_3_priorities.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500">
                Priorities
              </p>
              <ol className="space-y-1 text-xs text-gray-200">
                {analysis.coaching.top_3_priorities.map((p, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="flex-shrink-0 font-bold text-green-400">{i + 1}.</span>
                    <span>{p}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
