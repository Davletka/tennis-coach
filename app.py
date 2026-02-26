"""
Tennis Coach Video Analysis App — Streamlit entry point.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Load .env if present (useful for local dev without setting env vars manually)
load_dotenv()


# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Tennis Coach",
    page_icon="🎾",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🎾 Tennis Coach")
    st.markdown("---")

    api_key = st.text_input(
        "Anthropic API Key",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Get your key at https://console.anthropic.com",
    )

    st.markdown("### Display Options")
    show_angles = st.toggle("Show joint angles", value=True)
    show_trail = st.toggle("Show wrist trail", value=True)

    st.markdown("### Analysis Options")
    stride = st.slider(
        "Analysis stride (1 = every frame)",
        min_value=1,
        max_value=5,
        value=1,
        help="Increase to speed up analysis on long videos.",
    )

    st.markdown("---")
    st.caption("Powered by MediaPipe + Claude Sonnet")


# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
st.title("AI Tennis Coach — Video Analysis")
st.markdown(
    "Upload a tennis video (MP4, MOV, or AVI). "
    "The app will detect your pose, compute joint angles, and deliver "
    "coaching feedback powered by Claude."
)

uploaded_file = st.file_uploader(
    "Choose a video file",
    type=["mp4", "mov", "avi"],
    label_visibility="collapsed",
)

if uploaded_file is not None:
    # Show basic file metadata
    file_size_mb = uploaded_file.size / (1024 * 1024)
    col1, col2 = st.columns(2)
    col1.metric("File", uploaded_file.name)
    col2.metric("Size", f"{file_size_mb:.1f} MB")

    analyze_clicked = st.button("🔍 Analyze", type="primary", use_container_width=True)

    if analyze_clicked:
        if not api_key:
            st.error("Please enter your Anthropic API key in the sidebar.")
            st.stop()

        # ------------------------------------------------------------------
        # Pipeline
        # ------------------------------------------------------------------
        progress = st.progress(0, text="Initializing…")
        status = st.empty()

        # Save uploaded file to disk
        with tempfile.NamedTemporaryFile(
            suffix=Path(uploaded_file.name).suffix, delete=False
        ) as tmp_in:
            tmp_in.write(uploaded_file.read())
            input_path = tmp_in.name

        try:
            # Step 1 — Extract frames
            status.info("Step 1/5 — Extracting frames…")
            progress.progress(10, text="Extracting frames…")

            from pipeline.video_io import extract_frames, frames_to_video

            frames, fps, total_frames = extract_frames(
                input_path, stride=stride
            )
            duration_s = total_frames / max(fps, 1.0)

            st.caption(
                f"Video: {duration_s:.1f}s · {total_frames} total frames · "
                f"{fps:.1f} fps · {len(frames)} frames analyzed"
            )

            # Step 2 — Pose detection
            status.info("Step 2/5 — Detecting pose…")
            progress.progress(30, text="Running MediaPipe pose detection…")

            from pipeline.pose_detector import PoseDetector

            with PoseDetector() as detector:
                pose_results = detector.detect_batch(frames)

            detected_count = sum(1 for r in pose_results if r is not None)
            detection_rate = detected_count / max(len(frames), 1)

            if detection_rate < 0.40:
                st.warning(
                    f"⚠️ Pose detected in only {detection_rate*100:.0f}% of frames. "
                    "Try a video with better lighting and a clear view of the player."
                )

            # Step 3 — Compute metrics
            status.info("Step 3/5 — Computing metrics…")
            progress.progress(50, text="Computing joint angles and swing events…")

            from pipeline.metrics import compute_frame_metrics, aggregate_metrics

            h, w = frames[0].shape[:2]
            frame_metrics = []
            for i, (frame, result) in enumerate(zip(frames, pose_results)):
                prev_result = pose_results[i - 1] if i > 0 else None
                fm = compute_frame_metrics(result, prev_result, w, h)
                frame_metrics.append(fm)

            agg = aggregate_metrics(frame_metrics, pose_results)

            # Step 4 — Annotate frames
            status.info("Step 4/5 — Annotating video…")
            progress.progress(65, text="Drawing skeleton and angle labels…")

            from pipeline.annotator import annotate_all_frames

            swing_indices = {e.frame_index for e in agg.swing_events}
            annotated_frames = annotate_all_frames(
                frames,
                pose_results,
                frame_metrics,
                swing_indices,
                show_angles=show_angles,
                show_trail=show_trail,
            )

            # Write annotated video
            with tempfile.NamedTemporaryFile(
                suffix="_annotated.mp4", delete=False
            ) as tmp_out:
                output_path = tmp_out.name

            frames_to_video(annotated_frames, output_path, fps=fps)

            # Step 5 — Claude coaching
            status.info("Step 5/5 — Generating coaching feedback…")
            progress.progress(85, text="Calling Claude API…")

            from pipeline.coach import get_coaching_feedback

            report = get_coaching_feedback(
                agg=agg,
                fps=fps,
                total_source_frames=total_frames,
                api_key=api_key,
            )

            progress.progress(100, text="Done!")
            status.success("Analysis complete!")

            # ------------------------------------------------------------------
            # Results layout
            # ------------------------------------------------------------------
            st.markdown("---")
            left_col, right_col = st.columns([1, 1])

            # -- Annotated video --
            with left_col:
                st.subheader("Annotated Video")
                with open(output_path, "rb") as vf:
                    video_bytes = vf.read()
                st.video(video_bytes)
                st.download_button(
                    label="⬇️ Download annotated video",
                    data=video_bytes,
                    file_name="tennis_coach_annotated.mp4",
                    mime="video/mp4",
                )

            # -- Coaching tabs --
            with right_col:
                st.subheader("Coaching Feedback")
                tab_swing, tab_foot, tab_stance, tab_tactics, tab_prio = st.tabs(
                    ["Swing", "Footwork", "Stance", "Tactics", "Priorities"]
                )

                with tab_swing:
                    st.markdown(report.swing_mechanics or "_No feedback available._")

                with tab_foot:
                    st.markdown(report.footwork_movement or "_No feedback available._")

                with tab_stance:
                    st.markdown(report.stance_posture or "_No feedback available._")

                with tab_tactics:
                    st.markdown(report.shot_selection_tactics or "_No feedback available._")

                with tab_prio:
                    if report.top_3_priorities:
                        for i, p in enumerate(report.top_3_priorities, 1):
                            st.markdown(f"**{i}.** {p}")
                    else:
                        st.markdown("_No priorities available._")

            # -- Raw metrics table --
            st.markdown("---")
            with st.expander("📊 Raw Metrics"):
                import pandas as pd

                rows = []
                metric_defs = [
                    ("Right Elbow", agg.right_elbow),
                    ("Left Elbow", agg.left_elbow),
                    ("Right Shoulder", agg.right_shoulder),
                    ("Left Shoulder", agg.left_shoulder),
                    ("Right Knee", agg.right_knee),
                    ("Left Knee", agg.left_knee),
                ]
                for name, stat in metric_defs:
                    rows.append(
                        {
                            "Joint": name,
                            "Mean (°)": stat.mean,
                            "Min (°)": stat.min,
                            "Max (°)": stat.max,
                            "Std (°)": stat.std,
                        }
                    )

                df = pd.DataFrame(rows)
                st.dataframe(
                    df.style.format(
                        {
                            "Mean (°)": "{:.1f}",
                            "Min (°)": "{:.1f}",
                            "Max (°)": "{:.1f}",
                            "Std (°)": "{:.1f}",
                        },
                        na_rep="N/A",
                    ),
                    use_container_width=True,
                )

                col_a, col_b, col_c = st.columns(3)
                col_a.metric(
                    "Torso Rotation (mean)",
                    f"{agg.torso_rotation_mean:.1f}°" if agg.torso_rotation_mean else "N/A",
                )
                col_b.metric(
                    "Stance Width (norm.)",
                    f"{agg.stance_width_mean:.2f}" if agg.stance_width_mean else "N/A",
                )
                col_c.metric(
                    "Swing Events",
                    str(agg.swing_count),
                )

        except Exception as exc:
            st.error(f"Pipeline error: {exc}")
            raise
        finally:
            # Clean up temp input file
            try:
                os.unlink(input_path)
            except OSError:
                pass
