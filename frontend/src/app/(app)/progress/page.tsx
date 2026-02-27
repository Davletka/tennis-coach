"use client";

import { useEffect, useState } from "react";
import { getProgress, type ProgressDataPoint } from "@/lib/api";
import { useAuthContext } from "@/lib/auth-context";
import { Spinner, ErrorBanner, SignInPrompt } from "@/components/shared";

// ---------------------------------------------------------------------------
// SparklineChart
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

// ---------------------------------------------------------------------------
// ProgressTab
// ---------------------------------------------------------------------------

function ProgressTab({ token, userId }: { token: string; userId: string }) {
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
// Page
// ---------------------------------------------------------------------------

export default function ProgressPage() {
  const { token, user, signIn } = useAuthContext();

  if (!token || !user) {
    return (
      <SignInPrompt
        label="Sign in to view your progress"
        onSignIn={signIn}
      />
    );
  }

  return <ProgressTab token={token} userId={user.user_id} />;
}
