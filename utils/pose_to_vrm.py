"""
pose_to_vrm.py — Convert MediaPipe world landmarks to VRM normalized bone Euler angles.

MediaPipe world landmarks live in a metric coordinate system where:
  - Y is up
  - X is right (from camera's perspective)
  - Z points toward the camera
  - Origin is at the midpoint of the hips

VRM normalized pose space:
  - Character is in T-pose facing +Z
  - Y is up, X is character-right

This module builds a body-local coordinate frame from hip/shoulder landmarks,
transforms all points into that frame (so the player always faces +Z regardless
of the camera angle in the video), then computes shortest-arc rotations from
T-pose reference directions to the observed joint directions.  Each rotation is
then made LOCAL by removing the accumulated parent world rotation.

Dependencies: scipy>=1.13.0, numpy>=1.26.0
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation
from typing import Sequence, Union

# ---------------------------------------------------------------------------
# MediaPipe landmark indices
# ---------------------------------------------------------------------------

IDX = {
    "nose":       0,
    "l_shoulder": 11,
    "r_shoulder": 12,
    "l_elbow":    13,
    "r_elbow":    14,
    "l_wrist":    15,
    "r_wrist":    16,
    "l_hip":      23,
    "r_hip":      24,
    "l_knee":     25,
    "r_knee":     26,
    "l_ankle":    27,
    "r_ankle":    28,
    "l_foot":     31,
    "r_foot":     32,
}

# ---------------------------------------------------------------------------
# T-pose reference directions in each bone's local parent space.
# These are the directions the bone segment points in the rest pose.
# ---------------------------------------------------------------------------

_T_POSE = {
    # Torso chain: each segment points upward
    "hips":          np.array([0.0,  1.0,  0.0]),
    "chest":         np.array([0.0,  1.0,  0.0]),
    "neck":          np.array([0.0,  1.0,  0.0]),
    # Arms: left side points left (-X), right side points right (+X)
    "leftUpperArm":  np.array([-1.0,  0.0,  0.0]),
    "leftLowerArm":  np.array([-1.0,  0.0,  0.0]),
    "rightUpperArm": np.array([ 1.0,  0.0,  0.0]),
    "rightLowerArm": np.array([ 1.0,  0.0,  0.0]),
    # Legs: all point downward (-Y)
    "leftUpperLeg":  np.array([0.0, -1.0,  0.0]),
    "leftLowerLeg":  np.array([0.0, -1.0,  0.0]),
    "rightUpperLeg": np.array([0.0, -1.0,  0.0]),
    "rightLowerLeg": np.array([0.0, -1.0,  0.0]),
}

# ---------------------------------------------------------------------------
# Bone chain: which bones are children of which (for parent-frame removal).
# We traverse in this order so parents are always computed before children.
# ---------------------------------------------------------------------------

# (bone_name, parent_bone_name or None)
_BONE_CHAIN = [
    ("hips",          None),
    ("chest",         "hips"),
    ("neck",          "chest"),
    ("rightUpperArm", "chest"),
    ("rightLowerArm", "rightUpperArm"),
    ("leftUpperArm",  "chest"),
    ("leftLowerArm",  "leftUpperArm"),
    ("rightUpperLeg", "hips"),
    ("rightLowerLeg", "rightUpperLeg"),
    ("leftUpperLeg",  "hips"),
    ("leftLowerLeg",  "leftUpperLeg"),
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(v: np.ndarray) -> np.ndarray:
    """Return unit vector; returns zeros if the input has near-zero length."""
    n = np.linalg.norm(v)
    if n < 1e-9:
        return np.zeros_like(v)
    return v / n


def _shortest_arc_rotation(from_dir: np.ndarray, to_dir: np.ndarray) -> Rotation:
    """
    Return the smallest rotation that takes unit vector *from_dir* to *to_dir*.
    Handles the degenerate anti-parallel case by choosing a perpendicular axis.
    """
    from_dir = _normalize(from_dir)
    to_dir   = _normalize(to_dir)

    dot = float(np.dot(from_dir, to_dir))
    dot = np.clip(dot, -1.0, 1.0)

    if dot > 0.9999999:
        # Vectors are nearly identical — no rotation needed.
        return Rotation.identity()

    if dot < -0.9999999:
        # Anti-parallel: pick an arbitrary perpendicular axis.
        perp = np.array([1.0, 0.0, 0.0])
        if abs(from_dir[0]) > 0.9:
            perp = np.array([0.0, 1.0, 0.0])
        axis = _normalize(np.cross(from_dir, perp))
        return Rotation.from_rotvec(axis * np.pi)

    axis  = _normalize(np.cross(from_dir, to_dir))
    angle = np.arccos(dot)
    return Rotation.from_rotvec(axis * angle)


def _build_body_frame(pts: dict[str, np.ndarray]) -> Rotation:
    """
    Construct a rotation that maps world space into body-local space where the
    player faces +Z, Y is up, and X is character-right.

    Returns the Rotation that, when applied to a world-space vector, gives
    the body-local vector.
    """
    l_hip  = pts["l_hip"]
    r_hip  = pts["r_hip"]
    l_sh   = pts["l_shoulder"]
    r_sh   = pts["r_shoulder"]

    mid_hip      = (l_hip + r_hip) / 2.0
    mid_shoulder = (l_sh + r_sh) / 2.0

    # Right axis: from left hip to right hip
    body_right = _normalize(r_hip - l_hip)

    # Approximate up: from mid-hip to mid-shoulder
    body_up_approx = _normalize(mid_shoulder - mid_hip)

    # Forward: right × up_approx  (will be orthogonal to right)
    body_forward = _normalize(np.cross(body_right, body_up_approx))

    # Re-orthogonalized up: forward × right is guaranteed perpendicular to both
    body_up = _normalize(np.cross(body_forward, body_right))

    # Build rotation matrix [right | up | forward] as columns.
    # This matrix transforms body-local axes → world axes.
    # Its transpose (= inverse for orthonormal) transforms world → body.
    rot_mat = np.column_stack([body_right, body_up, body_forward])  # 3x3

    # world_to_body_rotation: rotate world vectors into body frame
    # We want R such that R @ world_vec = body_vec
    # Since rot_mat @ body_vec ≈ world_vec, R = rot_mat.T
    return Rotation.from_matrix(rot_mat.T)


def _extract_pts(world_lm: list) -> dict[str, np.ndarray]:
    """
    Build a dict of landmark name → np.ndarray([x, y, z]) from the raw
    landmark list (which may be (x,y,z) or (x,y,z,visibility) tuples).
    """
    pts: dict[str, np.ndarray] = {}
    for name, idx in IDX.items():
        lm = world_lm[idx]
        # Accept both 3-element and 4-element tuples/objects.
        if hasattr(lm, "x"):
            pts[name] = np.array([lm.x, lm.y, lm.z], dtype=float)
        else:
            pts[name] = np.array(lm[:3], dtype=float)
    return pts


def _segment_frame(up_approx: np.ndarray, right: np.ndarray) -> Rotation:
    """
    Build a full 3D rotation from a segment's up-vector and right-vector.
    This captures axial (twist) rotation that a single direction vector misses.
    Returns the rotation whose matrix columns are [right, up, forward].
    """
    right   = _normalize(right)
    forward = _normalize(np.cross(right, up_approx))
    up      = _normalize(np.cross(forward, right))
    mat     = np.column_stack([right, up, forward])
    return Rotation.from_matrix(mat)


def _pelvis_frame(pts: dict[str, np.ndarray]) -> Rotation:
    """Full 3D rotation of the pelvis, capturing hip-turn (Y-axis twist)."""
    mid_hip = (pts["l_hip"] + pts["r_hip"]) / 2.0
    mid_sh  = (pts["l_shoulder"] + pts["r_shoulder"]) / 2.0
    return _segment_frame(
        up_approx=_normalize(mid_sh - mid_hip),
        right=_normalize(pts["r_hip"] - pts["l_hip"]),
    )


def _shoulder_frame(pts: dict[str, np.ndarray]) -> Rotation:
    """Full 3D rotation of the shoulder girdle, capturing shoulder-turn."""
    mid_hip = (pts["l_hip"] + pts["r_hip"]) / 2.0
    mid_sh  = (pts["l_shoulder"] + pts["r_shoulder"]) / 2.0
    return _segment_frame(
        up_approx=_normalize(mid_sh - mid_hip),
        right=_normalize(pts["r_shoulder"] - pts["l_shoulder"]),
    )


def _get_bone_world_rotation(
    bone: str,
    pts_body: dict[str, np.ndarray],
    nose_body: np.ndarray,
) -> Rotation:
    """
    Return the world-space Rotation for the given bone.
    Hips and chest use full 3D frame rotations (capturing axial twist).
    All other bones use shortest-arc from T-pose direction to observed direction.
    """
    p = pts_body

    # --- Trunk bones: use full frame rotation to capture Y-axis (hip/shoulder turn) ---
    if bone == "hips":
        return _pelvis_frame(p)

    if bone == "chest":
        return _shoulder_frame(p)

    # --- Direction-vector bones ---
    if bone == "neck":
        mid_sh = (p["l_shoulder"] + p["r_shoulder"]) / 2.0
        observed = _normalize(nose_body - mid_sh)
    else:
        mapping = {
            "rightUpperArm": ("r_shoulder", "r_elbow"),
            "rightLowerArm": ("r_elbow",    "r_wrist"),
            "leftUpperArm":  ("l_shoulder", "l_elbow"),
            "leftLowerArm":  ("l_elbow",    "l_wrist"),
            "rightUpperLeg": ("r_hip",      "r_knee"),
            "rightLowerLeg": ("r_knee",     "r_ankle"),
            "leftUpperLeg":  ("l_hip",      "l_knee"),
            "leftLowerLeg":  ("l_knee",     "l_ankle"),
        }
        src, dst = mapping[bone]
        observed = _normalize(p[dst] - p[src])

    if np.linalg.norm(observed) < 1e-9:
        return Rotation.identity()

    return _shortest_arc_rotation(_T_POSE[bone], observed)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_global_alignment(world_lm: list) -> Rotation:
    """
    Compute a FIXED alignment rotation from a reference (neutral) frame.

    This rotation maps world space → VRM canonical space where the player
    faces +Z and Y is up.  Pass the returned Rotation to every call of
    ``landmarks_to_vrm_pose`` so that hips/chest rotations in non-neutral
    frames reflect real pelvis/shoulder twist rather than being zeroed out.

    Use a frame where the player is standing relatively upright — e.g. a few
    frames before the backswing starts.
    """
    world_pts = _extract_pts(world_lm)
    return _build_body_frame(world_pts)


def landmarks_to_vrm_pose(
    world_lm: list,
    global_align: Rotation | None = None,
) -> dict[str, list[float]]:
    """
    Convert a single frame of MediaPipe *world* landmarks to VRM normalized
    bone Euler XYZ rotations.

    Parameters
    ----------
    world_lm : list
        Raw list of landmarks from ``result.pose_world_landmarks[0]``.
        Each element may be a MediaPipe ``Landmark`` object (with .x .y .z
        attributes) or a plain tuple/list ``(x, y, z[, visibility])``.
    global_align : Rotation, optional
        Fixed alignment rotation from ``compute_global_alignment()`` called
        on a neutral reference frame.  When provided, hips/chest rotations
        reflect real trunk twist relative to the neutral pose.  When None
        (legacy behaviour), a per-frame body frame is used and trunk
        rotations come out near-zero.

    Returns
    -------
    dict
        Maps VRM bone name → ``[euler_x, euler_y, euler_z]`` in radians,
        each value rounded to 3 decimal places.
    """
    # 1. Extract raw world-space positions.
    world_pts = _extract_pts(world_lm)

    # 2. Transform landmarks into canonical VRM space.
    #    With a fixed global_align the per-frame pelvis twist is preserved;
    #    without it we fall back to zeroing out trunk rotation (old behaviour).
    if global_align is not None:
        align = global_align
    else:
        align = _build_body_frame(world_pts)

    pts_body: dict[str, np.ndarray] = {
        name: align.apply(v) for name, v in world_pts.items()
    }
    nose_body = pts_body["nose"]

    # 3. Compute bone rotations, then make each LOCAL by removing parent world rot.
    world_rotations: dict[str, Rotation] = {}
    result: dict[str, list[float]] = {}

    for bone, parent in _BONE_CHAIN:
        world_rot = _get_bone_world_rotation(bone, pts_body, nose_body)
        world_rotations[bone] = world_rot

        if parent is not None and parent in world_rotations:
            local_rot = world_rotations[parent].inv() * world_rot
        else:
            local_rot = world_rot

        euler = local_rot.as_euler("xyz")
        result[bone] = [round(float(e), 3) for e in euler]

    return result
