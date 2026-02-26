const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types mirroring api/models.py
// ---------------------------------------------------------------------------

export type JobStatus = "pending" | "running" | "completed" | "failed";

export interface AnalyzeResponse {
  job_id: string;
  status: JobStatus;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  progress: number; // 0–100
  message: string;
  created_at: string;
  updated_at: string;
}

export interface AngleStatResult {
  mean: number | null;
  min: number | null;
  max: number | null;
  std: number | null;
}

export interface SwingEventResult {
  frame_index: number;
  wrist_speed: number;
  com_x: number | null;
}

export interface MetricsResult {
  right_elbow: AngleStatResult;
  left_elbow: AngleStatResult;
  right_shoulder: AngleStatResult;
  left_shoulder: AngleStatResult;
  right_knee: AngleStatResult;
  left_knee: AngleStatResult;
  torso_rotation_mean: number | null;
  torso_rotation_max: number | null;
  stance_width_mean: number | null;
  com_x_range: number | null;
  swing_count: number;
  swing_events: SwingEventResult[];
  frames_analyzed: number;
  pose_detected_frames: number;
  detection_rate: number;
}

export interface CoachingReportResult {
  swing_mechanics: string;
  footwork_movement: string;
  stance_posture: string;
  shot_selection_tactics: string;
  top_3_priorities: string[];
}

export interface JobResultResponse {
  job_id: string;
  status: JobStatus;
  coaching_report: CoachingReportResult;
  metrics: MetricsResult;
  annotated_video_url: string;
  input_video_url: string;
  fps: number;
  total_source_frames: number;
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

export async function uploadVideo(file: File): Promise<AnalyzeResponse> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/api/v1/analyze`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Upload failed (${res.status}): ${detail}`);
  }

  return res.json() as Promise<AnalyzeResponse>;
}

export async function getJobStatus(
  jobId: string
): Promise<JobStatusResponse> {
  const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}`);
  if (!res.ok) {
    throw new Error(`Status check failed (${res.status})`);
  }
  return res.json() as Promise<JobStatusResponse>;
}

export async function getJobResult(
  jobId: string
): Promise<JobResultResponse> {
  const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/result`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Result fetch failed (${res.status}): ${detail}`);
  }
  return res.json() as Promise<JobResultResponse>;
}
