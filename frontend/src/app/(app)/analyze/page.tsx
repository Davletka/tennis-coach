"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import {
  uploadVideo,
  uploadReferenceVideo,
  retryJob,
  getJobStatus,
  getJobResult,
  type JobResultResponse,
  type ReferencePoseResult,
  type TargetAngles,
} from "@/lib/api";
import { useAuthContext } from "@/lib/auth-context";
import {
  CoachingPanel,
  MetricsTable,
  SwingCard,
  Spinner,
} from "@/components/shared";

// ---------------------------------------------------------------------------
// State machine
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
// useCourtCoach hook
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
    async (f: File, activity = "tennis") => {
      if (!tokenRef.current) {
        dispatch({ type: "FAIL", error: "Please sign in to analyze a video." });
        return;
      }
      dispatch({ type: "UPLOAD_START" });
      try {
        const { job_id } = await uploadVideo(f, tokenRef.current, activity);
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
// UploadZone
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

// ---------------------------------------------------------------------------
// ProgressBar
// ---------------------------------------------------------------------------

function ProgressBar({ progress, message }: { progress: number; message: string }) {
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

// ---------------------------------------------------------------------------
// Pose overlay drawing helpers
// ---------------------------------------------------------------------------

const POSE_CONNECTIONS: [number, number][] = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24],
  [23, 25], [25, 27], [24, 26], [26, 28],
];

const CONNECTION_ANGLE_KEY: Record<string, keyof TargetAngles> = {
  "11,13": "left_shoulder", "13,15": "left_elbow",
  "12,14": "right_shoulder", "14,16": "right_elbow",
  "23,25": "left_knee",  "25,27": "left_knee",
  "24,26": "right_knee", "26,28": "right_knee",
  "11,12": "right_shoulder", "11,23": "left_shoulder",
  "12,24": "right_shoulder", "23,24": "right_knee",
};

function formatTime(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

import type { FrameData } from "@/lib/api";

function drawDiff(
  canvas: HTMLCanvasElement,
  fd: FrameData | undefined,
  bbox: { x: number; y: number; w: number; h: number },
  result: JobResultResponse,
  refPose: ReferencePoseResult | null,
  showGhost: boolean,
  showLabels: boolean,
  swingFrames: Set<number>,
  fi: number,
  eventLabel = "EVENT",
) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const W = canvas.width;
  const H = canvas.height;
  ctx.fillStyle = "#111";
  ctx.fillRect(0, 0, W, H);
  if (!fd?.lm) return;

  const targets = result.coaching_report.target_angles;

  function toCanvas(lx: number, ly: number): [number, number] {
    return [((lx - bbox.x) / bbox.w) * W, ((ly - bbox.y) / bbox.h) * H];
  }

  const angleOfJoint: Record<keyof TargetAngles, number | null> = {
    right_elbow: fd.re,
    left_elbow: fd.le,
    right_shoulder: fd.rs,
    left_shoulder: fd.ls,
    right_knee: fd.rk,
    left_knee: fd.lk,
  };

  function deviationColor(key: keyof TargetAngles): string {
    const current = angleOfJoint[key];
    const target = targets?.[key] ?? null;
    if (current === null || target === null) return "rgba(150,150,150,0.6)";
    const diff = Math.abs(current - target);
    if (diff < 15) return "rgba(0,255,120,0.9)";
    if (diff < 30) return "rgba(255,200,0,0.9)";
    return "rgba(255,70,70,0.9)";
  }

  if (showGhost && refPose) {
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = "rgba(100,150,255,0.45)";
    ctx.lineWidth = 2;
    for (const [a, b] of POSE_CONNECTIONS) {
      const pa = refPose.avg_landmarks[a];
      const pb = refPose.avg_landmarks[b];
      if (!pa || !pb) continue;
      const [ax, ay] = toCanvas(pa[0], pa[1]);
      const [bx, by] = toCanvas(pb[0], pb[1]);
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
      ctx.stroke();
    }
    ctx.setLineDash([]);
  }

  ctx.lineWidth = 2.5;
  for (const [a, b] of POSE_CONNECTIONS) {
    const ptA = fd.lm[a];
    const ptB = fd.lm[b];
    if (!ptA || !ptB) continue;
    const key = CONNECTION_ANGLE_KEY[`${a},${b}`] as keyof TargetAngles | undefined;
    ctx.strokeStyle = key ? deviationColor(key) : "rgba(150,150,150,0.6)";
    ctx.beginPath();
    const [ax, ay] = toCanvas(ptA[0], ptA[1]);
    const [bx, by] = toCanvas(ptB[0], ptB[1]);
    ctx.moveTo(ax, ay);
    ctx.lineTo(bx, by);
    ctx.stroke();
  }

  ctx.fillStyle = "rgba(255,255,255,0.8)";
  for (const pt of fd.lm) {
    if (!pt) continue;
    const [cx, cy] = toCanvas(pt[0], pt[1]);
    ctx.beginPath();
    ctx.arc(cx, cy, 3, 0, Math.PI * 2);
    ctx.fill();
  }

  if (showLabels && targets) {
    const labelMap: [number, number | null, keyof TargetAngles, string][] = [
      [14, fd.re, "right_elbow", "RE"],
      [13, fd.le, "left_elbow", "LE"],
      [12, fd.rs, "right_shoulder", "RS"],
      [11, fd.ls, "left_shoulder", "LS"],
      [26, fd.rk, "right_knee", "RK"],
      [25, fd.lk, "left_knee", "LK"],
    ];
    ctx.font = "bold 10px monospace";
    ctx.shadowColor = "black";
    ctx.shadowBlur = 3;
    for (const [lmIdx, current, key, label] of labelMap) {
      const pt = fd.lm[lmIdx];
      if (!pt || current === null) continue;
      const target = targets[key] ?? null;
      const [cx, cy] = toCanvas(pt[0], pt[1]);
      let text = `${label}:${current.toFixed(0)}°`;
      if (target !== null) {
        const delta = target - current;
        text += ` (${delta >= 0 ? "↑" : "↓"}${Math.abs(delta).toFixed(0)}°)`;
      }
      ctx.fillStyle = deviationColor(key).replace("0.9", "1");
      ctx.fillText(text, cx + 5, cy - 5);
    }
    ctx.shadowBlur = 0;
  }

  if (swingFrames.has(fi)) {
    ctx.strokeStyle = "rgb(255,165,0)";
    ctx.lineWidth = 3;
    ctx.strokeRect(2, 2, W - 4, H - 4);
    ctx.font = "bold 11px sans-serif";
    ctx.fillStyle = "rgb(255,165,0)";
    ctx.shadowBlur = 0;
    const labelW = eventLabel.length * 7 + 8;
    ctx.fillText(eventLabel, W - labelW, 18);
  }
}

// ---------------------------------------------------------------------------
// ResultView
// ---------------------------------------------------------------------------

function ResultView({
  result,
  token,
  onReset,
  onRetry,
}: {
  result: JobResultResponse;
  token: string | null;
  onReset: () => void;
  onRetry: () => void;
}) {
  const lowDetection = result.metrics.detection_rate < 0.4;
  const videoRef = useRef<HTMLVideoElement>(null);
  const videoCanvasRef = useRef<HTMLCanvasElement>(null);
  const diffCanvasRef = useRef<HTMLCanvasElement>(null);
  const bboxRef = useRef({ x: 0, y: 0, w: 1, h: 1 });
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [showGhost, setShowGhost] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [refPose, setRefPose] = useState<ReferencePoseResult | null>(null);
  const [refLoading, setRefLoading] = useState(false);
  const smartPlayRef = useRef(true);
  const seekingRef = useRef(false);

  const swingFrames = useMemo(
    () => new Set(result.metrics.swing_events.map((e) => e.frame_index)),
    [result.metrics.swing_events],
  );

  const duration = result.total_source_frames / result.fps;

  const segments = useMemo(() => {
    if (!result.metrics.swing_events.length) return [];
    const BEFORE = Math.round(result.fps * 1.5);
    const AFTER  = Math.round(result.fps * 2.0);
    const raw = result.metrics.swing_events.map((e) => ({
      start: Math.max(0, (e.frame_index - BEFORE) / result.fps),
      end:   Math.min(duration, (e.frame_index + AFTER)  / result.fps),
    }));
    const sorted = [...raw].sort((a, b) => a.start - b.start);
    const merged: { start: number; end: number }[] = [];
    for (const s of sorted) {
      const last = merged[merged.length - 1];
      if (last && s.start <= last.end + 0.5) {
        last.end = Math.max(last.end, s.end);
      } else {
        merged.push({ ...s });
      }
    }
    return merged;
  }, [result, duration]);

  const segmentsRef = useRef(segments);
  useEffect(() => { segmentsRef.current = segments; }, [segments]);

  useEffect(() => {
    const vc = videoCanvasRef.current;
    const dc = diffCanvasRef.current;
    if (!vc || !dc) return;
    const sync = () => {
      vc.width = vc.clientWidth;
      vc.height = vc.clientHeight;
      dc.width = dc.clientWidth;
      dc.height = dc.clientHeight;
    };
    const ro = new ResizeObserver(sync);
    ro.observe(vc);
    ro.observe(dc);
    sync();
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    const vc = videoCanvasRef.current;
    const dc = diffCanvasRef.current;
    if (!video || !vc || !dc) return;
    const SMOOTH = 0.12;
    let rafId: number;

    function tick() {
      rafId = requestAnimationFrame(tick);
      if (!video || !vc || !dc) return;
      const fi = Math.min(
        Math.floor(video.currentTime * result.fps),
        result.frame_data.length - 1,
      );
      const fd = result.frame_data[fi];

      if (fd?.lm) {
        const pts = fd.lm.filter(Boolean) as [number, number, number][];
        if (pts.length) {
          const pad = 0.15;
          const xs = pts.map((p) => p[0]);
          const ys = pts.map((p) => p[1]);
          const minX = Math.max(0, Math.min(...xs) - pad);
          const minY = Math.max(0, Math.min(...ys) - pad);
          const maxX = Math.min(1, Math.max(...xs) + pad);
          const maxY = Math.min(1, Math.max(...ys) + pad);
          const nb = { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
          const b = bboxRef.current;
          bboxRef.current = {
            x: b.x + (nb.x - b.x) * SMOOTH,
            y: b.y + (nb.y - b.y) * SMOOTH,
            w: b.w + (nb.w - b.w) * SMOOTH,
            h: b.h + (nb.h - b.h) * SMOOTH,
          };
        }
      }
      const bbox = bboxRef.current;

      const vctx = vc.getContext("2d");
      if (vctx) {
        vctx.clearRect(0, 0, vc.width, vc.height);
        if (video.readyState >= 2) {
          const vw = video.videoWidth;
          const vh = video.videoHeight;
          vctx.drawImage(
            video,
            bbox.x * vw, bbox.y * vh, bbox.w * vw, bbox.h * vh,
            0, 0, vc.width, vc.height,
          );
        }
      }

      const evtLabel = (result.event_singular ?? "swing").toUpperCase();
      drawDiff(dc, fd, bbox, result, refPose, showGhost, showLabels, swingFrames, fi, evtLabel);
    }

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [result, refPose, showGhost, showLabels, swingFrames]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onTime = () => {
      setCurrentTime(video.currentTime);
      if (!smartPlayRef.current || !segmentsRef.current.length || seekingRef.current) return;
      const t = video.currentTime;
      const segs = segmentsRef.current;
      const inSeg = segs.find((s) => t >= s.start - 0.05 && t <= s.end);
      if (inSeg) {
        if (Math.abs(video.playbackRate - 0.4) > 0.01) video.playbackRate = 0.4;
      } else {
        const next = segs.find((s) => s.start > t);
        if (next) {
          seekingRef.current = true;
          video.currentTime = next.start;
        } else {
          video.pause();
        }
      }
    };
    const onSeeked = () => { seekingRef.current = false; };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    video.addEventListener("timeupdate", onTime);
    video.addEventListener("seeked", onSeeked);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    return () => {
      video.removeEventListener("timeupdate", onTime);
      video.removeEventListener("seeked", onSeeked);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
    };
  }, []);

  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      if (smartPlayRef.current && segmentsRef.current.length) {
        const t = video.currentTime;
        const segs = segmentsRef.current;
        const inSeg = segs.some((s) => t >= s.start - 0.05 && t <= s.end);
        if (!inSeg) {
          const next = segs.find((s) => s.start > t) ?? segs[0];
          video.currentTime = next.start;
        }
      }
      video.play();
    } else {
      video.pause();
    }
  }, []);

  const seekTo = useCallback((t: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = t;
    video.pause();
  }, []);

  const handleRefUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0];
      if (!f || !token) return;
      setRefLoading(true);
      try {
        const rp = await uploadReferenceVideo(f, token);
        setRefPose(rp);
      } catch (err) {
        console.error("Reference upload failed:", err);
      } finally {
        setRefLoading(false);
        e.target.value = "";
      }
    },
    [token],
  );

  return (
    <div className="space-y-6">
      {lowDetection && (
        <div className="rounded-lg border border-yellow-600 bg-yellow-950/40 px-4 py-3 text-sm text-yellow-300">
          <strong>Low pose detection rate</strong> (
          {(result.metrics.detection_rate * 100).toFixed(1)}%). Results may be
          less accurate — try a video with better lighting or less occlusion.
        </div>
      )}

      <video ref={videoRef} src={result.input_video_url} className="hidden" preload="auto" muted />

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">
            Zoomed View
          </h2>
          <canvas
            ref={videoCanvasRef}
            className="block w-full rounded-lg bg-black"
            style={{ aspectRatio: "4/3" }}
          />
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">
              Form Diff
            </h2>
            <div className="flex gap-2 text-xs text-gray-400">
              <label className="flex items-center gap-1 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={showGhost}
                  onChange={(e) => setShowGhost(e.target.checked)}
                  className="accent-blue-400"
                />
                Ghost
              </label>
              <label className="flex items-center gap-1 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={showLabels}
                  onChange={(e) => setShowLabels(e.target.checked)}
                  className="accent-green-400"
                />
                Labels
              </label>
            </div>
          </div>
          <canvas
            ref={diffCanvasRef}
            className="block w-full rounded-lg bg-[#111]"
            style={{ aspectRatio: "4/3" }}
          />
        </div>
      </div>

      <div className="space-y-2">
        <div className="relative h-2 rounded-full bg-gray-700 overflow-hidden">
          {segments.map((s, i) => (
            <div
              key={i}
              className="absolute top-0 h-full bg-green-600/70"
              style={{
                left: `${(s.start / duration) * 100}%`,
                width: `${((s.end - s.start) / duration) * 100}%`,
              }}
            />
          ))}
          <div
            className="absolute top-0 left-0 h-full bg-white/25"
            style={{ width: `${(currentTime / duration) * 100}%` }}
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={togglePlay}
            className="px-3 py-1 rounded bg-gray-700 text-sm text-white hover:bg-gray-600 transition-colors"
          >
            {playing ? "Pause" : "Play"}
          </button>


          <input
            type="range"
            min={0}
            max={duration}
            step={1 / result.fps}
            value={currentTime}
            onChange={(e) => {
              const v = videoRef.current;
              if (v) v.currentTime = +e.target.value;
            }}
            className="flex-1 accent-green-500"
          />
          <span className="text-xs text-gray-400 w-20 text-right tabular-nums">
            {formatTime(currentTime)}
            {playing && segments.length > 0 && (
              <span className="ml-1 text-green-400">0.4×</span>
            )}
          </span>
          <label className="cursor-pointer rounded border border-dashed border-gray-600 px-3 py-1 text-xs text-gray-400 hover:border-blue-400 hover:text-blue-300 transition-colors whitespace-nowrap">
            {refLoading ? "Processing…" : refPose ? "Reference ✓" : "+ Reference"}
            <input
              type="file"
              accept="video/*"
              className="hidden"
              onChange={handleRefUpload}
            />
          </label>
        </div>
      </div>

      <div className="flex flex-wrap gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-4 h-0.5 bg-green-400 rounded" />
          Good (&lt;15°)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-4 h-0.5 bg-yellow-400 rounded" />
          Off (15–30°)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-4 h-0.5 bg-red-400 rounded" />
          Needs fix (&gt;30°)
        </span>
        {refPose && (
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-4 border-t-2 border-dashed border-blue-400 opacity-60" />
            Reference pose
          </span>
        )}
      </div>

      {result.per_swing_analyses.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
            Per-{(result.event_singular ?? "swing").charAt(0).toUpperCase() + (result.event_singular ?? "swing").slice(1)} Breakdown ({result.per_swing_analyses.length} {result.per_swing_analyses.length !== 1 ? (result.event_plural ?? "swings") : (result.event_singular ?? "swing")})
          </h2>
          {result.per_swing_analyses.map((a) => (
            <SwingCard
              key={a.swing_index}
              analysis={a}
              swingNumber={a.swing_index + 1}
              fps={result.fps}
              onSeek={seekTo}
              labels={result.coaching_labels}
              videoUrl={result.input_video_url}
            />
          ))}
        </div>
      )}

      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
            Coaching Feedback
          </h2>
          {result.coaching_report.session_score > 0 && (
            <div className="flex items-center gap-1.5">
              <span className={`rounded-full px-3 py-0.5 text-sm font-bold tabular-nums ${
                result.coaching_report.session_score >= 80 ? "bg-green-900/60 text-green-300" :
                result.coaching_report.session_score >= 60 ? "bg-yellow-900/60 text-yellow-300" :
                "bg-red-900/60 text-red-300"
              }`}>
                {result.coaching_report.session_score}
              </span>
              <span className="text-xs text-gray-500">/ 100</span>
            </div>
          )}
        </div>
        <CoachingPanel report={result.coaching_report} labels={result.coaching_labels} />
      </div>

      {result.coaching_report.top_3_priorities.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">
            Top Priorities
          </h2>
          <div className="rounded-xl border border-gray-700 bg-gray-900 p-4">
            <ol className="space-y-1 text-sm text-gray-200">
              {result.coaching_report.top_3_priorities.map((p, i) => (
                <li key={i} className="flex gap-2">
                  <span className="flex-shrink-0 font-bold text-green-400">{i + 1}.</span>
                  <span>{p}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}

      <MetricsTable metrics={result.metrics} />

      <div className="flex gap-3">
        {result.coaching_report.swing_mechanics.startsWith("❌") && (
          <button
            onClick={onRetry}
            className="flex-1 rounded-lg bg-yellow-700 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-yellow-600"
          >
            Re-analyze Coaching
          </button>
        )}
        <button
          onClick={onReset}
          className="flex-1 rounded-lg border border-gray-600 px-4 py-2.5 text-sm font-medium text-gray-300 transition-colors hover:border-gray-400 hover:text-white"
        >
          Analyze another video
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// FeatureCard + LandingPage
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
// Activity choices
// ---------------------------------------------------------------------------

const ACTIVITY_CHOICES = [
  { id: "gym", label: "Gym Workout" },
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AnalyzePage() {
  const { token, user, signIn } = useAuthContext();
  const { state, file, setFile, analyze, retry, reset } = useCourtCoach(token);
  const [selectedActivity, setSelectedActivity] = useState("gym");

  const handleFile = useCallback((f: File) => setFile(f), [setFile]);
  const isActive = state.phase === "uploading" || state.phase === "polling";

  if (state.phase === "completed") {
    return (
      <ResultView
        result={state.result}
        token={token}
        onReset={reset}
        onRetry={() => retry(state.result.job_id)}
      />
    );
  }

  if (state.phase === "failed") {
    return (
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
    );
  }

  if (!user) {
    return <LandingPage onSignIn={signIn} />;
  }

  return (
    <div className="space-y-6 rounded-2xl bg-gray-900 p-6 shadow-xl ring-1 ring-gray-700/50">
      {/* Activity selector */}
      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
          Activity
        </p>
        <div className="flex gap-2">
          {ACTIVITY_CHOICES.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setSelectedActivity(id)}
              className={[
                "rounded-lg border px-4 py-1.5 text-sm font-medium transition-colors",
                selectedActivity === id
                  ? "border-green-600 bg-green-900/40 text-green-300"
                  : "border-gray-600 text-gray-400 hover:border-gray-400 hover:text-gray-200",
              ].join(" ")}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <UploadZone
        file={file}
        onFile={handleFile}
        onAnalyze={() => file && analyze(file, selectedActivity)}
        disabled={isActive}
      />
      {(state.phase === "uploading" || state.phase === "polling") && (
        <div className="space-y-2">
          <ProgressBar
            progress={state.progress}
            message={
              state.phase === "uploading" ? "Uploading…" : state.message
            }
          />
          {state.phase === "polling" && (
            <div className="flex justify-end">
              <button
                onClick={() => retry(state.jobId)}
                className="text-xs text-gray-500 hover:text-yellow-400 transition-colors"
                title="Cancel the current run and restart from the last checkpoint"
              >
                Stuck? Cancel &amp; Retry
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
