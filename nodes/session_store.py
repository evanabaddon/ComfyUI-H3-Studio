import base64
import io
import os
import shutil
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import torch
except ImportError:
    torch = None


def compute_h3_frame_length(duration_seconds: float, fps: float = 24.0) -> Tuple[int, float]:
    """
    Calculate MiniMax-H3 valid frame length using the official 17k + 5 grid rule at 24fps:
    max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17
    Returns (frame_length, effective_duration_seconds).
    """
    raw_frames = max(5, round(float(duration_seconds) * float(fps)))
    frame_length = raw_frames + (5 - (raw_frames % 17)) % 17
    effective_sec = round(frame_length / float(fps), 2)
    return int(frame_length), float(effective_sec)


def tensor_to_pil(image_tensor: Any, index: int = 0) -> Optional[Any]:
    """Convert a single frame from a ComfyUI IMAGE tensor [B, H, W, C] to PIL Image."""
    if image_tensor is None or np is None or Image is None:
        return None
    if torch is not None and isinstance(image_tensor, torch.Tensor):
        arr = image_tensor.detach().cpu().numpy()
    elif isinstance(image_tensor, np.ndarray):
        arr = image_tensor
    else:
        return None

    if arr.ndim == 4:
        idx = max(0, min(index, arr.shape[0] - 1))
        arr = arr[idx]
    elif arr.ndim != 3:
        return None

    arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def tensor_to_base64_jpeg(image_tensor: Any, index: int = 0, max_side: int = 768, quality: int = 85) -> Optional[str]:
    """Convert a single frame from a ComfyUI IMAGE tensor to base64 JPEG string (without data URI prefix)."""
    pil_img = tensor_to_pil(image_tensor, index=index)
    if pil_img is None:
        return None
    w, h = pil_img.size
    if max(w, h) > max_side:
        scale = max_side / float(max(w, h))
        pil_img = pil_img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


class SegmentEntry:
    """Represents a single generated video+audio clip segment in the H3 Extender timeline."""

    def __init__(
        self,
        segment_id: str,
        images: Any,
        audio: Optional[Dict[str, Any]] = None,
        fps: float = 24.0,
        trim_start: int = 0,
        trim_end: Optional[int] = None,
    ):
        self.segment_id = segment_id
        self.images = images  # Tensor [F, H, W, C]
        self.audio = audio    # Dict {"waveform": Tensor [B, C, S], "sample_rate": int} or None
        self.fps = float(fps)
        self.total_frames = int(images.shape[0]) if images is not None else 0
        self.trim_start = max(0, int(trim_start))
        self.trim_end = int(trim_end) if trim_end is not None else max(0, self.total_frames - 1)
        self.created_at = time.time()

    @property
    def active_frame_count(self) -> int:
        if self.total_frames == 0:
            return 0
        start = max(0, min(self.trim_start, self.total_frames - 1))
        end = max(start, min(self.trim_end, self.total_frames - 1))
        return (end - start) + 1

    def to_meta(self, index: int) -> Dict[str, Any]:
        return {
            "index": index,
            "segment_id": self.segment_id,
            "total_frames": self.total_frames,
            "trim_start": self.trim_start,
            "trim_end": self.trim_end,
            "active_frames": self.active_frame_count,
            "duration_sec": round(self.active_frame_count / max(1.0, self.fps), 2),
            "has_audio": self.audio is not None and "waveform" in self.audio,
        }


class NodeSessionState:
    """Holds multi-segment timeline state for a single H3InteractiveVideoExtender node instance."""

    def __init__(self, node_id: str, cache_dir: str):
        self.node_id = str(node_id)
        self.cache_dir = os.path.join(cache_dir, f"node_{self.node_id}")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.segments: List[SegmentEntry] = []
        self.fps: float = 24.0
        self.playhead_global_frame: int = 0
        self.locked_ref_segment_idx: int = -1
        self.locked_ref_local_frame: int = -1
        self.last_input_signature: Optional[str] = None
        self.lock = threading.Lock()

    def clear(self) -> None:
        with self.lock:
            self.segments.clear()
            self.playhead_global_frame = 0
            self.locked_ref_segment_idx = -1
            self.locked_ref_local_frame = -1
            self.last_input_signature = None
            if os.path.exists(self.cache_dir):
                shutil.rmtree(self.cache_dir, ignore_errors=True)
            os.makedirs(self.cache_dir, exist_ok=True)

    def drop_last_segment(self) -> bool:
        with self.lock:
            if not self.segments:
                return False
            removed = self.segments.pop()
            seg_dir = os.path.join(self.cache_dir, removed.segment_id)
            if os.path.exists(seg_dir):
                shutil.rmtree(seg_dir, ignore_errors=True)
            total = self.get_total_active_frames()
            self.playhead_global_frame = max(0, total - 1)
            self.locked_ref_segment_idx = -1
            self.locked_ref_local_frame = -1
            self.last_input_signature = None
            return True

    def append_segment(
        self,
        images: Any,
        audio: Optional[Dict[str, Any]] = None,
        fps: float = 24.0,
        auto_skip_first_frame: bool = True,
        signature: Optional[str] = None,
    ) -> SegmentEntry:
        with self.lock:
            self.fps = float(fps)
            seg_idx = len(self.segments)
            seg_id = f"seg_{seg_idx:03d}_{int(time.time() * 1000) % 100000}"
            # If this is segment 2+ and auto_skip_first_frame is True, skip frame 0 to prevent duplicate seam frame
            trim_start = 1 if (seg_idx > 0 and auto_skip_first_frame and int(images.shape[0]) > 1) else 0
            entry = SegmentEntry(
                segment_id=seg_id,
                images=images.detach().cpu() if (torch is not None and isinstance(images, torch.Tensor)) else images,
                audio=self._detach_audio(audio),
                fps=fps,
                trim_start=trim_start,
                trim_end=int(images.shape[0]) - 1,
            )
            self.segments.append(entry)
            if signature:
                self.last_input_signature = signature
            # Default playhead & reference frame to the very last frame of the newly added segment
            total = self.get_total_active_frames()
            self.playhead_global_frame = max(0, total - 1)
            self.locked_ref_segment_idx = len(self.segments) - 1
            self.locked_ref_local_frame = entry.trim_end
            return entry

    def replace_all_with_single_segment(
        self,
        images: Any,
        audio: Optional[Dict[str, Any]] = None,
        fps: float = 24.0,
        signature: Optional[str] = None,
    ) -> SegmentEntry:
        self.clear()
        return self.append_segment(
            images=images,
            audio=audio,
            fps=fps,
            auto_skip_first_frame=False,
            signature=signature,
        )

    @staticmethod
    def _detach_audio(audio: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if audio is None or not isinstance(audio, dict) or "waveform" not in audio:
            return None
        wf = audio["waveform"]
        if torch is not None and isinstance(wf, torch.Tensor):
            wf = wf.detach().cpu()
        return {
            "waveform": wf,
            "sample_rate": int(audio.get("sample_rate", 32000)),
        }

    def get_total_active_frames(self) -> int:
        return sum(seg.active_frame_count for seg in self.segments)

    def global_to_segment_local(self, global_frame: int) -> Tuple[int, int]:
        """Map a global timeline frame index (0 .. total_active-1) to (segment_index, local_frame_index_in_segment_tensor)."""
        if not self.segments:
            return (-1, 0)
        g = max(0, int(global_frame))
        running = 0
        for idx, seg in enumerate(self.segments):
            count = seg.active_frame_count
            if g < running + count:
                offset = g - running
                local_frame = seg.trim_start + offset
                return (idx, min(local_frame, seg.total_frames - 1))
            running += count
        last_idx = len(self.segments) - 1
        return (last_idx, self.segments[last_idx].trim_end)

    def set_trim_and_lock_reference(
        self,
        global_frame: Optional[int] = None,
        segment_idx: Optional[int] = None,
        trim_start: Optional[int] = None,
        trim_end: Optional[int] = None,
        trim_at_playhead: bool = False,
    ) -> Dict[str, Any]:
        with self.lock:
            if not self.segments:
                return self.to_summary()

            if segment_idx is not None and 0 <= int(segment_idx) < len(self.segments):
                seg = self.segments[int(segment_idx)]
                if trim_start is not None:
                    seg.trim_start = max(0, min(int(trim_start), seg.total_frames - 1))
                if trim_end is not None:
                    seg.trim_end = max(seg.trim_start, min(int(trim_end), seg.total_frames - 1))

            if global_frame is not None:
                self.playhead_global_frame = max(0, min(int(global_frame), max(0, self.get_total_active_frames() - 1)))
                s_idx, l_frame = self.global_to_segment_local(self.playhead_global_frame)
                self.locked_ref_segment_idx = s_idx
                self.locked_ref_local_frame = l_frame

                if trim_at_playhead and 0 <= s_idx < len(self.segments):
                    # Trim the selected segment's out-point to this frame and drop any segments after it
                    self.segments[s_idx].trim_end = l_frame
                    if s_idx < len(self.segments) - 1:
                        self.segments = self.segments[: s_idx + 1]
                    self.playhead_global_frame = max(0, self.get_total_active_frames() - 1)

            return self.to_summary()

    def get_reference_frame_tensor(self) -> Optional[Any]:
        """Return the single selected reference frame as a [1, H, W, C] tensor."""
        with self.lock:
            if not self.segments:
                return None
            if 0 <= self.locked_ref_segment_idx < len(self.segments):
                seg = self.segments[self.locked_ref_segment_idx]
                f_idx = max(0, min(self.locked_ref_local_frame, seg.total_frames - 1))
            else:
                seg = self.segments[-1]
                f_idx = max(0, min(seg.trim_end, seg.total_frames - 1))
            return seg.images[f_idx : f_idx + 1]

    def get_stitched_images_and_audio(self, crossfade_ms: int = 40) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
        """
        Concatenate all active segments according to their [trim_start .. trim_end] range,
        and slice/stitch their corresponding stereo audio tracks in exact sync!
        """
        with self.lock:
            if not self.segments or torch is None:
                return (None, None)

            image_chunks = []
            audio_chunks = []
            sample_rate = 32000
            target_h, target_w = None, None

            for seg in self.segments:
                if seg.total_frames == 0:
                    continue
                start_f = max(0, min(seg.trim_start, seg.total_frames - 1))
                end_f = max(start_f, min(seg.trim_end, seg.total_frames - 1))
                clip_imgs = seg.images[start_f : end_f + 1]

                if target_h is None:
                    target_h, target_w = clip_imgs.shape[1], clip_imgs.shape[2]
                elif clip_imgs.shape[1] != target_h or clip_imgs.shape[2] != target_w:
                    # Resize spatial dimensions to match the first segment
                    clip_nchw = clip_imgs.permute(0, 3, 1, 2)
                    clip_nchw = torch.nn.functional.interpolate(
                        clip_nchw, size=(target_h, target_w), mode="bilinear", align_corners=False
                    )
                    clip_imgs = clip_nchw.permute(0, 2, 3, 1)

                image_chunks.append(clip_imgs)

                # Sync audio slice with video frame trim
                if seg.audio is not None and "waveform" in seg.audio:
                    wf = seg.audio["waveform"]
                    sr = int(seg.audio.get("sample_rate", 32000))
                    sample_rate = sr
                    start_sample = int(round((start_f / max(1.0, seg.fps)) * sr))
                    end_sample = int(round(((end_f + 1) / max(1.0, seg.fps)) * sr))
                    total_samples = wf.shape[-1]
                    start_sample = max(0, min(start_sample, total_samples))
                    end_sample = max(start_sample, min(end_sample, total_samples))
                    sliced_wf = wf[..., start_sample:end_sample]
                    if sliced_wf.shape[-1] > 0:
                        audio_chunks.append(sliced_wf)
                else:
                    # Generate silence matching this segment's active duration if some segments have audio
                    dur_sec = (end_f - start_f + 1) / max(1.0, seg.fps)
                    num_samples = max(1, int(round(dur_sec * sample_rate)))
                    audio_chunks.append(torch.zeros((1, 2, num_samples), dtype=torch.float32))

            if not image_chunks:
                return (None, None)

            stitched_images = torch.cat(image_chunks, dim=0)

            has_any_real_audio = any(seg.audio is not None for seg in self.segments)
            if not has_any_real_audio or not audio_chunks:
                return (stitched_images, None)

            # Ensure consistent channel count across audio chunks (stereo = 2)
            normalized_audio_chunks = []
            for ac in audio_chunks:
                if ac.ndim == 2:
                    ac = ac.unsqueeze(0)
                if ac.shape[1] == 1:
                    ac = ac.repeat(1, 2, 1)
                normalized_audio_chunks.append(ac)

            stitched_waveform = self._stitch_audio_with_crossfade(
                normalized_audio_chunks, sample_rate=sample_rate, crossfade_ms=crossfade_ms
            )
            return (stitched_images, {"waveform": stitched_waveform, "sample_rate": sample_rate})

    @staticmethod
    def _stitch_audio_with_crossfade(chunks: List[Any], sample_rate: int, crossfade_ms: int) -> Any:
        if len(chunks) == 1 or crossfade_ms <= 0:
            return torch.cat(chunks, dim=-1)
        fade_samples = int((crossfade_ms / 1000.0) * sample_rate)
        if fade_samples <= 1:
            return torch.cat(chunks, dim=-1)

        out = chunks[0]
        for nxt in chunks[1:]:
            actual_fade = min(fade_samples, out.shape[-1] // 4, nxt.shape[-1] // 4)
            if actual_fade <= 1:
                out = torch.cat([out, nxt], dim=-1)
                continue
            fade_out = torch.linspace(1.0, 0.0, actual_fade, device=out.device, dtype=out.dtype)
            fade_in = torch.linspace(0.0, 1.0, actual_fade, device=nxt.device, dtype=nxt.dtype)
            overlap = out[..., -actual_fade:] * fade_out + nxt[..., :actual_fade] * fade_in
            out = torch.cat([out[..., :-actual_fade], overlap, nxt[..., actual_fade:]], dim=-1)
        return out

    def get_frame_jpeg_bytes(self, global_frame: int, max_side: int = 640) -> Optional[bytes]:
        with self.lock:
            if not self.segments:
                return None
            s_idx, l_frame = self.global_to_segment_local(global_frame)
            if s_idx < 0 or s_idx >= len(self.segments):
                return None
            seg = self.segments[s_idx]
            pil_img = tensor_to_pil(seg.images, index=l_frame)
            if pil_img is None:
                return None
            w, h = pil_img.size
            if max(w, h) > max_side:
                scale = max_side / float(max(w, h))
                pil_img = pil_img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BILINEAR)
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=82)
            return buf.getvalue()

    def to_summary(self) -> Dict[str, Any]:
        total_active = self.get_total_active_frames()
        return {
            "node_id": self.node_id,
            "fps": self.fps,
            "segment_count": len(self.segments),
            "total_active_frames": total_active,
            "total_duration_sec": round(total_active / max(1.0, self.fps), 2),
            "playhead_global_frame": min(self.playhead_global_frame, max(0, total_active - 1)),
            "locked_ref_segment_idx": self.locked_ref_segment_idx,
            "locked_ref_local_frame": self.locked_ref_local_frame,
            "segments": [seg.to_meta(i) for i, seg in enumerate(self.segments)],
        }


class SessionStore:
    """Global singleton store managing NodeSessionState instances across ComfyUI executions."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        base_temp = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache_sessions")
        os.makedirs(base_temp, exist_ok=True)
        self.base_temp = base_temp
        self.sessions: Dict[str, NodeSessionState] = {}
        self.character_previews: Dict[str, Dict[str, Any]] = {}
        self.latest_session_id: Optional[str] = None

    @classmethod
    def get(cls) -> "SessionStore":
        with cls._lock:
            if cls._instance is None:
                cls._instance = SessionStore()
            return cls._instance

    def get_node_session(self, node_id: str) -> NodeSessionState:
        nid = str(node_id)
        if nid == "latest" and self.latest_session_id and self.latest_session_id in self.sessions:
            return self.sessions[self.latest_session_id]
        if nid not in self.sessions:
            self.sessions[nid] = NodeSessionState(nid, self.base_temp)
        self.latest_session_id = nid
        return self.sessions[nid]

    def get_active_or_latest_session(self, timeline_id: str = "default") -> NodeSessionState:
        tid = str(timeline_id).strip()
        if tid and tid != "default" and tid in self.sessions:
            return self.sessions[tid]
        if self.latest_session_id and self.latest_session_id in self.sessions:
            return self.sessions[self.latest_session_id]
        # Fallback: return any session that has segments, or create "default"
        for s in self.sessions.values():
            if len(s.segments) > 0:
                return s
        return self.get_node_session("default")


def compute_tensor_signature(images: Any) -> str:
    """Compute a fast lightweight hash signature of an image batch tensor to detect new generation outputs."""
    if images is None:
        return "none"
    try:
        shape_str = "x".join(str(x) for x in images.shape)
        first_mean = float(images[0].float().mean().item())
        last_mean = float(images[-1].float().mean().item())
        mid_std = float(images[len(images) // 2].float().std().item())
        return f"{shape_str}:{first_mean:.5f}:{last_mean:.5f}:{mid_std:.5f}"
    except Exception:
        return f"id:{id(images)}"
