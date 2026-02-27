"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  listSessions,
  deleteSession,
  type SessionSummary,
  type SessionListResponse,
} from "@/lib/api";
import { useAuthContext } from "@/lib/auth-context";
import {
  Spinner,
  ErrorBanner,
  SignInPrompt,
  CoachingPanel,
  MetricsTable,
  DetectionBadge,
} from "@/components/shared";

// ---------------------------------------------------------------------------
// Helpers
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

// ---------------------------------------------------------------------------
// SessionCard
// ---------------------------------------------------------------------------

function SessionCard({
  session,
  onDelete,
}: {
  session: SessionSummary;
  onDelete: (sessionId: string) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const inputVideoRef = useRef<HTMLVideoElement>(null);
  const annotatedVideoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  function syncVideos(master: HTMLVideoElement, other: HTMLVideoElement) {
    if (Math.abs(other.currentTime - master.currentTime) > 0.1) {
      other.currentTime = master.currentTime;
    }
  }

  function togglePlay() {
    const a = inputVideoRef.current;
    const b = annotatedVideoRef.current;
    if (!a || !b) return;
    if (playing) {
      a.pause(); b.pause();
    } else {
      b.currentTime = a.currentTime;
      a.play(); b.play();
    }
    setPlaying(!playing);
  }

  function handleSeek(e: React.ChangeEvent<HTMLInputElement>) {
    const t = parseFloat(e.target.value);
    if (inputVideoRef.current) inputVideoRef.current.currentTime = t;
    if (annotatedVideoRef.current) annotatedVideoRef.current.currentTime = t;
    setCurrentTime(t);
  }

  async function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    setDeleting(true);
    try {
      await onDelete(session.session_id);
    } finally {
      setDeleting(false);
      setConfirming(false);
    }
  }

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
          {/* Side-by-side video playback */}
          {session.input_video_url && session.annotated_video_url && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                Playback
              </p>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <p className="mb-1 text-xs text-gray-500 text-center">Original</p>
                  <video
                    ref={inputVideoRef}
                    src={session.input_video_url}
                    className="w-full rounded-lg bg-black"
                    preload="metadata"
                    muted
                    onLoadedMetadata={(e) => setDuration((e.target as HTMLVideoElement).duration)}
                    onTimeUpdate={(e) => {
                      const t = (e.target as HTMLVideoElement).currentTime;
                      setCurrentTime(t);
                      if (annotatedVideoRef.current) syncVideos(e.target as HTMLVideoElement, annotatedVideoRef.current);
                    }}
                    onEnded={() => setPlaying(false)}
                  />
                </div>
                <div>
                  <p className="mb-1 text-xs text-gray-500 text-center">Annotated</p>
                  <video
                    ref={annotatedVideoRef}
                    src={session.annotated_video_url}
                    className="w-full rounded-lg bg-black"
                    preload="metadata"
                    muted
                  />
                </div>
              </div>
              <div className="mt-2 flex items-center gap-3">
                <button
                  onClick={togglePlay}
                  className="flex-shrink-0 rounded-md bg-gray-700 px-3 py-1 text-xs font-medium text-white hover:bg-gray-600"
                >
                  {playing ? "Pause" : "Play"}
                </button>
                <input
                  type="range"
                  min={0}
                  max={duration || 1}
                  step={0.033}
                  value={currentTime}
                  onChange={handleSeek}
                  className="h-1.5 w-full cursor-pointer accent-green-400"
                />
                <span className="flex-shrink-0 text-xs tabular-nums text-gray-500">
                  {Math.floor(currentTime / 60)}:{String(Math.floor(currentTime % 60)).padStart(2, "0")}
                </span>
              </div>
            </div>
          )}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Coaching Feedback
            </p>
            <CoachingPanel report={session.coaching} />
          </div>
          {session.coaching.top_3_priorities.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                Top Priorities
              </p>
              <div className="rounded-xl border border-gray-700 bg-gray-900 p-4">
                <ol className="space-y-1 text-sm text-gray-200">
                  {session.coaching.top_3_priorities.map((p, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="flex-shrink-0 font-bold text-green-400">{i + 1}.</span>
                      <span>{p}</span>
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          )}
          <MetricsTable metrics={session.metrics} />
          <div className="flex justify-end border-t border-gray-700 pt-3">
            {confirming ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">Delete this session?</span>
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="rounded-md bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-500 disabled:opacity-50"
                >
                  {deleting ? "Deleting…" : "Confirm"}
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); setConfirming(false); }}
                  disabled={deleting}
                  className="rounded-md border border-gray-600 px-3 py-1 text-xs font-medium text-gray-300 hover:border-gray-400 disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={(e) => { e.stopPropagation(); setConfirming(true); }}
                className="flex items-center gap-1.5 rounded-md border border-gray-700 px-3 py-1 text-xs font-medium text-gray-400 transition-colors hover:border-red-800 hover:text-red-400"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Delete
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// HistoryTab
// ---------------------------------------------------------------------------

function HistoryTab({ token, userId }: { token: string; userId: string }) {
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

  const handleDelete = useCallback(async (sessionId: string) => {
    await deleteSession(token, userId, sessionId);
    setData((prev) => {
      if (!prev) return prev;
      const sessions = prev.sessions.filter((s) => s.session_id !== sessionId);
      return { ...prev, sessions, total: prev.total - 1 };
    });
  }, [token, userId]);

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
          <SessionCard key={s.session_id} session={s} onDelete={handleDelete} />
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
// Page
// ---------------------------------------------------------------------------

export default function HistoryPage() {
  const { token, user, signIn } = useAuthContext();

  if (!token || !user) {
    return (
      <SignInPrompt
        label="Sign in to view your session history"
        onSignIn={signIn}
      />
    );
  }

  return <HistoryTab token={token} userId={user.user_id} />;
}
