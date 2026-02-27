"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import {
  uploadVideo,
  retryJob,
  getJobStatus,
  getJobResult,
  getMe,
  listSessions,
  getProgress,
  compareSessions,
  type JobResultResponse,
  type AngleStatResult,
  type MetricsResult,
  type UserProfile,
  type SessionSummary,
  type SessionListResponse,
  type ProgressDataPoint,
  type MetricDelta,
  type DeltaCoachingReport,
  type CompareResponse,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// State machine — discriminated union keeps invalid states impossible
// ---------------------------------------------------------------------------

type AppState =
  | { phase: "idle" }
  | { phase: "uploading"; file: File; progress: number }
  | { phase: "polling"; jobId: string; progress: number; message: string }
  | { phase: "completed"; result: JobResultResponse }
  | { phase: "failed"; error: string; jobId?: string };

type AppAction =
  | { type: "SELECT_FILE"; file: File }
  | { type: "UPLOAD_START" }
  | { type: "UPLOAD_DONE"; jobId: string }
  | { type: "POLL_UPDATE"; progress: number; message: string }
  | { type: "COMPLETE"; result: JobResultResponse }
  | { type: "FAIL"; error: string; jobId?: string }
  | { type: "RETRY"; jobId: string }
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
      return { phase: "failed", error: action.error, jobId: action.jobId };
    case "RETRY":
      return { phase: "polling", jobId: action.jobId, progress: 0, message: "Retrying…" };
    case "RESET":
      return { phase: "idle" };
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Upload + polling orchestration hook
// ---------------------------------------------------------------------------

function useCourtCoach(token: string | null) {
  const [state, dispatch] = useReducer(reducer, { phase: "idle" });
  const [file, setFile] = useState<File | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tokenRef = useRef(token);
  useEffect(() => { tokenRef.current = token; }, [token]);

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
          const tok = tokenRef.current!;
          const status = await getJobStatus(jobId, tok);
          if (status.status === "completed") {
            const result = await getJobResult(jobId, tok);
            dispatch({ type: "COMPLETE", result });
          } else if (status.status === "failed") {
            dispatch({ type: "FAIL", error: "Analysis failed on the server.", jobId });
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
      if (!tokenRef.current) {
        dispatch({ type: "FAIL", error: "Please sign in to analyze a video." });
        return;
      }
      dispatch({ type: "UPLOAD_START" });
      try {
        const { job_id } = await uploadVideo(f, tokenRef.current);
        dispatch({ type: "UPLOAD_DONE", jobId: job_id });
        scheduleNextPoll(job_id);
      } catch (err) {
        dispatch({ type: "FAIL", error: String(err) });
      }
    },
    [scheduleNextPoll]
  );

  const retry = useCallback(
    async (jobId: string) => {
      if (!tokenRef.current) return;
      try {
        await retryJob(jobId, tokenRef.current);
        dispatch({ type: "RETRY", jobId });
        scheduleNextPoll(jobId);
      } catch (err) {
        dispatch({ type: "FAIL", error: String(err), jobId });
      }
    },
    [scheduleNextPoll]
  );

  const reset = useCallback(() => {
    stopPolling();
    setFile(null);
    dispatch({ type: "RESET" });
  }, [stopPolling]);

  return { state, file, setFile, analyze, retry, reset };
}

// ---------------------------------------------------------------------------
// Auth hook
// ---------------------------------------------------------------------------

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function useAuth() {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get("token");
    if (urlToken) {
      localStorage.setItem("courtcoach_jwt", urlToken);
      window.history.replaceState({}, "", window.location.pathname);
    }
    const stored = urlToken ?? localStorage.getItem("courtcoach_jwt");
    if (!stored) {
      setLoading(false);
      return;
    }
    setToken(stored);
    getMe(stored)
      .then((u) => setUser(u))
      .catch(() => {
        localStorage.removeItem("courtcoach_jwt");
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem("courtcoach_jwt");
    setToken(null);
    setUser(null);
  }, []);

  const signIn = useCallback(() => {
    window.location.href = `${API_BASE_URL}/auth/google`;
  }, []);

  return { token, user, loading, signIn, signOut };
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

type Tab = "analyze" | "history" | "compare" | "progress";

function NavBar({
  activeTab,
  onTabChange,
  user,
  onSignIn,
  onSignOut,
}: {
  activeTab: Tab;
  onTabChange: (t: Tab) => void;
  user: UserProfile | null;
  onSignIn: () => void;
  onSignOut: () => void;
}) {
  const tabs: { key: Tab; label: string }[] = [
    { key: "analyze", label: "Analyze" },
    { key: "history", label: "History" },
    { key: "compare", label: "Compare" },
    { key: "progress", label: "Progress" },
  ];

  return (
    <header className="mb-8">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            CourtCoach
          </h1>
          <p className="text-xs text-gray-500">
            Pose analysis &amp; coaching feedback
          </p>
        </div>
        {user ? (
          <div className="flex items-center gap-3">
            {user.picture && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={user.picture}
                alt={user.name}
                className="h-8 w-8 rounded-full"
                referrerPolicy="no-referrer"
              />
            )}
            <div className="text-right">
              <p className="text-xs font-medium text-gray-200">{user.name}</p>
              <button
                onClick={onSignOut}
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Sign out
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={onSignIn}
            className="flex items-center gap-2 rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm font-medium text-gray-200 hover:border-gray-400 hover:bg-gray-700 transition-colors"
          >
            <svg className="h-4 w-4 flex-shrink-0" viewBox="0 0 24 24">
              <path
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                fill="#4285F4"
              />
              <path
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                fill="#34A853"
              />
              <path
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
                fill="#FBBC05"
              />
              <path
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                fill="#EA4335"
              />
            </svg>
            Sign in
          </button>
        )}
      </div>

      <div className="flex border-b border-gray-700">
        {tabs.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => onTabChange(key)}
            className={[
              "px-4 py-2.5 text-sm font-medium transition-colors",
              activeTab === key
                ? "border-b-2 border-green-500 text-green-400"
                : "text-gray-400 hover:text-gray-200",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>
    </header>
  );
}

function SignInPrompt({
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

function Spinner() {
  return (
    <div className="flex justify-center py-12">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-600 border-t-green-500" />
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-700 bg-red-950/40 px-4 py-3 text-sm text-red-300">
      <strong>Error:</strong> {message}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Analyze sub-components (unchanged)
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
              Drag &amp; drop a video, or{" "}
              <span className="text-green-400 underline">browse</span>
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
  report: {
    swing_mechanics: string;
    footwork_movement: string;
    stance_posture: string;
    shot_selection_tactics: string;
    top_3_priorities: string[];
  };
}) {
  const [activeTab, setActiveTab] = useState<CoachingKey>("swing_mechanics");

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-700">
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

      <div className="p-4 text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">
        {report[activeTab] || <span className="text-gray-500 italic">No data.</span>}
      </div>

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
      {lowDetection && (
        <div className="rounded-lg border border-yellow-600 bg-yellow-950/40 px-4 py-3 text-sm text-yellow-300">
          <strong>Low pose detection rate</strong> (
          {(result.metrics.detection_rate * 100).toFixed(1)}%). Results may be
          less accurate — try a video with better lighting or less occlusion.
        </div>
      )}

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

      <div className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
          Coaching Feedback
        </h2>
        <CoachingPanel report={result.coaching_report} />
      </div>

      <MetricsTable metrics={result.metrics} />

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
// History tab
// ---------------------------------------------------------------------------

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return (
    d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    }) +
    " · " +
    d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
  );
}

function DetectionBadge({ rate }: { rate: number }) {
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

function SessionCard({ session }: { session: SessionSummary }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900">
      <button
        onClick={() => setExpanded((o) => !o)}
        className="flex w-full items-start gap-4 rounded-xl p-4 text-left transition-colors hover:bg-gray-800/50"
      >
        <div className="mt-0.5 flex-shrink-0 rounded-lg bg-gray-800 p-2">
          <svg
            className="h-5 w-5 text-gray-400"
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
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-gray-200">
            {session.original_filename}
          </p>
          <p className="mt-0.5 text-xs text-gray-500">
            {fmtDate(session.recorded_at)}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <DetectionBadge rate={session.detection_rate} />
            <span className="text-xs text-gray-500">
              {session.metrics.swing_count}{" "}
              swing{session.metrics.swing_count !== 1 ? "s" : ""}
            </span>
            <span className="text-xs text-gray-500">
              {session.frames_analyzed} frames
            </span>
          </div>
        </div>
        <svg
          className={`mt-1 h-4 w-4 flex-shrink-0 text-gray-500 transition-transform ${
            expanded ? "rotate-180" : ""
          }`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="space-y-4 border-t border-gray-700 p-4">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Coaching Feedback
            </p>
            <CoachingPanel report={session.coaching} />
          </div>
          <MetricsTable metrics={session.metrics} />
        </div>
      )}
    </div>
  );
}

function HistoryTab({
  token,
  userId,
}: {
  token: string;
  userId: string;
}) {
  const [data, setData] = useState<SessionListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    listSessions(token, userId, 10, 0)
      .then(setData)
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [token, userId]);

  const loadMore = useCallback(async () => {
    if (!data) return;
    setLoadingMore(true);
    try {
      const more = await listSessions(token, userId, 10, data.sessions.length);
      setData({ ...more, sessions: [...data.sessions, ...more.sessions] });
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setLoadingMore(false);
    }
  }, [data, token, userId]);

  if (loading) return <Spinner />;
  if (error) return <ErrorBanner message={error} />;

  if (!data || data.sessions.length === 0) {
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
            d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <p className="text-sm font-medium text-gray-400">No sessions yet</p>
        <p className="mt-1 text-xs text-gray-600">
          Analyze a video to start tracking your progress
        </p>
      </div>
    );
  }

  const hasMore = data.sessions.length < data.total;

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">
        {data.total} session{data.total !== 1 ? "s" : ""} total
      </p>
      <div className="space-y-3">
        {data.sessions.map((s) => (
          <SessionCard key={s.id} session={s} />
        ))}
      </div>
      {hasMore && (
        <button
          onClick={loadMore}
          disabled={loadingMore}
          className="w-full rounded-lg border border-gray-600 px-4 py-2.5 text-sm font-medium text-gray-300 transition-colors hover:border-gray-400 hover:text-white disabled:opacity-50"
        >
          {loadingMore
            ? "Loading…"
            : `Load more (${data.total - data.sessions.length} remaining)`}
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Compare tab
// ---------------------------------------------------------------------------

function directionIcon(direction: MetricDelta["direction"]) {
  if (direction === "improved")
    return <span className="font-bold text-green-400">↑</span>;
  if (direction === "regressed")
    return <span className="font-bold text-red-400">↓</span>;
  return <span className="text-gray-500">→</span>;
}

function fmtMetricName(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtMetricValue(v: number | null, name: string): string {
  if (v === null) return "—";
  if (
    name.includes("elbow") ||
    name.includes("shoulder") ||
    name.includes("knee") ||
    name.includes("torso") ||
    name.includes("rotation")
  ) {
    return v.toFixed(1) + "°";
  }
  if (name === "swing_count") return String(Math.round(v));
  if (name === "detection_rate") return (v * 100).toFixed(0) + "%";
  return v.toFixed(2);
}

function MetricDeltaTable({ deltas }: { deltas: MetricDelta[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-700 bg-gray-900">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-700 text-xs text-gray-500">
            <th className="py-3 pl-4 pr-3 text-left font-medium">Metric</th>
            <th className="py-3 px-3 text-right font-medium">Session A</th>
            <th className="py-3 px-3 text-right font-medium">Session B</th>
            <th className="py-3 px-3 text-right font-medium">Change</th>
            <th className="py-3 pl-3 pr-4 text-center font-medium">Trend</th>
          </tr>
        </thead>
        <tbody>
          {deltas.map((d) => (
            <tr key={d.metric_name} className="border-t border-gray-700/50">
              <td className="py-2.5 pl-4 pr-3 text-gray-300">
                {fmtMetricName(d.metric_name)}
              </td>
              <td className="py-2.5 px-3 text-right tabular-nums text-gray-400">
                {fmtMetricValue(d.session_a_value, d.metric_name)}
              </td>
              <td className="py-2.5 px-3 text-right tabular-nums text-gray-200">
                {fmtMetricValue(d.session_b_value, d.metric_name)}
              </td>
              <td
                className={[
                  "py-2.5 px-3 text-right tabular-nums",
                  d.direction === "improved"
                    ? "text-green-400"
                    : d.direction === "regressed"
                    ? "text-red-400"
                    : "text-gray-500",
                ].join(" ")}
              >
                {d.delta === null
                  ? "—"
                  : (d.delta > 0 ? "+" : "") + d.delta.toFixed(1)}
              </td>
              <td className="py-2.5 pl-3 pr-4 text-center">
                {directionIcon(d.direction)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DeltaCoachingPanel({ report }: { report: DeltaCoachingReport }) {
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-700 bg-gray-900 p-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
          Overall Progress
        </p>
        <p className="text-sm leading-relaxed text-gray-200">
          {report.overall_progress_summary}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {report.improvements.length > 0 && (
          <div className="rounded-xl border border-green-800/50 bg-green-950/30 p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-green-400">
              Improvements
            </p>
            <ul className="space-y-1.5">
              {report.improvements.map((item, i) => (
                <li key={i} className="flex gap-2 text-xs text-green-200">
                  <span className="flex-shrink-0 text-green-400">↑</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {report.regressions.length > 0 && (
          <div className="rounded-xl border border-red-800/50 bg-red-950/30 p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-red-400">
              Areas of Concern
            </p>
            <ul className="space-y-1.5">
              {report.regressions.map((item, i) => (
                <li key={i} className="flex gap-2 text-xs text-red-200">
                  <span className="flex-shrink-0 text-red-400">↓</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {report.unchanged_areas.length > 0 && (
        <div className="rounded-xl border border-gray-700 bg-gray-900 p-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
            Unchanged
          </p>
          <ul className="space-y-1 text-xs text-gray-400">
            {report.unchanged_areas.map((item, i) => (
              <li key={i} className="flex gap-2">
                <span className="flex-shrink-0">→</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.top_3_priorities.length > 0 && (
        <div className="rounded-xl border border-gray-700 bg-gray-900 p-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
            Top Priorities
          </p>
          <ol className="space-y-1.5 text-sm text-gray-200">
            {report.top_3_priorities.map((p, i) => (
              <li key={i} className="flex gap-2">
                <span className="flex-shrink-0 font-bold text-green-400">
                  {i + 1}.
                </span>
                <span>{p}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function CompareTab({
  token,
  userId,
}: {
  token: string;
  userId: string;
}) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [sessionAId, setSessionAId] = useState("");
  const [sessionBId, setSessionBId] = useState("");
  const [comparing, setComparing] = useState(false);
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSessions(token, userId, 50, 0)
      .then((r) => setSessions(r.sessions))
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setLoadingSessions(false));
  }, [token, userId]);

  const runCompare = useCallback(async () => {
    if (!sessionAId || !sessionBId || sessionAId === sessionBId) return;
    setComparing(true);
    setResult(null);
    setError(null);
    try {
      const res = await compareSessions(token, userId, sessionAId, sessionBId);
      setResult(res);
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setComparing(false);
    }
  }, [token, userId, sessionAId, sessionBId]);

  function sessionLabel(s: SessionSummary): string {
    const date = new Date(s.recorded_at).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
    const name =
      s.original_filename.length > 26
        ? s.original_filename.slice(0, 24) + "…"
        : s.original_filename;
    return `${name} (${date})`;
  }

  if (loadingSessions) return <Spinner />;

  if (sessions.length < 2) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-gray-700 bg-gray-900/50 py-16 text-center">
        <p className="text-sm font-medium text-gray-400">Not enough sessions</p>
        <p className="mt-1 text-xs text-gray-600">
          You need at least 2 sessions to compare. Analyze more videos to get
          started.
        </p>
      </div>
    );
  }

  const canCompare =
    sessionAId && sessionBId && sessionAId !== sessionBId && !comparing;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-xs font-medium text-gray-400">
            Session A
          </label>
          <select
            value={sessionAId}
            onChange={(e) => setSessionAId(e.target.value)}
            className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-green-500 focus:outline-none"
          >
            <option value="">Select session…</option>
            {sessions.map((s) => (
              <option key={s.id} value={s.id} disabled={s.id === sessionBId}>
                {sessionLabel(s)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-gray-400">
            Session B
          </label>
          <select
            value={sessionBId}
            onChange={(e) => setSessionBId(e.target.value)}
            className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-green-500 focus:outline-none"
          >
            <option value="">Select session…</option>
            {sessions.map((s) => (
              <option key={s.id} value={s.id} disabled={s.id === sessionAId}>
                {sessionLabel(s)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <button
        onClick={runCompare}
        disabled={!canCompare}
        className="w-full rounded-lg bg-green-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-green-500 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {comparing ? "Comparing…" : "Run Comparison"}
      </button>

      {error && <ErrorBanner message={error} />}

      {result && (
        <div className="space-y-6">
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Metric Changes
            </p>
            <MetricDeltaTable deltas={result.metric_deltas} />
          </div>
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
              AI Coaching Analysis
            </p>
            <DeltaCoachingPanel report={result.delta_coaching_report} />
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Progress tab
// ---------------------------------------------------------------------------

const CHART_W = 300;
const CHART_H = 90;
const CHART_PAD = 8;

function SparklineChart({
  label,
  points,
  unit = "",
}: {
  label: string;
  points: Array<{ date: string; value: number | null }>;
  unit?: string;
}) {
  const valid = points
    .filter((p): p is { date: string; value: number } => p.value !== null)
    .slice(-20);

  if (valid.length < 2) {
    return (
      <div className="rounded-lg border border-gray-700 bg-gray-900 p-4">
        <p className="mb-2 text-xs font-medium text-gray-400">{label}</p>
        <p className="text-xs italic text-gray-600">Not enough data</p>
      </div>
    );
  }

  const vals = valid.map((p) => p.value);
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const range = maxV - minV || 1;

  const toX = (i: number) =>
    CHART_PAD + (i / (valid.length - 1)) * (CHART_W - CHART_PAD * 2);
  const toY = (v: number) =>
    CHART_H - CHART_PAD - ((v - minV) / range) * (CHART_H - CHART_PAD * 2);

  const pathD = valid
    .map(
      (p, i) =>
        `${i === 0 ? "M" : "L"} ${toX(i).toFixed(1)} ${toY(p.value).toFixed(1)}`
    )
    .join(" ");

  const fillD =
    pathD +
    ` L ${toX(valid.length - 1).toFixed(1)} ${CHART_H - CHART_PAD} L ${CHART_PAD} ${CHART_H - CHART_PAD} Z`;

  const latest = valid[valid.length - 1].value;
  const trend = latest - valid[0].value;
  const showTrend = Math.abs(trend) >= 0.5;

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-900 p-4">
      <div className="mb-2 flex items-start justify-between">
        <p className="text-xs font-medium text-gray-400">{label}</p>
        <div className="text-right">
          <span className="text-sm font-semibold text-white">
            {latest.toFixed(1)}
            {unit}
          </span>
          {showTrend && (
            <span
              className={[
                "ml-1.5 text-xs",
                trend > 0 ? "text-green-400" : "text-red-400",
              ].join(" ")}
            >
              {trend > 0 ? "+" : ""}
              {trend.toFixed(1)}
              {unit}
            </span>
          )}
        </div>
      </div>

      <svg
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        className="w-full"
        style={{ height: 60 }}
        aria-hidden
      >
        <path d={fillD} fill="rgba(34,197,94,0.08)" />
        <path d={pathD} fill="none" stroke="#22c55e" strokeWidth={1.5} />
        {valid.map((p, i) => (
          <circle
            key={i}
            cx={toX(i).toFixed(1)}
            cy={toY(p.value).toFixed(1)}
            r={2}
            fill="#22c55e"
          />
        ))}
        <circle
          cx={toX(valid.length - 1).toFixed(1)}
          cy={toY(latest).toFixed(1)}
          r={3.5}
          fill="#22c55e"
          stroke="#111827"
          strokeWidth={1.5}
        />
      </svg>

      <p className="mt-1 text-right text-xs text-gray-600">
        {valid.length} session{valid.length !== 1 ? "s" : ""}
      </p>
    </div>
  );
}

function ProgressTab({
  token,
  userId,
}: {
  token: string;
  userId: string;
}) {
  const [data, setData] = useState<ProgressDataPoint[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProgress(token, userId, 30)
      .then((r) => setData(r.data_points))
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [token, userId]);

  if (loading) return <Spinner />;
  if (error) return <ErrorBanner message={error} />;

  if (!data || data.length < 2) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-gray-700 bg-gray-900/50 py-16 text-center">
        <p className="text-sm font-medium text-gray-400">Not enough data</p>
        <p className="mt-1 text-xs text-gray-600">
          Analyze at least 2 videos to see your progress over time
        </p>
      </div>
    );
  }

  const charts: Array<{
    label: string;
    key: Exclude<keyof ProgressDataPoint, "recorded_at">;
    unit: string;
    scale?: number;
  }> = [
    { label: "Right Elbow Angle", key: "right_elbow_mean", unit: "°" },
    { label: "Left Elbow Angle", key: "left_elbow_mean", unit: "°" },
    { label: "Right Shoulder Angle", key: "right_shoulder_mean", unit: "°" },
    { label: "Left Shoulder Angle", key: "left_shoulder_mean", unit: "°" },
    { label: "Right Knee Angle", key: "right_knee_mean", unit: "°" },
    { label: "Left Knee Angle", key: "left_knee_mean", unit: "°" },
    { label: "Torso Rotation", key: "torso_rotation_mean", unit: "°" },
    { label: "Stance Width", key: "stance_width_mean", unit: "" },
    { label: "Swings per Session", key: "swing_count", unit: "" },
    { label: "Pose Detection Rate", key: "detection_rate", unit: "%", scale: 100 },
  ];

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">
        Last {data.length} session{data.length !== 1 ? "s" : ""}
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {charts.map(({ label, key, unit, scale }) => (
          <SparklineChart
            key={key}
            label={label}
            unit={unit}
            points={data.map((d) => {
              const raw: number | null = d[key];
              return {
                date: d.recorded_at,
                value: raw !== null && scale ? raw * scale : raw,
              };
            })}
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Landing page (unauthenticated)
// ---------------------------------------------------------------------------

function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900 p-5">
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-green-600/10 text-green-400">
        {icon}
      </div>
      <p className="mb-1 text-sm font-semibold text-gray-100">{title}</p>
      <p className="text-xs leading-relaxed text-gray-400">{description}</p>
    </div>
  );
}

function LandingPage({ onSignIn }: { onSignIn: () => void }) {
  return (
    <div className="space-y-10 py-4">
      {/* Hero */}
      <div className="space-y-5 text-center">
        <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-2xl bg-green-600/10 ring-1 ring-green-500/30">
          <svg
            className="h-10 w-10 text-green-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
          >
            <circle cx="12" cy="12" r="10" strokeWidth={1.5} />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6.5 6.5c2.5 2 3.5 5.5 1.5 9M17.5 6.5c-2.5 2-3.5 5.5-1.5 9M6.5 17.5c2-2.5 5.5-3.5 9-1.5M6.5 6.5c2 2.5 5.5 3.5 9 1.5"
            />
          </svg>
        </div>

        <div>
          <h2 className="text-3xl font-bold tracking-tight text-white">
            CourtCoach
          </h2>
          <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-gray-400">
            Upload a video of your swing and get instant pose analysis,
            annotated footage, and personalised coaching feedback powered by
            Claude AI.
          </p>
        </div>

        <button
          onClick={onSignIn}
          className="inline-flex items-center gap-2.5 rounded-xl bg-green-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-green-900/30 transition-colors hover:bg-green-500"
        >
          <svg className="h-4 w-4 flex-shrink-0" viewBox="0 0 24 24">
            <path
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              fill="#fff"
              fillOpacity=".9"
            />
            <path
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              fill="#fff"
              fillOpacity=".9"
            />
            <path
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
              fill="#fff"
              fillOpacity=".9"
            />
            <path
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              fill="#fff"
              fillOpacity=".9"
            />
          </svg>
          Sign in with Google to get started
        </button>
      </div>

      {/* How it works */}
      <div>
        <p className="mb-4 text-center text-xs font-semibold uppercase tracking-widest text-gray-500">
          How it works
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <FeatureCard
            icon={
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} className="h-5 w-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
              </svg>
            }
            title="Upload Your Video"
            description="Drop in any MP4, MOV, or AVI clip of your tennis stroke — practice session or match footage."
          />
          <FeatureCard
            icon={
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} className="h-5 w-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M17.982 18.725A7.488 7.488 0 0012 15.75a7.488 7.488 0 00-5.982 2.975m11.963 0a9 9 0 10-11.963 0m11.963 0A8.966 8.966 0 0112 21a8.966 8.966 0 01-5.982-2.275M15 9.75a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            }
            title="Pose Detection"
            description="MediaPipe tracks 33 body landmarks frame-by-frame, measuring joint angles, torso rotation, and swing timing."
          />
          <FeatureCard
            icon={
              <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} className="h-5 w-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
              </svg>
            }
            title="AI Coaching"
            description="Claude AI analyses your swing mechanics, footwork, stance, and tactics, then gives you prioritised, actionable feedback."
          />
        </div>
      </div>

      {/* Progress pitch */}
      <div className="rounded-xl border border-gray-700 bg-gray-900/60 px-6 py-5 text-center">
        <p className="text-sm font-medium text-gray-200">
          Track your improvement over time
        </p>
        <p className="mt-1.5 text-xs text-gray-500">
          Every session is saved to your profile. Compare sessions, view
          sparkline charts of your joint angles, and watch your game evolve.
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Home() {
  const { token, user, loading: authLoading, signIn, signOut } = useAuth();
  const { state, file, setFile, analyze, retry, reset } = useCourtCoach(token);
  const [activeTab, setActiveTab] = useState<Tab>("analyze");

  const handleFile = useCallback((f: File) => setFile(f), [setFile]);

  const isActive = state.phase === "uploading" || state.phase === "polling";

  if (authLoading) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Spinner />
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <NavBar
        activeTab={activeTab}
        onTabChange={(t) => {
          setActiveTab(t);
          if (t === "analyze") reset();
        }}
        user={user}
        onSignIn={signIn}
        onSignOut={signOut}
      />

      {activeTab === "analyze" && (
        <>
          {state.phase === "completed" ? (
            <ResultView result={state.result} onReset={reset} />
          ) : state.phase === "failed" ? (
            <div className="space-y-4">
              <div className="rounded-lg border border-red-700 bg-red-950/40 px-4 py-3 text-sm text-red-300">
                <strong>Error:</strong> {state.error}
              </div>
              <div className="flex gap-3">
                {state.jobId && (
                  <button
                    onClick={() => retry(state.jobId!)}
                    className="flex-1 rounded-lg bg-green-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-green-600 transition-colors"
                  >
                    Retry Analysis
                  </button>
                )}
                <button
                  onClick={reset}
                  className="flex-1 rounded-lg border border-gray-600 px-4 py-2.5 text-sm font-medium text-gray-300 hover:border-gray-400 hover:text-white transition-colors"
                >
                  Start Fresh
                </button>
              </div>
            </div>
          ) : !user ? (
            <LandingPage onSignIn={signIn} />
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
                    state.phase === "uploading" ? "Uploading…" : state.message
                  }
                />
              )}
            </div>
          )}
        </>
      )}

      {activeTab === "history" &&
        (token && user ? (
          <HistoryTab token={token} userId={user.user_id} />
        ) : (
          <SignInPrompt
            label="Sign in to view your session history"
            onSignIn={signIn}
          />
        ))}

      {activeTab === "compare" &&
        (token && user ? (
          <CompareTab token={token} userId={user.user_id} />
        ) : (
          <SignInPrompt
            label="Sign in to compare sessions"
            onSignIn={signIn}
          />
        ))}

      {activeTab === "progress" &&
        (token && user ? (
          <ProgressTab token={token} userId={user.user_id} />
        ) : (
          <SignInPrompt
            label="Sign in to view your progress"
            onSignIn={signIn}
          />
        ))}
    </main>
  );
}
