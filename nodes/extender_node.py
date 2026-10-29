import json
from typing import Any, Dict, Optional, Tuple

try:
    import torch
except ImportError:
    torch = None

from .session_store import SessionStore, compute_tensor_signature, tensor_to_base64_jpeg


class H3InteractiveVideoExtender:
    """
    Interactive Video + Audio Timeline Editor & First-Frame Extender Node for MiniMax-H3.
    Allows scrubbing frames in-canvas, trimming segments before motion degrades, locking a
    First-Frame Reference (<Picture 1>), and seamlessly stitching all video + stereo audio segments.
    """

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 1.0}),
                "ingest_mode": (
                    [
                        "append_new_segment",
                        "replace_timeline",
                        "hold_current_timeline (do_not_append)",
                    ],
                    {"default": "append_new_segment"},
                ),
                "auto_skip_first_frame": ("BOOLEAN", {"default": True}),
                "audio_crossfade_ms": ("INT", {"default": 40, "min": 0, "max": 500, "step": 5}),
                "selected_global_frame": ("INT", {"default": -1, "min": -1, "max": 999999, "step": 1}),
                "trim_out_at_selected": ("BOOLEAN", {"default": False}),
                "timeline_state_json": ("STRING", {"default": "{}", "multiline": False}),
            },
            "optional": {
                "images": ("IMAGE",),
                "audio": ("AUDIO",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "AUDIO", "H3_EXT_CTX", "INT")
    RETURN_NAMES = (
        "reference_frame",
        "stitched_images",
        "stitched_audio",
        "extender_context",
        "total_frames",
    )
    FUNCTION = "process_timeline"
    CATEGORY = "MiniMax-H3 Studio/Timeline & Extender"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs) -> Any:
        # Re-evaluate when user changes selected frame, trim settings, or incoming images
        return f"{kwargs.get('selected_global_frame')}_{kwargs.get('trim_out_at_selected')}_{kwargs.get('timeline_state_json')}_{id(kwargs.get('images'))}"

    def process_timeline(
        self,
        fps: float = 24.0,
        ingest_mode: str = "append_new_segment",
        auto_skip_first_frame: bool = True,
        audio_crossfade_ms: int = 40,
        selected_global_frame: int = -1,
        trim_out_at_selected: bool = False,
        timeline_state_json: str = "{}",
        images: Optional[Any] = None,
        audio: Optional[Dict[str, Any]] = None,
        unique_id: str = "0",
    ) -> Dict[str, Any]:
        store = SessionStore.get()
        session = store.get_node_session(str(unique_id))
        session.fps = float(fps)

        # Apply any segment trim overrides persisted in timeline_state_json from the interactive DOM UI
        if timeline_state_json and timeline_state_json.strip() not in ("", "{}"):
            try:
                state_data = json.loads(timeline_state_json)
                seg_trims = state_data.get("segment_trims", [])
                for st in seg_trims:
                    idx = int(st.get("index", -1))
                    if 0 <= idx < len(session.segments):
                        t_start = st.get("trim_start")
                        t_end = st.get("trim_end")
                        if t_start is not None:
                            session.segments[idx].trim_start = max(
                                0, min(int(t_start), session.segments[idx].total_frames - 1)
                            )
                        if t_end is not None:
                            session.segments[idx].trim_end = max(
                                session.segments[idx].trim_start,
                                min(int(t_end), session.segments[idx].total_frames - 1),
                            )
            except Exception:
                pass

        # Ingest incoming images + audio batch if connected
        if images is not None and int(images.shape[0]) > 0:
            sig = compute_tensor_signature(images)
            if ingest_mode == "replace_timeline":
                session.replace_all_with_single_segment(images=images, audio=audio, fps=fps, signature=sig)
            elif ingest_mode == "append_new_segment":
                # Avoid appending the exact same tensor twice if user only re-ran downstream nodes
                if sig != session.last_input_signature or len(session.segments) == 0:
                    session.append_segment(
                        images=images,
                        audio=audio,
                        fps=fps,
                        auto_skip_first_frame=auto_skip_first_frame,
                        signature=sig,
                    )

        # Update playhead & reference frame selection if specified
        total_active = session.get_total_active_frames()
        if total_active > 0:
            target_global = (
                int(selected_global_frame)
                if int(selected_global_frame) >= 0
                else max(0, total_active - 1)
            )
            session.set_trim_and_lock_reference(
                global_frame=target_global,
                trim_at_playhead=bool(trim_out_at_selected),
            )

        ref_frame = session.get_reference_frame_tensor()
        stitched_imgs, stitched_aud = session.get_stitched_images_and_audio(crossfade_ms=int(audio_crossfade_ms))

        # Provide safe empty tensors if timeline is still empty (e.g. first run before any video exists)
        if torch is not None:
            if ref_frame is None:
                ref_frame = torch.zeros((1, 768, 1344, 3), dtype=torch.float32)
            if stitched_imgs is None:
                stitched_imgs = ref_frame.clone()
            if stitched_aud is None:
                num_samples = max(1, int(round((stitched_imgs.shape[0] / max(1.0, fps)) * 32000)))
                stitched_aud = {
                    "waveform": torch.zeros((1, 2, num_samples), dtype=torch.float32),
                    "sample_rate": 32000,
                }

        summary = session.to_summary()
        summary["reference_frame_b64"] = tensor_to_base64_jpeg(ref_frame, index=0, max_side=512)
        total_out_frames = int(stitched_imgs.shape[0]) if stitched_imgs is not None else 0

        ext_ctx = {
            "has_segments": session.get_total_active_frames() > 0,
            "segment_count": len(session.segments),
            "total_frames": total_out_frames,
            "total_duration_sec": round(total_out_frames / max(1.0, fps), 2),
            "fps": float(fps),
            "reference_frame_b64": summary["reference_frame_b64"],
        }

        return {
            "ui": {"h3_extender_summary": [summary]},
            "result": (ref_frame, stitched_imgs, stitched_aud, ext_ctx, total_out_frames),
        }
