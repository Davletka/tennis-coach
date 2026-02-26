"use client";

import { useCallback, useReducer, useRef, useState } from "react";
import {
  uploadVideo,
  getJobStatus,
  getJobResult,
  type JobResultResponse,
  type AngleStatResult,
  type MetricsResult,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// State machine — discriminated union keeps invalid states impossible
// ---------------------------------------------------------------------------

type AppState =
  | { phase: "idle" }
  | { phase: "uploading"; file: File; progress: number }
  | { phase: "polling"; jobId: string; progress: number; message: string }
  | { phase: "completed"; result: JobResultResponse }
  | { phase: "failed"; error: string };

type AppAction =
  | { type: "SELECT_FILE"; file: File }
  | { type: "UPLOAD_START" }
  | { type: "UPLOAD_DONE"; jobId: string }
  | { type: "POLL_UPDATE"; progress: number; message: string }
  | { type: "COMPLETE"; result: JobResultResponse }
  | { type: "FAIL"; error: string }
  | { type: "RESET" };

function reducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "SELECT_FILE":
      return { phase: "idle" };
    case "UPLOAD_START":
      if (state.phase !== "idle") return state;
      return { phase: "uploading", file: (state as never as { file: File }).file, progress: 0 };
    case "UPLOAD_DONE":
      return { phase: "polling", jobId: action.jobId, progress: 0, message: "Queued…" };
    case "POLL_UPDATE":
      if (state.phase !== "polling") return state;
      return { ...state, progress: action.progress, message: action.message };
    case "COMPLETE":
      return { phase: "completed", result: action.result };
    case "FAIL":
      return { phase: "failed", error: action.error };
    case "RESET":
      return { phase: "idle" };
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Upload + polling orchestration hook
// ---------------------------------------------------------------------------

function useTennisCoach() {
  const [state, dispatch] = useReducer(reducer, { phase: "idle" });
  const [file, setFile] = useState<File | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const scheduleNextPoll = useCallback(
    (jobId: string) => {
      pollTimerRef.current = setTimeout(async () => {
        try {
          const status = await getJobStatus(jobId);
          if (status.status === "completed") {
            const result = await getJobResult(jobId);
            dispatch({ type: "COMPLETE", result });
          } else if (status.status === "failed") {
            dispatch({ type: "FAIL", error: "Analysis failed on the server." });
          } else {
            dispatch({
              type: "POLL_UPDATE",
              progress: status.progress,
              message: status.message || "Processing…",
            });
            scheduleNextPoll(jobId);
          }
        } catch (err) {
          dispatch({ type: "FAIL", error: String(err) });
        }
      }, 2000);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const analyze = useCallback(
    async (f: File) => {
      dispatch({ type: "UPLOAD_START" });
      try {
        const { job_id } = await uploadVideo(f);
        dispatch({ type: "UPLOAD_DONE", jobId: job_id });
        scheduleNextPoll(job_id);
      } catch (err) {
        dispatch({ type: "FAIL", error: String(err) });
      }
    },
    [scheduleNextPoll]
  );

  const reset = useCallback(() => {
    stopPolling();
    setFile(null);
    dispatch({ type: "RESET" });
  }, [stopPolling]);

  return { state, file, setFile, analyze, reset };
}

// ---------------------------------------------------------------------------
// Sub-components (all inlined)
// ---------------------------------------------------------------------------

function UploadZone({
  file,
  onFile,
  onAnalyze,
  disabled,
}: {
  file: File | null;
  onFile: (f: File) => void;
  onAnalyze: () => void;
  disabled: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files[0];
      if (f) onFile(f);
    },
    [onFile]
  );

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        className={[
          "flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 transition-colors cursor-pointer select-none",
          dragging
            ? "border-green-400 bg-green-950/30"
            : "border-gray-600 hover:border-gray-400 bg-gray-900/50",
          disabled ? "pointer-events-none opacity-50" : "",
        ].join(" ")}
      >
        <svg
          className="mb-3 h-10 w-10 text-gray-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z"
          />
        </svg>
        {file ? (
          <p className="text-sm text-gray-200 font-medium">{file.name}</p>
        ) : (
          <>
            <p className="text-sm text-gray-300">
              Drag &amp; drop a video, or <span className="text-green-400 underline">browse</span>
            </p>
            <p className="mt-1 text-xs text-gray-500">MP4, MOV, AVI supported</p>
          </>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".mp4,.mov,.avi"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
        }}
      />

      <button
        disabled={!file || disabled}
        onClick={onAnalyze}
        className="w-full rounded-lg bg-green-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-green-500 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Analyze Video
      </button>
    </div>
  );
}

function ProgressBar({
  progress,
  message,
}: {
  progress: number;
  message: string;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-300">{message}</span>
        <span className="text-gray-400">{progress}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-700">
        <div
          className="h-full rounded-full bg-green-500 transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

const COACHING_TABS = [
  { key: "swing_mechanics", label: "Swing" },
  { key: "footwork_movement", label: "Footwork" },
  { key: "stance_posture", label: "Stance" },
  { key: "shot_selection_tactics", label: "Tactics" },
] as const;

type CoachingKey = (typeof COACHING_TABS)[number]["key"];

function CoachingPanel({
  report,
}: {
  report: JobResultResponse["coaching_report"];
}) {
  const [activeTab, setActiveTab] = useState<CoachingKey>("swing_mechanics");

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-700">
      {/* Tab bar */}
      <div className="flex border-b border-gray-700">
        {COACHING_TABS.map(({ key, label }) => (
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
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="p-4 text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">
        {report[activeTab] || <span className="text-gray-500 italic">No data.</span>}
      </div>

      {/* Priorities */}
      {report.top_3_priorities.length > 0 && (
        <div className="border-t border-gray-700 p-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
            Top Priorities
          </p>
          <ol className="space-y-1 text-sm text-gray-200">
            {report.top_3_priorities.map((p, i) => (
              <li key={i} className="flex gap-2">
                <span className="flex-shrink-0 font-bold text-green-400">{i + 1}.</span>
                <span>{p}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function fmt(v: number | null, decimals = 1): string {
  return v === null ? "—" : v.toFixed(decimals);
}

function AngleRow({
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

function MetricsTable({ metrics }: { metrics: MetricsResult }) {
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
              [
                "Detection Rate",
                (metrics.detection_rate * 100).toFixed(1) + "%",
              ],
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

function ResultView({
  result,
  onReset,
}: {
  result: JobResultResponse;
  onReset: () => void;
}) {
  const lowDetection = result.metrics.detection_rate < 0.4;

  return (
    <div className="space-y-6">
      {/* Warning banner */}
      {lowDetection && (
        <div className="rounded-lg border border-yellow-600 bg-yellow-950/40 px-4 py-3 text-sm text-yellow-300">
          <strong>Low pose detection rate</strong> (
          {(result.metrics.detection_rate * 100).toFixed(1)}%). Results may be
          less accurate — try a video with better lighting or less occlusion.
        </div>
      )}

      {/* Annotated video */}
      <div className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
          Annotated Video
        </h2>
        <video
          src={result.annotated_video_url}
          controls
          className="w-full rounded-lg bg-black"
          style={{ maxHeight: "480px" }}
        />
        <a
          href={result.annotated_video_url}
          download
          className="inline-flex items-center gap-1.5 rounded-md bg-gray-800 px-3 py-1.5 text-xs font-medium text-gray-200 hover:bg-gray-700"
        >
          <svg
            className="h-3.5 w-3.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"
            />
          </svg>
          Download annotated video
        </a>
      </div>

      {/* Coaching tabs */}
      <div className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
          Coaching Feedback
        </h2>
        <CoachingPanel report={result.coaching_report} />
      </div>

      {/* Raw metrics */}
      <MetricsTable metrics={result.metrics} />

      {/* Analyze another */}
      <button
        onClick={onReset}
        className="w-full rounded-lg border border-gray-600 px-4 py-2.5 text-sm font-medium text-gray-300 transition-colors hover:border-gray-400 hover:text-white"
      >
        Analyze another video
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Home() {
  const { state, file, setFile, analyze, reset } = useTennisCoach();

  const handleFile = useCallback(
    (f: File) => {
      setFile(f);
    },
    [setFile]
  );

  const isActive =
    state.phase === "uploading" || state.phase === "polling";

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      {/* Header */}
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold tracking-tight text-white">
          AI Tennis Coach
        </h1>
        <p className="mt-2 text-sm text-gray-400">
          Upload a video clip for instant pose analysis and coaching feedback
        </p>
      </div>

      {/* Content */}
      {state.phase === "completed" ? (
        <ResultView result={state.result} onReset={reset} />
      ) : state.phase === "failed" ? (
        <div className="space-y-4">
          <div className="rounded-lg border border-red-700 bg-red-950/40 px-4 py-3 text-sm text-red-300">
            <strong>Error:</strong> {state.error}
          </div>
          <button
            onClick={reset}
            className="w-full rounded-lg border border-gray-600 px-4 py-2.5 text-sm font-medium text-gray-300 hover:border-gray-400 hover:text-white"
          >
            Try again
          </button>
        </div>
      ) : (
        <div className="space-y-6 rounded-2xl bg-gray-900 p-6 shadow-xl ring-1 ring-gray-700/50">
          <UploadZone
            file={file}
            onFile={handleFile}
            onAnalyze={() => file && analyze(file)}
            disabled={isActive}
          />

          {(state.phase === "uploading" || state.phase === "polling") && (
            <ProgressBar
              progress={state.progress}
              message={
                state.phase === "uploading"
                  ? "Uploading…"
                  : state.message
              }
            />
          )}
        </div>
      )}
    </main>
  );
}
