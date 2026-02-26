"""
Frame annotation: skeleton overlay, joint angle labels, wrist trail.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional, Tuple

import cv2
import numpy as np

from config import (
    ANGLE_TEXT_COLOR,
    FONT_SCALE,
    FONT_THICKNESS,
    JOINT_COLOR,
    POSE_CONNECTIONS,
    SKELETON_COLOR,
    TRAIL_LENGTH,
    WRIST_TRAIL_COLOR,
    Landmarks,
)
from pipeline.metrics import FrameMetrics
from pipeline.pose_detector import LandmarkResult


class Annotator:
    """Stateful annotator that maintains the wrist trail across frames."""

    def __init__(self, show_angles: bool = True, show_trail: bool = True) -> None:
        self.show_angles = show_angles
        self.show_trail = show_trail
        self._right_trail: Deque[Tuple[int, int]] = deque(maxlen=TRAIL_LENGTH)
        self._left_trail: Deque[Tuple[int, int]] = deque(maxlen=TRAIL_LENGTH)

    def reset_trail(self) -> None:
        self._right_trail.clear()
        self._left_trail.clear()

    def annotate_frame(
        self,
        frame: np.ndarray,
        result: Optional[LandmarkResult],
        metrics: Optional[FrameMetrics] = None,
        is_swing_frame: bool = False,
    ) -> np.ndarray:
        """
        Return an annotated copy of *frame*.
        """
        out = frame.copy()
        h, w = out.shape[:2]

        if result is None:
            # No pose — just draw a subtle "no pose" message
            cv2.putText(
                out,
                "No pose detected",
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                FONT_SCALE,
                (100, 100, 255),
                FONT_THICKNESS,
                cv2.LINE_AA,
            )
            return out

        # Collect pixel coords for all landmarks
        pixels: dict[int, Tuple[int, int]] = {}
        for idx in range(33):
            pt = result.get_pixel(idx, w, h)
            if pt is not None:
                pixels[idx] = pt

        # -- Skeleton lines --
        for start_idx, end_idx in POSE_CONNECTIONS:
            if start_idx in pixels and end_idx in pixels:
                cv2.line(out, pixels[start_idx], pixels[end_idx], SKELETON_COLOR, 2, cv2.LINE_AA)

        # -- Joint circles --
        for pt in pixels.values():
            cv2.circle(out, pt, 4, JOINT_COLOR, -1, cv2.LINE_AA)

        # -- Wrist trail --
        rw_px = pixels.get(Landmarks.RIGHT_WRIST)
        lw_px = pixels.get(Landmarks.LEFT_WRIST)

        if rw_px:
            self._right_trail.append(rw_px)
        if lw_px:
            self._left_trail.append(lw_px)

        if self.show_trail:
            self._draw_trail(out, self._right_trail)
            self._draw_trail(out, self._left_trail)

        # -- Angle labels --
        if self.show_angles and metrics is not None:
            self._draw_angle_labels(out, pixels, metrics)

        # -- Swing event flash --
        if is_swing_frame:
            cv2.rectangle(out, (0, 0), (w - 1, h - 1), (0, 165, 255), 3)
            cv2.putText(
                out,
                "SWING",
                (w - 80, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 165, 255),
                2,
                cv2.LINE_AA,
            )

        return out

    def _draw_trail(
        self, frame: np.ndarray, trail: Deque[Tuple[int, int]]
    ) -> None:
        pts = list(trail)
        for i in range(1, len(pts)):
            alpha = i / len(pts)
            color = tuple(int(c * alpha) for c in WRIST_TRAIL_COLOR)
            cv2.line(frame, pts[i - 1], pts[i], color, 2, cv2.LINE_AA)

    def _draw_angle_labels(
        self,
        frame: np.ndarray,
        pixels: dict,
        metrics: FrameMetrics,
    ) -> None:
        angle_map = [
            (Landmarks.RIGHT_ELBOW, metrics.right_elbow_angle, "RE"),
            (Landmarks.LEFT_ELBOW, metrics.left_elbow_angle, "LE"),
            (Landmarks.RIGHT_SHOULDER, metrics.right_shoulder_angle, "RS"),
            (Landmarks.LEFT_SHOULDER, metrics.left_shoulder_angle, "LS"),
            (Landmarks.RIGHT_KNEE, metrics.right_knee_angle, "RK"),
            (Landmarks.LEFT_KNEE, metrics.left_knee_angle, "LK"),
        ]

        for lm_idx, angle, label in angle_map:
            if angle is None or lm_idx not in pixels:
                continue
            px, py = pixels[lm_idx]
            text = f"{label}:{angle:.0f}\u00b0"
            # Offset text slightly above the joint
            tx, ty = px + 6, py - 6
            cv2.putText(
                frame,
                text,
                (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX,
                FONT_SCALE,
                ANGLE_TEXT_COLOR,
                FONT_THICKNESS,
                cv2.LINE_AA,
            )


def annotate_all_frames(
    frames: List[np.ndarray],
    pose_results: List[Optional[LandmarkResult]],
    frame_metrics: List[FrameMetrics],
    swing_frame_indices: set,
    show_angles: bool = True,
    show_trail: bool = True,
) -> List[np.ndarray]:
    """
    Annotate every frame and return the annotated list.
    """
    annotator = Annotator(show_angles=show_angles, show_trail=show_trail)
    annotated = []
    for i, (frame, result, metrics) in enumerate(
        zip(frames, pose_results, frame_metrics)
    ):
        is_swing = i in swing_frame_indices
        ann = annotator.annotate_frame(frame, result, metrics, is_swing)
        annotated.append(ann)
    return annotated
