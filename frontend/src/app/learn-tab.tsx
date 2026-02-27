"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import type React from "react";
import {
  LEARN_CONTENT,
  getLessonByRef,
  countLessons,
  variantLessonId,
  directLessonId,
  planDayId,
  type LearnActivity,
  type LearnModule,
  type Lesson,
  type Variant,
  type WorkoutPlan,
  type PlanDay,
  type ContentBlock,
} from "@/lib/learn-content";
import {
  getLearningProgress,
  markLessonComplete,
  unmarkLessonComplete,
  type UserProfile,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// 3D scene registry — loaded client-side only (ssr: false)
// ---------------------------------------------------------------------------

const HighBounceForehand3D = dynamic(
  () => import("@/components/scenes/HighBounceForehand3D"),
  {
    ssr: false,
    loading: () => (
      <div className="h-80 rounded-xl border border-slate-200 bg-slate-50 flex items-center justify-center">
        <span className="text-sm text-slate-400">Loading 3D scene…</span>
      </div>
    ),
  },
);

const SCENE_REGISTRY: Record<string, React.ComponentType<{ caption?: string }>> = {
  "high-bounce-forehand": HighBounceForehand3D,
};

// ---------------------------------------------------------------------------
// Navigation state machine
// ---------------------------------------------------------------------------

type LearnView =
  | { screen: "sports" }
  | { screen: "modules"; activityId: string }
  | { screen: "variants"; activityId: string; moduleId: string }
  | { screen: "lessons"; activityId: string; moduleId: string; variantId: string }
  | { screen: "lesson"; activityId: string; moduleId: string; variantId: string; lessonId: string }
  | { screen: "plans"; activityId: string; moduleId: string }
  | { screen: "plan-detail"; activityId: string; moduleId: string; planId: string }
  | { screen: "direct-lessons"; activityId: string; moduleId: string }
  | { screen: "direct-lesson"; activityId: string; moduleId: string; lessonId: string };

// ---------------------------------------------------------------------------
// Breadcrumb helper
// ---------------------------------------------------------------------------

function Breadcrumb({ crumbs }: { crumbs: { label: string; onClick: () => void }[] }) {
  return (
    <nav className="flex items-center gap-1 text-sm text-slate-500 mb-6 flex-wrap">
      {crumbs.map((c, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <span className="text-slate-300">›</span>}
          {i < crumbs.length - 1 ? (
            <button
              onClick={c.onClick}
              className="hover:text-slate-900 transition-colors underline-offset-2 hover:underline"
            >
              {c.label}
            </button>
          ) : (
            <span className="text-slate-800 font-medium">{c.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

// ---------------------------------------------------------------------------
// Progress ring — small circular indicator
// ---------------------------------------------------------------------------

function ProgressRing({ done, total, size = 36 }: { done: number; total: number; size?: number }) {
  const r = (size - 4) / 2;
  const circ = 2 * Math.PI * r;
  const pct = total === 0 ? 0 : done / total;
  const dash = pct * circ;
  return (
    <svg width={size} height={size} className="shrink-0">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth="3" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="#22c55e"
        strokeWidth="3"
        strokeDasharray={`${dash} ${circ}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Difficulty badge
// ---------------------------------------------------------------------------

const DIFF_COLORS: Record<string, string> = {
  beginner: "bg-green-100 text-green-700",
  intermediate: "bg-amber-100 text-amber-700",
  advanced: "bg-red-100 text-red-700",
};

function DiffBadge({ level }: { level: string }) {
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${DIFF_COLORS[level] ?? "bg-slate-100 text-slate-600"}`}>
      {level}
    </span>
  );
}

// ---------------------------------------------------------------------------
// ContentBlock renderer
// ---------------------------------------------------------------------------

function ContentBlockView({ block }: { block: ContentBlock }) {
  switch (block.type) {
    case "section-header":
      return (
        <h3 className="text-base font-semibold text-slate-800 mt-6 mb-2 border-b border-slate-100 pb-1">
          {block.text}
        </h3>
      );
    case "text":
      return <p className="text-sm text-slate-700 leading-relaxed mb-3">{block.text}</p>;
    case "key-points":
      return (
        <ul className="mb-4 space-y-1">
          {(block.points ?? []).map((p, i) => (
            <li key={i} className="flex gap-2 text-sm text-slate-700">
              <span className="text-green-500 shrink-0 mt-0.5">✓</span>
              <span>{p}</span>
            </li>
          ))}
        </ul>
      );
    case "tip":
      return (
        <div className="my-3 flex gap-3 bg-amber-50 border border-amber-200 rounded-lg p-3">
          <span className="text-amber-500 shrink-0 text-base mt-0.5">💡</span>
          <p className="text-sm text-amber-800 leading-relaxed">{block.text}</p>
        </div>
      );
    case "svg":
      return (
        <div className="my-4">
          <div
            className="rounded-xl overflow-hidden border border-slate-200"
            dangerouslySetInnerHTML={{ __html: block.svg ?? "" }}
          />
          {block.caption && (
            <p className="text-xs text-slate-500 text-center mt-1.5 italic">{block.caption}</p>
          )}
        </div>
      );
    case "3d-scene": {
      const SceneComponent = block.sceneId ? SCENE_REGISTRY[block.sceneId] : undefined;
      if (!SceneComponent) return null;
      return (
        <div className="my-4">
          <div className="rounded-xl overflow-hidden border border-slate-200">
            <SceneComponent caption={block.caption} />
          </div>
        </div>
      );
    }
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Lesson detail screen
// ---------------------------------------------------------------------------

function LessonDetail({
  lesson,
  lessonId,
  completed,
  onToggle,
  onBack,
}: {
  lesson: Lesson;
  lessonId: string;
  completed: boolean;
  onToggle: (id: string, done: boolean) => void;
  onBack: () => void;
}) {
  const [toggling, setToggling] = useState(false);

  async function handleToggle() {
    setToggling(true);
    try {
      await onToggle(lessonId, !completed);
    } finally {
      setToggling(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900">{lesson.title}</h2>
          <div className="flex items-center gap-2 mt-1">
            <DiffBadge level={lesson.difficulty} />
            {completed && (
              <span className="text-xs text-green-600 font-medium flex items-center gap-1">
                <span>✓</span> Completed
              </span>
            )}
          </div>
        </div>
        <button
          onClick={handleToggle}
          disabled={toggling}
          className={`shrink-0 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            completed
              ? "bg-slate-100 text-slate-600 hover:bg-slate-200"
              : "bg-green-500 text-white hover:bg-green-600"
          } disabled:opacity-50`}
        >
          {toggling ? "…" : completed ? "Mark incomplete" : "Mark complete"}
        </button>
      </div>

      <p className="text-sm text-slate-500 mb-4">{lesson.description}</p>

      <div>
        {lesson.content.map((block, i) => (
          <ContentBlockView key={i} block={block} />
        ))}
      </div>

      <div className="mt-8 pt-4 border-t border-slate-100">
        <button
          onClick={handleToggle}
          disabled={toggling}
          className={`w-full py-3 rounded-xl text-sm font-semibold transition-colors ${
            completed
              ? "bg-slate-100 text-slate-600 hover:bg-slate-200"
              : "bg-green-500 text-white hover:bg-green-600"
          } disabled:opacity-50`}
        >
          {toggling ? "Saving…" : completed ? "✓ Completed — click to undo" : "Mark as Complete"}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lessons list screen (after variant selection)
// ---------------------------------------------------------------------------

function LessonsList({
  lessons,
  buildId: buildLessonId,
  completed,
  onSelect,
}: {
  lessons: Lesson[];
  buildId: (lessonId: string) => string;
  completed: Set<string>;
  onSelect: (lesson: Lesson, lessonId: string) => void;
}) {
  return (
    <div className="space-y-3 max-w-2xl">
      {lessons.map((lesson) => {
        const id = buildLessonId(lesson.id);
        const done = completed.has(id);
        return (
          <button
            key={lesson.id}
            onClick={() => onSelect(lesson, id)}
            className="w-full text-left bg-white border border-slate-200 rounded-xl p-4 hover:border-slate-400 hover:shadow-sm transition-all flex items-center gap-4"
          >
            <div
              className={`w-8 h-8 rounded-full border-2 flex items-center justify-center shrink-0 ${
                done ? "border-green-500 bg-green-500 text-white" : "border-slate-300 text-transparent"
              }`}
            >
              ✓
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="font-medium text-slate-900 text-sm">{lesson.title}</span>
                <DiffBadge level={lesson.difficulty} />
              </div>
              <p className="text-xs text-slate-500 truncate">{lesson.description}</p>
            </div>
            <span className="text-slate-300 shrink-0">›</span>
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Variant selector screen
// ---------------------------------------------------------------------------

function VariantSelector({
  variants,
  completed,
  buildLessonId,
  onSelect,
}: {
  variants: Variant[];
  completed: Set<string>;
  buildLessonId: (variantId: string, lessonId: string) => string;
  onSelect: (variant: Variant) => void;
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl">
      {variants.map((variant) => {
        const total = variant.lessons.length;
        const done = variant.lessons.filter((l) =>
          completed.has(buildLessonId(variant.id, l.id))
        ).length;
        return (
          <button
            key={variant.id}
            onClick={() => onSelect(variant)}
            className="text-left bg-white border border-slate-200 rounded-xl overflow-hidden hover:border-slate-400 hover:shadow-md transition-all"
          >
            {variant.svg && (
              <div
                className="w-full border-b border-slate-100"
                dangerouslySetInnerHTML={{ __html: variant.svg }}
              />
            )}
            <div className="p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-slate-900 text-sm">{variant.title}</span>
                <div className="flex items-center gap-1.5">
                  <ProgressRing done={done} total={total} size={28} />
                  <span className="text-xs text-slate-400">{done}/{total}</span>
                </div>
              </div>
              <p className="text-xs text-slate-500">{variant.subtitle}</p>
            </div>
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Module grid screen
// ---------------------------------------------------------------------------

function ModuleGrid({
  activity,
  completed,
  onSelect,
}: {
  activity: LearnActivity;
  completed: Set<string>;
  onSelect: (mod: LearnModule) => void;
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {activity.modules.map((mod) => {
        let total = 0;
        let done = 0;
        if (mod.type === "variant-select") {
          for (const v of mod.variantGroup.variants) {
            total += v.lessons.length;
            done += v.lessons.filter((l) =>
              completed.has(variantLessonId(activity.id, mod.id, v.id, l.id))
            ).length;
          }
        } else if (mod.type === "lessons") {
          total = mod.lessons.length;
          done = mod.lessons.filter((l) =>
            completed.has(directLessonId(activity.id, mod.id, l.id))
          ).length;
        } else if (mod.type === "plans") {
          for (const plan of mod.plans) {
            total += plan.days.length;
            done += plan.days.filter((d) =>
              completed.has(planDayId(activity.id, mod.id, plan.id, d.id))
            ).length;
          }
        }

        return (
          <button
            key={mod.id}
            onClick={() => onSelect(mod)}
            className="text-left bg-white border border-slate-200 rounded-xl p-5 hover:border-slate-400 hover:shadow-md transition-all"
          >
            <div className="flex items-start justify-between mb-3">
              <span className="text-3xl">{mod.icon}</span>
              <div className="flex items-center gap-1.5">
                <ProgressRing done={done} total={total} size={32} />
                <span className="text-xs text-slate-400 tabular-nums">{done}/{total}</span>
              </div>
            </div>
            <h3 className="font-semibold text-slate-900 mb-1">{mod.title}</h3>
            <p className="text-xs text-slate-500 leading-relaxed">{mod.description}</p>
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sport selector screen
// ---------------------------------------------------------------------------

function SportSelector({
  completed,
  onSelect,
}: {
  completed: Set<string>;
  onSelect: (activity: LearnActivity) => void;
}) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-800 mb-4">What are you training for?</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {LEARN_CONTENT.map((activity) => {
          const total = countLessons(activity);
          const done = Array.from(completed).filter((id) => id.startsWith(`${activity.id}.`)).length;
          return (
            <button
              key={activity.id}
              onClick={() => onSelect(activity)}
              className="text-left rounded-2xl overflow-hidden border border-slate-200 hover:shadow-lg transition-all"
            >
              <div className={`bg-gradient-to-br ${activity.color} p-6`}>
                <span className="text-5xl">{activity.icon}</span>
              </div>
              <div className="bg-white p-4">
                <div className="flex items-center justify-between mb-1">
                  <h3 className="font-bold text-slate-900">{activity.title}</h3>
                  <div className="flex items-center gap-1.5">
                    <ProgressRing done={done} total={total} size={32} />
                    <span className="text-xs text-slate-400 tabular-nums">{done}/{total}</span>
                  </div>
                </div>
                <p className="text-xs text-slate-500">{activity.description}</p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plan detail screen
// ---------------------------------------------------------------------------

function PlanDetail({
  plan,
  activityId,
  moduleId,
  completed,
  onToggleDay,
  onExerciseClick,
}: {
  plan: WorkoutPlan;
  activityId: string;
  moduleId: string;
  completed: Set<string>;
  onToggleDay: (dayId: string, done: boolean) => void;
  onExerciseClick: (lessonRef: string) => void;
}) {
  const LEVEL_COLORS: Record<string, string> = {
    beginner: "text-green-600 bg-green-50",
    intermediate: "text-amber-600 bg-amber-50",
    advanced: "text-red-600 bg-red-50",
  };

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <h2 className="text-xl font-bold text-slate-900">{plan.title}</h2>
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${LEVEL_COLORS[plan.level] ?? ""}`}>
            {plan.level}
          </span>
        </div>
        <p className="text-sm text-slate-500 mb-1">{plan.description}</p>
        <span className="text-xs text-slate-400">📅 {plan.frequency}</span>
      </div>

      <div className="space-y-4">
        {plan.days.map((day) => {
          const dayKey = planDayId(activityId, moduleId, plan.id, day.id);
          const done = completed.has(dayKey);
          return (
            <div key={day.id} className="bg-white border border-slate-200 rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-200">
                <div>
                  <h4 className="font-semibold text-slate-900 text-sm">{day.title}</h4>
                  <p className="text-xs text-slate-500">{day.focus}</p>
                </div>
                <button
                  onClick={() => onToggleDay(dayKey, !done)}
                  className={`text-xs font-medium px-3 py-1.5 rounded-lg transition-colors ${
                    done
                      ? "bg-green-500 text-white hover:bg-green-600"
                      : "bg-slate-200 text-slate-600 hover:bg-slate-300"
                  }`}
                >
                  {done ? "✓ Done" : "Mark done"}
                </button>
              </div>
              <div className="divide-y divide-slate-100">
                {day.exercises.map((ex, i) => {
                  const lesson = getLessonByRef(ex.lessonRef);
                  return (
                    <div key={i} className="px-4 py-3 flex items-center gap-3">
                      <span className="text-xs text-slate-400 w-4 shrink-0">{i + 1}.</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline gap-2">
                          <span className="text-sm font-medium text-slate-800 truncate">
                            {lesson?.title ?? ex.lessonRef}
                          </span>
                          <span className="text-xs text-slate-500 shrink-0">{ex.sets}</span>
                        </div>
                        {ex.notes && (
                          <p className="text-xs text-slate-400 mt-0.5">{ex.notes}</p>
                        )}
                        {ex.rest && (
                          <span className="text-xs text-slate-400">Rest: {ex.rest}</span>
                        )}
                      </div>
                      {lesson && (
                        <button
                          onClick={() => onExerciseClick(ex.lessonRef)}
                          className="shrink-0 text-xs text-blue-500 hover:text-blue-700 underline-offset-2 hover:underline"
                        >
                          View
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plans list screen
// ---------------------------------------------------------------------------

function PlansList({
  plans,
  activityId,
  moduleId,
  completed,
  onSelect,
}: {
  plans: WorkoutPlan[];
  activityId: string;
  moduleId: string;
  completed: Set<string>;
  onSelect: (plan: WorkoutPlan) => void;
}) {
  const LEVEL_COLORS: Record<string, string> = {
    beginner: "bg-green-100 text-green-700",
    intermediate: "bg-amber-100 text-amber-700",
    advanced: "bg-red-100 text-red-700",
  };
  return (
    <div className="space-y-4 max-w-2xl">
      {plans.map((plan) => {
        const totalDays = plan.days.length;
        const doneDays = plan.days.filter((d) =>
          completed.has(planDayId(activityId, moduleId, plan.id, d.id))
        ).length;
        return (
          <button
            key={plan.id}
            onClick={() => onSelect(plan)}
            className="w-full text-left bg-white border border-slate-200 rounded-xl p-5 hover:border-slate-400 hover:shadow-md transition-all"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-semibold text-slate-900">{plan.title}</h3>
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${LEVEL_COLORS[plan.level] ?? ""}`}>
                    {plan.level}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mb-2 leading-relaxed">{plan.description}</p>
                <span className="text-xs text-slate-400">📅 {plan.frequency}</span>
              </div>
              <div className="flex flex-col items-center gap-1 shrink-0">
                <ProgressRing done={doneDays} total={totalDays} size={36} />
                <span className="text-xs text-slate-400">{doneDays}/{totalDays} days</span>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main LearnTab component
// ---------------------------------------------------------------------------

export default function LearnTab({
  token,
  user,
}: {
  token: string | null;
  user: UserProfile | null;
}) {
  const [view, setView] = useState<LearnView>({ screen: "sports" });
  const [completed, setCompleted] = useState<Set<string>>(new Set());
  const [loadingProgress, setLoadingProgress] = useState(false);

  // Load progress on mount (skip if unauthenticated)
  useEffect(() => {
    if (!token) return;
    setLoadingProgress(true);
    getLearningProgress(token)
      .then((data) => setCompleted(new Set(data.items.map((i) => i.lesson_id))))
      .catch(() => {/* progress fetch is non-critical */})
      .finally(() => setLoadingProgress(false));
  }, [token]);

  const toggleLesson = useCallback(
    async (lessonId: string, markDone: boolean) => {
      if (!token) return;
      if (markDone) {
        await markLessonComplete(token, lessonId);
        setCompleted((prev) => new Set([...prev, lessonId]));
      } else {
        await unmarkLessonComplete(token, lessonId);
        setCompleted((prev) => {
          const next = new Set(prev);
          next.delete(lessonId);
          return next;
        });
      }
    },
    [token],
  );

  // Derive context from current view
  const currentActivity = useMemo(() => {
    if ("activityId" in view) return LEARN_CONTENT.find((a) => a.id === view.activityId);
    return undefined;
  }, [view]);

  const currentModule = useMemo(() => {
    if (!currentActivity || !("moduleId" in view)) return undefined;
    return currentActivity.modules.find((m) => m.id === (view as { moduleId: string }).moduleId);
  }, [currentActivity, view]);

  // ---------------------------------------------------------------------------
  // Render: breadcrumbs
  // ---------------------------------------------------------------------------

  function buildCrumbs() {
    const crumbs: { label: string; onClick: () => void }[] = [
      { label: "Learn", onClick: () => setView({ screen: "sports" }) },
    ];
    if ("activityId" in view && currentActivity) {
      crumbs.push({
        label: currentActivity.title,
        onClick: () => setView({ screen: "modules", activityId: currentActivity.id }),
      });
    }
    if ("moduleId" in view && currentModule) {
      crumbs.push({
        label: currentModule.title,
        onClick: () => {
          const v = view as { activityId: string; moduleId: string };
          if (currentModule.type === "variant-select") {
            setView({ screen: "variants", activityId: v.activityId, moduleId: v.moduleId });
          } else if (currentModule.type === "plans") {
            setView({ screen: "plans", activityId: v.activityId, moduleId: v.moduleId });
          } else {
            setView({ screen: "direct-lessons", activityId: v.activityId, moduleId: v.moduleId });
          }
        },
      });
    }
    if (view.screen === "lessons" || view.screen === "lesson") {
      const v = view as { activityId: string; moduleId: string; variantId: string };
      const mod = currentModule;
      if (mod?.type === "variant-select") {
        const variant = mod.variantGroup.variants.find((vv) => vv.id === v.variantId);
        if (variant) {
          crumbs.push({
            label: variant.title,
            onClick: () =>
              setView({ screen: "lessons", activityId: v.activityId, moduleId: v.moduleId, variantId: v.variantId }),
          });
        }
      }
    }
    if (view.screen === "plan-detail") {
      const v = view as { activityId: string; moduleId: string; planId: string };
      const mod = currentModule;
      if (mod?.type === "plans") {
        const plan = mod.plans.find((p) => p.id === v.planId);
        if (plan) {
          crumbs.push({
            label: plan.title,
            onClick: () => {},
          });
        }
      }
    }
    if (view.screen === "lesson" || view.screen === "direct-lesson") {
      const lessonId =
        view.screen === "lesson"
          ? (view as { lessonId: string }).lessonId
          : (view as { lessonId: string }).lessonId;
      let lesson: Lesson | undefined;
      if (view.screen === "lesson") {
        const v = view as { activityId: string; moduleId: string; variantId: string; lessonId: string };
        const mod = currentModule;
        if (mod?.type === "variant-select") {
          const variant = mod.variantGroup.variants.find((vv) => vv.id === v.variantId);
          lesson = variant?.lessons.find((l) => l.id === v.lessonId);
        }
      } else {
        const v = view as { activityId: string; moduleId: string; lessonId: string };
        const mod = currentModule;
        if (mod?.type === "lessons") {
          lesson = mod.lessons.find((l) => l.id === v.lessonId);
        }
      }
      if (lesson) {
        crumbs.push({ label: lesson.title, onClick: () => {} });
      }
    }
    return crumbs;
  }

  // ---------------------------------------------------------------------------
  // Render: main content
  // ---------------------------------------------------------------------------

  function renderContent() {
    if (view.screen === "sports") {
      return (
        <SportSelector
          completed={completed}
          onSelect={(activity) => setView({ screen: "modules", activityId: activity.id })}
        />
      );
    }

    if (view.screen === "modules" && currentActivity) {
      return (
        <ModuleGrid
          activity={currentActivity}
          completed={completed}
          onSelect={(mod) => {
            const v = view as { activityId: string };
            if (mod.type === "variant-select") {
              setView({ screen: "variants", activityId: v.activityId, moduleId: mod.id });
            } else if (mod.type === "plans") {
              setView({ screen: "plans", activityId: v.activityId, moduleId: mod.id });
            } else {
              setView({ screen: "direct-lessons", activityId: v.activityId, moduleId: mod.id });
            }
          }}
        />
      );
    }

    if (view.screen === "variants" && currentModule?.type === "variant-select") {
      const v = view as { activityId: string; moduleId: string };
      return (
        <div>
          <p className="text-slate-600 mb-5 text-sm">{currentModule.variantGroup.prompt}</p>
          <VariantSelector
            variants={currentModule.variantGroup.variants}
            completed={completed}
            buildLessonId={(variantId, lessonId) =>
              variantLessonId(v.activityId, v.moduleId, variantId, lessonId)
            }
            onSelect={(variant) =>
              setView({ screen: "lessons", activityId: v.activityId, moduleId: v.moduleId, variantId: variant.id })
            }
          />
        </div>
      );
    }

    if (view.screen === "lessons" && currentModule?.type === "variant-select") {
      const v = view as { activityId: string; moduleId: string; variantId: string };
      const variant = currentModule.variantGroup.variants.find((vv) => vv.id === v.variantId);
      if (!variant) return null;
      return (
        <LessonsList
          lessons={variant.lessons}
          buildId={(lessonId) => variantLessonId(v.activityId, v.moduleId, v.variantId, lessonId)}
          completed={completed}
          onSelect={(lesson, lessonId) =>
            setView({
              screen: "lesson",
              activityId: v.activityId,
              moduleId: v.moduleId,
              variantId: v.variantId,
              lessonId: lesson.id,
            })
          }
        />
      );
    }

    if (view.screen === "lesson") {
      const v = view as { activityId: string; moduleId: string; variantId: string; lessonId: string };
      const mod = currentModule;
      if (mod?.type !== "variant-select") return null;
      const variant = mod.variantGroup.variants.find((vv) => vv.id === v.variantId);
      const lesson = variant?.lessons.find((l) => l.id === v.lessonId);
      if (!lesson) return null;
      const lessonId = variantLessonId(v.activityId, v.moduleId, v.variantId, v.lessonId);
      return (
        <LessonDetail
          lesson={lesson}
          lessonId={lessonId}
          completed={completed.has(lessonId)}
          onToggle={(id, done) => toggleLesson(id, done)}
          onBack={() =>
            setView({ screen: "lessons", activityId: v.activityId, moduleId: v.moduleId, variantId: v.variantId })
          }
        />
      );
    }

    if (view.screen === "direct-lessons" && currentModule?.type === "lessons") {
      const v = view as { activityId: string; moduleId: string };
      return (
        <LessonsList
          lessons={currentModule.lessons}
          buildId={(lessonId) => directLessonId(v.activityId, v.moduleId, lessonId)}
          completed={completed}
          onSelect={(lesson) =>
            setView({ screen: "direct-lesson", activityId: v.activityId, moduleId: v.moduleId, lessonId: lesson.id })
          }
        />
      );
    }

    if (view.screen === "direct-lesson" && currentModule?.type === "lessons") {
      const v = view as { activityId: string; moduleId: string; lessonId: string };
      const lesson = currentModule.lessons.find((l) => l.id === v.lessonId);
      if (!lesson) return null;
      const lessonId = directLessonId(v.activityId, v.moduleId, v.lessonId);
      return (
        <LessonDetail
          lesson={lesson}
          lessonId={lessonId}
          completed={completed.has(lessonId)}
          onToggle={(id, done) => toggleLesson(id, done)}
          onBack={() =>
            setView({ screen: "direct-lessons", activityId: v.activityId, moduleId: v.moduleId })
          }
        />
      );
    }

    if (view.screen === "plans" && currentModule?.type === "plans") {
      const v = view as { activityId: string; moduleId: string };
      return (
        <PlansList
          plans={currentModule.plans}
          activityId={v.activityId}
          moduleId={v.moduleId}
          completed={completed}
          onSelect={(plan) =>
            setView({ screen: "plan-detail", activityId: v.activityId, moduleId: v.moduleId, planId: plan.id })
          }
        />
      );
    }

    if (view.screen === "plan-detail" && currentModule?.type === "plans") {
      const v = view as { activityId: string; moduleId: string; planId: string };
      const plan = currentModule.plans.find((p) => p.id === v.planId);
      if (!plan) return null;
      return (
        <PlanDetail
          plan={plan}
          activityId={v.activityId}
          moduleId={v.moduleId}
          completed={completed}
          onToggleDay={(dayKey, done) => toggleLesson(dayKey, done)}
          onExerciseClick={(lessonRef) => {
            // Navigate to the referenced lesson
            const parts = lessonRef.split(".");
            if (parts.length === 4) {
              const [actId, modId, varId, lesId] = parts;
              setView({ screen: "lesson", activityId: actId, moduleId: modId, variantId: varId, lessonId: lesId });
            }
          }}
        />
      );
    }

    return null;
  }

  const crumbs = buildCrumbs();

  return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Learning Track</h1>
        <p className="text-sm text-slate-500 mt-1">
          Master techniques with step-by-step lessons and track your progress.
        </p>
      </div>

      {/* Unauthenticated notice */}
      {!token && (
        <div className="mb-5 bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
          Sign in to save your progress across sessions.
        </div>
      )}

      {/* Loading indicator for progress */}
      {loadingProgress && (
        <div className="mb-4 text-xs text-slate-400">Loading your progress…</div>
      )}

      {/* Breadcrumbs */}
      {crumbs.length > 1 && <Breadcrumb crumbs={crumbs} />}

      {/* Main content */}
      {renderContent()}
    </div>
  );
}
