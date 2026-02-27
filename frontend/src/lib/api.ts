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

export interface TargetAngles {
  right_elbow: number | null;
  left_elbow: number | null;
  right_shoulder: number | null;
  left_shoulder: number | null;
  right_knee: number | null;
  left_knee: number | null;
}

export interface CoachingReportResult {
  swing_mechanics: string;
  footwork_movement: string;
  stance_posture: string;
  shot_selection_tactics: string;
  top_3_priorities: string[];
  target_angles: TargetAngles | null;
}

export interface ReferencePoseResult {
  avg_landmarks: ([number, number] | null)[];  // 33 items
  right_elbow: number | null;
  left_elbow: number | null;
  right_shoulder: number | null;
  left_shoulder: number | null;
  right_knee: number | null;
  left_knee: number | null;
  frames_analyzed: number;
  detection_rate: number;
}

// [x, y, visibility] — coordinates normalised [0, 1]; null if below visibility threshold
type LandmarkPoint = [number, number, number] | null;

export interface FrameData {
  lm: LandmarkPoint[] | null; // 33 MediaPipe landmarks; null if no pose detected
  re: number | null; // right elbow angle (degrees)
  le: number | null; // left elbow angle
  rs: number | null; // right shoulder angle
  ls: number | null; // left shoulder angle
  rk: number | null; // right knee angle
  lk: number | null; // left knee angle
}

export interface PerSwingMetricsResult {
  swing_index: number;
  peak_frame: number;
  window_start_frame: number;
  window_end_frame: number;
  peak_wrist_speed: number;
  com_x_at_peak: number | null;
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
}

export interface SwingCoachingResult {
  swing_index: number;
  quick_note: string;
  swing_mechanics: string;
  footwork_movement: string;
  stance_posture: string;
  shot_selection_tactics: string;
  top_3_priorities: string[];
}

export interface PerSwingAnalysis {
  swing_index: number;
  peak_frame: number;
  window_start_frame: number;
  window_end_frame: number;
  metrics: PerSwingMetricsResult;
  coaching: SwingCoachingResult;
}

export interface ActivityChoice {
  id: string;
  display_name: string;
}

export interface JobResultResponse {
  job_id: string;
  status: JobStatus;
  coaching_report: CoachingReportResult;
  metrics: MetricsResult;
  frame_data: FrameData[];
  input_video_url: string;
  fps: number;
  total_source_frames: number;
  per_swing_analyses: PerSwingAnalysis[];
  // Activity metadata
  activity: string;
  activity_display_name: string;
  coaching_labels: Record<string, string>;
  event_singular: string;
  event_plural: string;
}

// ---------------------------------------------------------------------------
// Auth types
// ---------------------------------------------------------------------------

export interface UserProfile {
  user_id: string;
  email: string;
  name: string;
  picture: string;
}

// ---------------------------------------------------------------------------
// History types
// ---------------------------------------------------------------------------

export interface SessionSummary {
  session_id: string;
  job_id: string;
  recorded_at: string;
  original_filename: string;
  fps: number;
  total_source_frames: number;
  frames_analyzed: number;
  detection_rate: number;
  annotated_video_url: string;
  input_video_url: string;
  metrics: MetricsResult;
  coaching: CoachingReportResult;
}

export interface SessionListResponse {
  sessions: SessionSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProgressDataPoint {
  recorded_at: string;
  right_elbow_mean: number | null;
  left_elbow_mean: number | null;
  right_shoulder_mean: number | null;
  left_shoulder_mean: number | null;
  right_knee_mean: number | null;
  left_knee_mean: number | null;
  torso_rotation_mean: number | null;
  stance_width_mean: number | null;
  swing_count: number | null;
  detection_rate: number | null;
}

export interface ProgressResponse {
  data_points: ProgressDataPoint[];
}

export interface MetricDelta {
  metric_name: string;
  session_a_value: number | null;
  session_b_value: number | null;
  delta: number | null;
  direction: "improved" | "regressed" | "unchanged";
}

export interface DeltaCoachingReport {
  overall_progress_summary: string;
  improvements: string[];
  regressions: string[];
  unchanged_areas: string[];
  top_3_priorities: string[];
}

export interface CompareResponse {
  metric_deltas: MetricDelta[];
  delta_coaching_report: DeltaCoachingReport;
}

// ---------------------------------------------------------------------------
// Fetch helpers — unauthenticated
// ---------------------------------------------------------------------------

export async function uploadVideo(
  file: File,
  token: string,
  activity = "tennis",
): Promise<AnalyzeResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("activity", activity);

  const res = await fetch(`${API_BASE}/api/v1/analyze`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Upload failed (${res.status}): ${detail}`);
  }

  return res.json() as Promise<AnalyzeResponse>;
}

export async function getJobStatus(
  jobId: string,
  token: string,
): Promise<JobStatusResponse> {
  const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new Error(`Status check failed (${res.status})`);
  }
  return res.json() as Promise<JobStatusResponse>;
}

export async function getJobResult(
  jobId: string,
  token: string,
): Promise<JobResultResponse> {
  const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/result`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Result fetch failed (${res.status}): ${detail}`);
  }
  return res.json() as Promise<JobResultResponse>;
}

export async function retryJob(
  jobId: string,
  token: string,
): Promise<AnalyzeResponse> {
  const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/retry`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Retry failed (${res.status}): ${detail}`);
  }
  return res.json() as Promise<AnalyzeResponse>;
}

export async function uploadReferenceVideo(
  file: File,
  token: string,
): Promise<ReferencePoseResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/v1/reference`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Reference upload failed (${res.status}): ${detail}`);
  }
  return res.json() as Promise<ReferencePoseResult>;
}

// ---------------------------------------------------------------------------
// Fetch helpers — authenticated
// ---------------------------------------------------------------------------

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export async function getMe(token: string): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(`Auth check failed (${res.status})`);
  return res.json() as Promise<UserProfile>;
}

export async function listSessions(
  token: string,
  userId: string,
  limit = 10,
  offset = 0
): Promise<SessionListResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/users/${userId}/history?limit=${limit}&offset=${offset}`,
    { headers: authHeaders(token) }
  );
  if (!res.ok) throw new Error(`History fetch failed (${res.status})`);
  return res.json() as Promise<SessionListResponse>;
}

export async function getProgress(
  token: string,
  userId: string,
  limit = 30
): Promise<ProgressResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/users/${userId}/progress?limit=${limit}`,
    { headers: authHeaders(token) }
  );
  if (!res.ok) throw new Error(`Progress fetch failed (${res.status})`);
  return res.json() as Promise<ProgressResponse>;
}

export async function deleteSession(
  token: string,
  userId: string,
  sessionId: string,
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/users/${userId}/sessions/${sessionId}`,
    { method: "DELETE", headers: authHeaders(token) }
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Delete failed (${res.status}): ${detail}`);
  }
}

export async function compareSessions(
  token: string,
  userId: string,
  sessionAId: string,
  sessionBId: string
): Promise<CompareResponse> {
  const res = await fetch(`${API_BASE}/api/v1/users/${userId}/compare`, {
    method: "POST",
    headers: { ...authHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify({ session_a_id: sessionAId, session_b_id: sessionBId }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Compare failed (${res.status}): ${detail}`);
  }
  return res.json() as Promise<CompareResponse>;
}
