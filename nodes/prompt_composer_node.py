import json
from typing import Any, Dict, List, Optional, Tuple

from .ollama_client import (
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL,
    build_local_fallback_h3_prompt,
    fetch_ollama_models,
    generate_h3_prompt_via_ollama,
    sanitize_dialogue_tags,
)
from .session_store import SessionStore, compute_h3_frame_length, tensor_to_base64_jpeg


H3_STYLE_EMBEDDINGS = [
    "none",
    "embedding:minimaxh3_art_is_explosion",
    "embedding:minimaxh3_anime_cinema",
    "embedding:minimaxh3_cyberpunk_neon",
    "embedding:minimaxh3_dark_fantasy",
    "embedding:minimaxh3_documentary_film",
    "embedding:minimaxh3_ghibli_watercolor",
    "embedding:minimaxh3_noir_monochrome",
    "embedding:minimaxh3_retro_vhs",
    "embedding:minimaxh3_scifi_epic",
    "embedding:minimaxh3_stop_motion_clay",
]


class H3AIPromptComposer:
    """
    AI-Powered MiniMax-H3 Prompt Composer connected to https://ollama.smixapp.com/.
    Automatically formats user ideas and dialogue (<d>[Language] ...</d>) into the strict
    MiniMax-H3 prompt specifications (T2VA, I2VA, FL2VA, L2VA, or 6-section Ref2VA),
    and calculates the exact 17k + 5 frame length required by H3 at 24 FPS.
    """

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "user_idea": (
                    "STRING",
                    {
                        "default": "Char1 duduk santai di kedai kopi saat hujan turun di luar jendela, lalu menoleh ke kamera sambil tersenyum.",
                        "multiline": True,
                    },
                ),
                "mode": (
                    [
                        "Auto (Ref2VA if Characters ON, I2VA if First-Frame, else T2VA)",
                        "I2VA (First-Frame / Video Extend)",
                        "Ref2VA (Full Multi-Character Reference)",
                        "T2VA (Text to Video+Audio)",
                        "FL2VA (First & Last Frame)",
                        "L2VA (Last Frame Landing)",
                    ],
                    {"default": "Auto (Ref2VA if Characters ON, I2VA if First-Frame, else T2VA)"},
                ),
                "duration_seconds": ("FLOAT", {"default": 5.0, "min": 2.0, "max": 15.0, "step": 0.5}),
                "visual_style": (
                    [
                        "Live-action, cinematic",
                        "Realistic photographic style",
                        "2D-animated",
                        "3D CG",
                        "Claymation",
                        "Watercolor",
                        "Vintage film",
                    ],
                    {"default": "Live-action, cinematic"},
                ),
                "style_embedding": (H3_STYLE_EMBEDDINGS, {"default": "none"}),
                "ollama_url": ("STRING", {"default": DEFAULT_OLLAMA_URL, "multiline": False}),
                "ollama_model": ("STRING", {"default": DEFAULT_OLLAMA_MODEL, "multiline": False}),
                "send_vision_images": ("BOOLEAN", {"default": True}),
                "auto_rewrite_on_queue": ("BOOLEAN", {"default": False}),
                "dialogue_lines_json": (
                    "STRING",
                    {
                        "default": json.dumps(
                            [
                                {
                                    "speaker": "<Subject 1> (S1)",
                                    "language": "Indonesian",
                                    "text": "Akhirnya kamu datang juga, kopinya masih hangat.",
                                    "delivery": "clear youthful female voice with a warm tone",
                                    "voiceover": False,
                                }
                            ]
                        ),
                        "multiline": False,
                    },
                ),
                "generated_h3_prompt": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                    },
                ),
            },
            "optional": {
                "h3_ref_bundle": ("H3_REF_BUNDLE",),
                "first_frame_image": ("IMAGE",),
                "last_frame_image": ("IMAGE",),
                "extender_context": ("H3_EXT_CTX",),
            },
        }

    RETURN_TYPES = ("STRING", "INT", "FLOAT", "IMAGE", "STRING", "STRING")
    RETURN_NAMES = (
        "h3_prompt",
        "frame_length_17k5",
        "effective_duration_sec",
        "first_frame_for_h3",
        "resolved_mode",
        "ai_status",
    )
    FUNCTION = "compose_prompt"
    CATEGORY = "MiniMax-H3 Studio/AI Prompting (Ollama)"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs) -> Any:
        session = SessionStore.get().get_active_or_latest_session()
        return f"{session.get_total_active_frames()}_{session.locked_ref_segment_idx}_{session.locked_ref_local_frame}_{kwargs.get('user_idea')}_{kwargs.get('mode')}_{kwargs.get('duration_seconds')}_{kwargs.get('dialogue_lines_json')}_{kwargs.get('generated_h3_prompt')}"

    def compose_prompt(
        self,
        user_idea: str,
        mode: str = "Auto (Ref2VA if Characters ON, I2VA if First-Frame, else T2VA)",
        duration_seconds: float = 5.0,
        visual_style: str = "Live-action, cinematic",
        style_embedding: str = "none",
        ollama_url: str = DEFAULT_OLLAMA_URL,
        ollama_model: str = DEFAULT_OLLAMA_MODEL,
        send_vision_images: bool = True,
        auto_rewrite_on_queue: bool = False,
        dialogue_lines_json: str = "[]",
        generated_h3_prompt: str = "",
        h3_ref_bundle: Optional[Dict[str, Any]] = None,
        first_frame_image: Optional[Any] = None,
        last_frame_image: Optional[Any] = None,
        extender_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # 1. Calculate valid H3 frame length (17k + 5 at 24fps)
        frame_length, effective_sec = compute_h3_frame_length(duration_seconds, fps=24.0)

        # Wireless First-Frame Bridge: if no explicit first_frame_image wire is connected,
        # automatically pull the locked reference frame from the H3InteractiveVideoExtender session store!
        # This avoids ComfyUI "Circular node connection" DAG errors while seamlessly chaining segments.
        ext_session = SessionStore.get().get_active_or_latest_session()
        effective_first_frame = first_frame_image
        if effective_first_frame is None and ext_session.get_total_active_frames() > 0:
            effective_first_frame = ext_session.get_reference_frame_tensor()
        continuity_ctx = ext_session.get_continuity_context()

        # 2. Resolve effective H3 mode
        has_ref_chars = bool(h3_ref_bundle and h3_ref_bundle.get("enabled", False))
        has_ff = (
            effective_first_frame is not None
            or bool(extender_context and extender_context.get("has_segments"))
            or bool(h3_ref_bundle and h3_ref_bundle.get("has_first_frame_anchor"))
        )
        has_lf = last_frame_image is not None

        if mode.startswith("Auto"):
            if has_ref_chars:
                resolved_mode = "Ref2VA"
            elif has_ff and has_lf:
                resolved_mode = "FL2VA"
            elif has_ff:
                resolved_mode = "I2VA"
            elif has_lf:
                resolved_mode = "L2VA"
            else:
                resolved_mode = "T2VA"
        else:
            resolved_mode = mode.split(" ")[0].strip()

        # 3. Parse structured <d> dialogue lines
        try:
            dialogue_lines = json.loads(dialogue_lines_json) if dialogue_lines_json.strip() else []
            if not isinstance(dialogue_lines, list):
                dialogue_lines = []
        except Exception:
            dialogue_lines = []

        # 4. If auto_rewrite_on_queue is False, run with zero network delay:
        #    - Use generated_h3_prompt if the user already compiled/edited one in the UI
        #    - Otherwise instantly compile a MiniMax-H3 compliant prompt locally
        existing_clean = generated_h3_prompt.strip()
        if not auto_rewrite_on_queue:
            if existing_clean:
                final_prompt = sanitize_dialogue_tags(existing_clean)
                status = "Using pre-generated / edited H3 prompt (Instant Queue)"
            else:
                final_prompt = build_local_fallback_h3_prompt(
                    user_idea=user_idea,
                    mode=resolved_mode,
                    effective_duration_sec=effective_sec,
                    visual_style=visual_style,
                    ref_bundle=h3_ref_bundle,
                    dialogue_lines=dialogue_lines,
                    style_embedding=style_embedding,
                )
                status = f"Compiled locally in {resolved_mode} mode (0ms delay)"
            ext_session.pending_user_idea = user_idea
            ext_session.pending_h3_prompt = final_prompt
            ext_session.pending_resolved_mode = resolved_mode
            print(f"[H3-Studio] Prompt ready ({resolved_mode}, {frame_length} frames / {effective_sec}s): {status}")
            return {
                "ui": {
                    "h3_composed_prompt": [final_prompt],
                    "h3_ai_status": [status],
                    "h3_frame_length": [frame_length],
                    "h3_effective_sec": [effective_sec],
                },
                "result": (final_prompt, frame_length, effective_sec, effective_first_frame, resolved_mode, status),
            }

        # 5. Collect base64 thumbnails for Vision LLM if enabled
        vision_b64_list: List[str] = []
        if send_vision_images:
            if effective_first_frame is not None:
                b64_ff = tensor_to_base64_jpeg(effective_first_frame, index=0, max_side=512)
                if b64_ff:
                    vision_b64_list.append(b64_ff)
            elif extender_context and extender_context.get("reference_frame_b64"):
                vision_b64_list.append(extender_context["reference_frame_b64"])

            if h3_ref_bundle and h3_ref_bundle.get("base64_thumbnails"):
                for tb in h3_ref_bundle["base64_thumbnails"]:
                    if tb and tb not in vision_b64_list:
                        vision_b64_list.append(tb)

            if last_frame_image is not None:
                b64_lf = tensor_to_base64_jpeg(last_frame_image, index=0, max_side=512)
                if b64_lf:
                    vision_b64_list.append(b64_lf)

        # 6. Call Ollama endpoint (https://ollama.smixapp.com/api/chat)
        final_prompt, status = generate_h3_prompt_via_ollama(
            user_idea=user_idea,
            mode=resolved_mode,
            effective_duration_sec=effective_sec,
            visual_style=visual_style,
            ref_bundle=h3_ref_bundle,
            dialogue_lines=dialogue_lines,
            base64_images=vision_b64_list if send_vision_images else None,
            ollama_url=ollama_url,
            model_name=ollama_model,
            style_embedding=style_embedding,
            continuity_context=continuity_ctx,
        )
        ext_session.pending_user_idea = user_idea
        ext_session.pending_h3_prompt = final_prompt
        ext_session.pending_resolved_mode = resolved_mode

        return {
            "ui": {
                "h3_composed_prompt": [final_prompt],
                "h3_ai_status": [status],
                "h3_frame_length": [frame_length],
                "h3_effective_sec": [effective_sec],
            },
            "result": (final_prompt, frame_length, effective_sec, effective_first_frame, resolved_mode, status),
        }
