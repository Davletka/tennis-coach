#!/usr/bin/env python3
"""
extract_reference_poses.py — Extract VRM bone poses from a reference tennis video.

Given a video file, this script:
  1. Runs MediaPipe Pose (Tasks API, VIDEO mode) on every frame.
  2. Collects both 2D normalized landmarks (for wrist tracking) and
     3D world landmarks (for rotation math).
  3. Identifies three key swing frames:
       backswing    — right wrist is at its maximum backward extent in body space
       contact      — right wrist velocity peaks (highest speed frame)
       followthrough — ~15 frames after contact, or the frame where the right
                       wrist reaches its maximum height after contact
  4. Calls ``landmarks_to_vrm_pose()`` for each key frame.
  5. Prints a ready-to-paste TypeScript ``POSES`` constant to stdout.

Usage
-----
    python scripts/extract_reference_poses.py path/to/forehand.mp4
    python scripts/extract_reference_poses.py path/to/forehand.mp4 --complexity 2

Requirements: opencv-python-headless, mediapipe>=0.10.11, numpy, scipy
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

# ---------------------------------------------------------------------------
# Path setup: allow running from any directory
# ---------------------------------------------------------------------------

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

from utils.pose_to_vrm import landmarks_to_vrm_pose, compute_global_alignment, IDX  # noqa: E402

# ---------------------------------------------------------------------------
# MediaPipe model management (mirrors pipeline/pose_detector.py)
# ---------------------------------------------------------------------------

_MODEL_URLS = {
    0: (
        "https://storage.googleapis.com/mediapipe-models/"
        "pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
    ),
    1: (
        "https://storage.googleapis.com/mediapipe-models/"
        "pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
    ),
    2: (
        "https://storage.googleapis.com/mediapipe-models/"
        "pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"
    ),
}
_MODEL_NAMES = {
    0: "pose_landmarker_lite.task",
    1: "pose_landmarker_full.task",
    2: "pose_landmarker_heavy.task",
}
_MODELS_DIR = os.path.join(_PROJECT_DIR, "models")


def _ensure_model(complexity: int) -> str:
    """Download the pose landmarker model if not already cached. Returns path."""
    complexity = max(0, min(2, complexity))
    os.makedirs(_MODELS_DIR, exist_ok=True)
    path = os.path.abspath(os.path.join(_MODELS_DIR, _MODEL_NAMES[complexity]))
    if not os.path.exists(path):
        url = _MODEL_URLS[complexity]
        print(f"[info] Downloading model {_MODEL_NAMES[complexity]} ...", file=sys.stderr)
        urllib.request.urlretrieve(url, path)
        print("[info] Download complete.", file=sys.stderr)
    return path


# ---------------------------------------------------------------------------
# Video processing
# ---------------------------------------------------------------------------

def _process_video(video_path: str, complexity: int) -> tuple[
    list[Optional[list]],   # world_landmarks per frame (None if no pose)
    list[Optional[list]],   # normalized_landmarks per frame (None if no pose)
    int,                    # total frame count
]:
    """
    Run MediaPipe pose detection (Tasks API, VIDEO mode) on every frame.

    Returns
    -------
    world_lm_per_frame : list[Optional[list]]
        Per-frame list of world landmark objects (pose_world_landmarks[0]).
        None when no pose was detected.
    norm_lm_per_frame : list[Optional[list]]
        Per-frame list of normalized landmark objects (pose_landmarks[0]).
        None when no pose was detected.
    total_frames : int
        Total number of frames in the video.
    """
    model_path = _ensure_model(complexity)

    PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
    RunningMode          = mp.tasks.vision.RunningMode

    options = PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(
            model_asset_path=model_path,
            delegate=mp.tasks.BaseOptions.Delegate.CPU,
        ),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[error] Cannot open video: {video_path}", file=sys.stderr)
        sys.exit(1)

    fps        = cap.get(cv2.CAP_PROP_FPS) or 30.0
    ms_per_frame = 1000.0 / fps

    world_lm_per_frame: list[Optional[list]] = []
    norm_lm_per_frame:  list[Optional[list]] = []
    frame_index = 0

    print("[info] Processing video frames ...", file=sys.stderr)

    with mp.tasks.vision.PoseLandmarker.create_from_options(options) as landmarker:
        while True:
            ret, bgr = cap.read()
            if not ret:
                break

            timestamp_ms = int(frame_index * ms_per_frame)
            rgb      = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result   = landmarker.detect_for_video(mp_image, timestamp_ms)

            if result.pose_landmarks and result.pose_world_landmarks:
                world_lm_per_frame.append(result.pose_world_landmarks[0])
                norm_lm_per_frame.append(result.pose_landmarks[0])
            else:
                world_lm_per_frame.append(None)
                norm_lm_per_frame.append(None)

            frame_index += 1

    cap.release()
    total_frames = frame_index
    detected = sum(1 for x in world_lm_per_frame if x is not None)
    print(
        f"[info] Processed {total_frames} frames; pose detected in {detected}.",
        file=sys.stderr,
    )
    return world_lm_per_frame, norm_lm_per_frame, total_frames


# ---------------------------------------------------------------------------
# Key-frame detection
# ---------------------------------------------------------------------------

def _get_wrist_positions(
    world_lm_per_frame: list[Optional[list]],
) -> list[Optional[np.ndarray]]:
    """
    Extract right wrist position in body-local space for each frame.

    We use the world landmarks so we can reuse the body-frame construction
    logic from pose_to_vrm.  We import the internal helper directly.

    Returns a list aligned with world_lm_per_frame; None where no pose.
    """
    from utils.pose_to_vrm import _extract_pts, _build_body_frame

    positions: list[Optional[np.ndarray]] = []
    for lm_list in world_lm_per_frame:
        if lm_list is None:
            positions.append(None)
            continue

        pts        = _extract_pts(lm_list)
        body_rot   = _build_body_frame(pts)
        # Wrist in body-local space
        wrist_body = body_rot.apply(pts["r_wrist"])
        positions.append(wrist_body)

    return positions


def _wrist_velocity(
    positions: list[Optional[np.ndarray]],
) -> list[Optional[float]]:
    """
    Compute right wrist speed (Euclidean distance between consecutive frames)
    for each frame.  Returns None at frame 0 and wherever a position is missing.
    """
    speeds: list[Optional[float]] = [None]  # frame 0 has no prior frame
    for i in range(1, len(positions)):
        if positions[i] is None or positions[i - 1] is None:
            speeds.append(None)
        else:
            speed = float(np.linalg.norm(positions[i] - positions[i - 1]))
            speeds.append(speed)
    return speeds


def _find_key_frames(
    world_lm_per_frame: list[Optional[list]],
    followthrough_offset: int = 15,
) -> tuple[int, int, int]:
    """
    Identify backswing, contact, and follow-through frame indices.

    Strategy
    --------
    - ``contact``      : frame with the highest right-wrist speed.
    - ``backswing``    : before contact, the frame where the body-local X
                         position of the right wrist is most negative
                         (wrist furthest "back" for a right-handed forehand).
    - ``followthrough``: ``contact + followthrough_offset`` clamped to the
                         last valid frame, or — if that frame has no detection —
                         the first valid frame after contact with maximum wrist
                         height (largest body-local Y).

    Falls back to evenly-spaced frames if fewer than 3 valid detections exist.
    """
    positions = _get_wrist_positions(world_lm_per_frame)
    speeds    = _wrist_velocity(positions)

    valid_indices = [i for i, p in enumerate(positions) if p is not None]

    if len(valid_indices) < 3:
        print(
            "[warning] Fewer than 3 frames with valid pose detection. "
            "Using evenly-spaced fallback frames.",
            file=sys.stderr,
        )
        n = len(world_lm_per_frame)
        return n // 4, n // 2, 3 * n // 4

    # --- Contact: maximum wrist speed ---
    best_speed      = -1.0
    contact_frame   = valid_indices[len(valid_indices) // 2]  # default: midpoint
    for i in valid_indices:
        spd = speeds[i]
        if spd is not None and spd > best_speed:
            best_speed    = spd
            contact_frame = i

    # --- Backswing: most negative body-local X, among frames BEFORE contact ---
    pre_contact = [i for i in valid_indices if i < contact_frame]
    if not pre_contact:
        # No frames before contact — use the first valid frame.
        backswing_frame = valid_indices[0]
    else:
        backswing_frame = min(
            pre_contact,
            key=lambda i: positions[i][0],  # type: ignore[index]  # most negative X
        )

    # --- Follow-through: offset after contact, or max height ---
    candidate_ft = contact_frame + followthrough_offset
    post_contact = [i for i in valid_indices if i > contact_frame]

    if not post_contact:
        # No frames after contact — use the last valid frame.
        followthrough_frame = valid_indices[-1]
    elif candidate_ft in post_contact:
        followthrough_frame = candidate_ft
    else:
        # Closest valid frame at or after the offset, falling back to max height.
        after_offset = [i for i in post_contact if i >= contact_frame + followthrough_offset]
        if after_offset:
            followthrough_frame = after_offset[0]
        else:
            # All valid post-contact frames are before the offset target;
            # pick the one with the highest wrist Y (maximum height).
            followthrough_frame = max(
                post_contact,
                key=lambda i: positions[i][1],  # type: ignore[index]  # highest Y
            )

    print(
        f"[info] Key frames — backswing={backswing_frame}, "
        f"contact={contact_frame}, followthrough={followthrough_frame}",
        file=sys.stderr,
    )
    return backswing_frame, contact_frame, followthrough_frame


# ---------------------------------------------------------------------------
# TypeScript output generation
# ---------------------------------------------------------------------------

_BONE_ORDER = [
    "hips",
    "chest",
    "neck",
    "rightUpperArm",
    "rightLowerArm",
    "leftUpperArm",
    "leftLowerArm",
    "rightUpperLeg",
    "rightLowerLeg",
    "leftUpperLeg",
    "leftLowerLeg",
]


def _format_pose_block(pose_name: str, vrm_pose: dict[str, list[float]]) -> str:
    """Format one named pose as a TypeScript object literal block."""
    lines = [f"  {pose_name}: {{"]
    max_bone_len = max(len(b) for b in _BONE_ORDER)
    for bone in _BONE_ORDER:
        angles = vrm_pose.get(bone, [0.0, 0.0, 0.0])
        # Format as fixed-width aligned columns for readability.
        vals = ", ".join(f"{v:7.3f}" for v in angles)
        padding = " " * (max_bone_len - len(bone))
        lines.append(f"    {bone}:{padding} [{vals}],")
    lines.append("  },")
    return "\n".join(lines)


def _emit_typescript(
    video_filename: str,
    backswing_frame: int,
    contact_frame: int,
    followthrough_frame: int,
    backswing_pose: dict[str, list[float]],
    contact_pose: dict[str, list[float]],
    followthrough_pose: dict[str, list[float]],
) -> str:
    """Build the full TypeScript POSES constant string."""
    header = (
        f"// Auto-generated from: {video_filename}\n"
        f"// Frames: backswing={backswing_frame}, "
        f"contact={contact_frame}, "
        f"followthrough={followthrough_frame}\n"
    )

    # Note: the spec calls for the follow-through entry to be named "midswing".
    blocks = "\n".join([
        _format_pose_block("backswing",  backswing_pose),
        _format_pose_block("midswing",   followthrough_pose),   # renamed per spec
        _format_pose_block("contact",    contact_pose),
    ])

    return (
        header
        + "const POSES = {\n"
        + blocks + "\n"
        + "} as const;\n"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract VRM bone poses from a reference tennis video."
    )
    parser.add_argument("video", help="Path to the input video file.")
    parser.add_argument(
        "--complexity",
        type=int,
        default=1,
        choices=[0, 1, 2],
        help="MediaPipe model complexity: 0=lite, 1=full (default), 2=heavy.",
    )
    parser.add_argument(
        "--followthrough-offset",
        type=int,
        default=15,
        metavar="N",
        help="Frames after contact to use as follow-through (default: 15).",
    )
    args = parser.parse_args()

    video_path = os.path.abspath(args.video)
    if not os.path.isfile(video_path):
        print(f"[error] File not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    # 1. Process video.
    world_lm_per_frame, _, total_frames = _process_video(
        video_path, complexity=args.complexity
    )

    # 2. Find key frames.
    backswing_frame, contact_frame, followthrough_frame = _find_key_frames(
        world_lm_per_frame,
        followthrough_offset=args.followthrough_offset,
    )

    # 3. Compute a FIXED global alignment from a neutral frame (a few frames
    #    before the backswing) so that hips/chest rotations are preserved
    #    across all three key frames rather than being zeroed out per-frame.
    neutral_idx = max(0, backswing_frame - 30)
    # Walk back to find the nearest valid frame if the neutral one is missing.
    while neutral_idx > 0 and world_lm_per_frame[neutral_idx] is None:
        neutral_idx -= 1
    neutral_lm = world_lm_per_frame[neutral_idx]
    global_align = compute_global_alignment(neutral_lm) if neutral_lm is not None else None
    if global_align is not None:
        print(
            f"[info] Global alignment computed from neutral frame {neutral_idx}.",
            file=sys.stderr,
        )

    def _get_pose(frame_idx: int) -> dict[str, list[float]]:
        lm = world_lm_per_frame[frame_idx]
        if lm is None:
            print(
                f"[warning] No pose detected at frame {frame_idx}; "
                "outputting identity rotations.",
                file=sys.stderr,
            )
            return {bone: [0.0, 0.0, 0.0] for bone in _BONE_ORDER}
        return landmarks_to_vrm_pose(lm, global_align=global_align)

    backswing_pose    = _get_pose(backswing_frame)
    contact_pose      = _get_pose(contact_frame)
    followthrough_pose = _get_pose(followthrough_frame)

    # 4. Emit TypeScript.
    ts_block = _emit_typescript(
        video_filename=os.path.basename(video_path),
        backswing_frame=backswing_frame,
        contact_frame=contact_frame,
        followthrough_frame=followthrough_frame,
        backswing_pose=backswing_pose,
        contact_pose=contact_pose,
        followthrough_pose=followthrough_pose,
    )

    print(ts_block)


if __name__ == "__main__":
    main()
