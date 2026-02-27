"use client";

import { useCallback, useEffect, useState } from "react";
import {
  listSessions,
  compareSessions,
  type SessionSummary,
  type MetricDelta,
  type DeltaCoachingReport,
  type CompareResponse,
} from "@/lib/api";
import { useAuthContext } from "@/lib/auth-context";
import { Spinner, ErrorBanner, SignInPrompt } from "@/components/shared";

// ---------------------------------------------------------------------------
// MetricDeltaTable
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

// ---------------------------------------------------------------------------
// DeltaCoachingPanel
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// CompareTab
// ---------------------------------------------------------------------------

function CompareTab({ token, userId }: { token: string; userId: string }) {
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
              <option key={s.session_id} value={s.session_id} disabled={s.session_id === sessionBId}>
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
              <option key={s.session_id} value={s.session_id} disabled={s.session_id === sessionAId}>
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
// Page
// ---------------------------------------------------------------------------

export default function ComparePage() {
  const { token, user, signIn } = useAuthContext();

  if (!token || !user) {
    return (
      <SignInPrompt
        label="Sign in to compare sessions"
        onSignIn={signIn}
      />
    );
  }

  return <CompareTab token={token} userId={user.user_id} />;
}
