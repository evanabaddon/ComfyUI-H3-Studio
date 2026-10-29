import json
import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    import torch
    import torch.nn.functional as F
except ImportError:
    torch = None
    F = None

try:
    import folder_paths
    import comfy.sd
    import comfy.utils
except ImportError:
    folder_paths = None
    comfy = None

logger = logging.getLogger("ComfyUI-H3-Studio")


def get_available_loras() -> List[str]:
    if folder_paths is not None:
        try:
            loras = folder_paths.get_filename_list("loras")
            return ["None"] + list(loras)
        except Exception:
            pass
    return [
        "None",
        "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
        "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors",
        "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
    ]


def _resolve_fast_attention_callable(backend: str):
    """
    Resolve the requested fast attention kernel (SageAttention, FlashAttention-2, xFormers, or PyTorch SDPA)
    into a ComfyUI-compatible attention override function `(q, k, v, heads, mask=None, attn_precision=None, skip_reshape=False)`.
    """
    sage_fn = None
    flash_fn = None
    xformers_fn = None

    if backend in ("auto", "sage_attention"):
        try:
            from sageattention import sageattn
            sage_fn = sageattn
        except ImportError:
            pass

    if backend in ("auto", "flash_attention_2") and sage_fn is None:
        try:
            from flash_attn import flash_attn_func
            flash_fn = flash_attn_func
        except ImportError:
            pass

    if backend in ("auto", "xformers") and sage_fn is None and flash_fn is None:
        try:
            import xformers.ops as xops
            xformers_fn = xops.memory_efficient_attention
        except ImportError:
            pass

    selected_name = "pytorch_sdpa"
    if sage_fn is not None:
        selected_name = "sage_attention"
    elif flash_fn is not None:
        selected_name = "flash_attention_2"
    elif xformers_fn is not None:
        selected_name = "xformers"

    def custom_attn_override(q, k, v, heads, mask=None, attn_precision=None, skip_reshape=False, **kwargs):
        if torch is None:
            return q
        # Standardize tensor layout to [B, H, S, D] for SageAttention / SDPA
        if skip_reshape:
            # q, k, v already have head dimension [B, H, S, D]
            b, h, s_q, d = q.shape
            q_bhsd, k_bhsd, v_bhsd = q, k, v
        else:
            b, s_q, total_d = q.shape
            d = total_d // heads
            q_bhsd = q.view(b, s_q, heads, d).transpose(1, 2)
            k_bhsd = k.view(b, -1, heads, d).transpose(1, 2)
            v_bhsd = v.view(b, -1, heads, d).transpose(1, 2)

        out_bhsd = None
        if sage_fn is not None and mask is None:
            try:
                out_bhsd = sage_fn(q_bhsd, k_bhsd, v_bhsd, tensor_layout="HND", is_causal=False)
            except Exception:
                out_bhsd = None

        if out_bhsd is None and flash_fn is not None and mask is None and q_bhsd.dtype in (torch.float16, torch.bfloat16):
            try:
                # flash_attn_func expects [B, S, H, D]
                out_bshd = flash_fn(
                    q_bhsd.transpose(1, 2).contiguous(),
                    k_bhsd.transpose(1, 2).contiguous(),
                    v_bhsd.transpose(1, 2).contiguous(),
                     causal=False,
                )
                out_bhsd = out_bshd.transpose(1, 2)
            except Exception:
                out_bhsd = None

        if out_bhsd is None and xformers_fn is not None and mask is None:
            try:
                out_bshd = xformers_fn(
                    q_bhsd.transpose(1, 2).contiguous(),
                    k_bhsd.transpose(1, 2).contiguous(),
                    v_bhsd.transpose(1, 2).contiguous(),
                )
                out_bhsd = out_bshd.transpose(1, 2)
            except Exception:
                out_bhsd = None

        if out_bhsd is None:
            out_bhsd = F.scaled_dot_product_attention(q_bhsd, k_bhsd, v_bhsd, attn_mask=mask, is_causal=False)

        if skip_reshape:
            return out_bhsd
        return out_bhsd.transpose(1, 2).reshape(b, s_q, heads * d)

    return custom_attn_override, selected_name


class H3ModelSpeedAndLoraHub:
    """
    Accelerates MiniMax-H3 (33B Omni-Transformer) using Fast Attention (SageAttention / FlashAttn2 / SDPA),
    FP16/BF16 fast accumulation, optional torch.compile, and an Unlimited Dynamic LoRA Stack with per-LoRA On/Off toggles.
    """

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "model": ("MODEL",),
                "attention_backend": (
                    [
                        "auto (SageAttn -> FlashAttn2 -> SDPA)",
                        "sage_attention",
                        "flash_attention_2",
                        "xformers",
                        "pytorch_sdpa",
                        "comfy_default (no_override)",
                    ],
                    {"default": "auto (SageAttn -> FlashAttn2 -> SDPA)"},
                ),
                "fast_fp16_bf16_matmul": ("BOOLEAN", {"default": True}),
                "cache_adaln_modulation": ("BOOLEAN", {"default": True}),
                "torch_compile_transformer": ("BOOLEAN", {"default": False}),
                "default_steps_when_no_turbo": ("INT", {"default": 20, "min": 1, "max": 100, "step": 1}),
                "lora_stack_json": (
                    "STRING",
                    {
                        "default": json.dumps(
                            [
                                {
                                    "enabled": True,
                                    "name": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
                                    "model_strength": 1.0,
                                    "clip_strength": 1.0,
                                }
                            ]
                        ),
                        "multiline": False,
                    },
                ),
            },
            "optional": {
                "clip": ("CLIP",),
            },
        }

    RETURN_TYPES = ("MODEL", "CLIP", "INT", "STRING")
    RETURN_NAMES = ("model", "clip", "recommended_steps", "optimization_report")
    FUNCTION = "apply_speed_and_loras"
    CATEGORY = "MiniMax-H3 Studio/Speed & LoRA"

    def apply_speed_and_loras(
        self,
        model: Any,
        attention_backend: str = "auto (SageAttn -> FlashAttn2 -> SDPA)",
        fast_fp16_bf16_matmul: bool = True,
        cache_adaln_modulation: bool = True,
        torch_compile_transformer: bool = False,
        default_steps_when_no_turbo: int = 20,
        lora_stack_json: str = "[]",
        clip: Optional[Any] = None,
    ) -> Tuple[Any, Optional[Any], int, str]:
        work_model = model.clone() if hasattr(model, "clone") else model
        work_clip = clip.clone() if (clip is not None and hasattr(clip, "clone")) else clip
        report_lines = []

        # 1. Fast MatMul / CuDNN flags
        if torch is not None and fast_fp16_bf16_matmul:
            try:
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True
                torch.backends.cudnn.benchmark = True
                if hasattr(torch.backends.cuda.matmul, "allow_fp16_reduced_precision_reduction"):
                    torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction = True
                if hasattr(torch.backends.cuda.matmul, "allow_bf16_reduced_precision_reduction"):
                    torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction = True
                report_lines.append("MatMul: Fast TF32/FP16/BF16 accumulation enabled")
            except Exception as e:
                report_lines.append(f"MatMul setup note: {e}")

        # 2. Fast Attention Patching
        backend_key = attention_backend.split(" ")[0].strip()
        if backend_key != "comfy_default":
            attn_fn, active_backend = _resolve_fast_attention_callable(backend_key)
            try:
                if hasattr(work_model, "model_options"):
                    work_model.model_options = dict(work_model.model_options)
                    t_opts = dict(work_model.model_options.get("transformer_options", {}))
                    t_opts["optimized_attention_override"] = attn_fn
                    t_opts["h3_cache_adaln"] = bool(cache_adaln_modulation)
                    work_model.model_options["transformer_options"] = t_opts
                report_lines.append(f"Attention Backend: {active_backend} (AdaLN Cache={cache_adaln_modulation})")
            except Exception as e:
                report_lines.append(f"Attention patch fallback: {e}")
        else:
            report_lines.append("Attention Backend: ComfyUI Default")

        # 3. Unlimited Dynamic LoRA Stack Application
        recommended_steps = int(default_steps_when_no_turbo)
        applied_loras = []
        try:
            lora_entries = json.loads(lora_stack_json) if lora_stack_json.strip() else []
        except Exception:
            lora_entries = []

        for entry in lora_entries:
            if not isinstance(entry, dict):
                continue
            if not entry.get("enabled", True):
                continue
            lora_name = str(entry.get("name", "")).strip()
            if not lora_name or lora_name == "None":
                continue

            m_str = float(entry.get("model_strength", 1.0))
            c_str = float(entry.get("clip_strength", 1.0))
            if m_str == 0.0 and c_str == 0.0:
                continue

            # Detect H3 4-step or 8-step Turbo LoRAs to auto-recommend step count
            lower_name = lora_name.lower()
            if "4step" in lower_name or "4_step" in lower_name:
                recommended_steps = 4
            elif ("8step" in lower_name or "8_step" in lower_name) and recommended_steps > 8:
                recommended_steps = 8

            if folder_paths is not None and comfy is not None:
                try:
                    lora_path = folder_paths.get_full_path("loras", lora_name)
                    if lora_path:
                        lora_weights = comfy.utils.load_torch_file(lora_path, safe_load=True)
                        work_model, work_clip = comfy.sd.load_lora_for_models(
                            work_model, work_clip, lora_weights, m_str, c_str
                        )
                        applied_loras.append(f"{lora_name} (M:{m_str:.2f}, C:{c_str:.2f})")
                    else:
                        report_lines.append(f"LoRA not found on disk (skipped): {lora_name}")
                except Exception as e:
                    report_lines.append(f"LoRA error ({lora_name}): {e}")
            else:
                applied_loras.append(f"{lora_name} (M:{m_str:.2f})")

        if applied_loras:
            report_lines.append(f"Active LoRAs ({len(applied_loras)}): " + ", ".join(applied_loras))
        else:
            report_lines.append("Active LoRAs: None")

        # 4. Optional torch.compile on diffusion model
        if torch is not None and torch_compile_transformer and hasattr(torch, "compile"):
            try:
                if hasattr(work_model, "model") and hasattr(work_model.model, "diffusion_model"):
                    work_model.model.diffusion_model = torch.compile(
                        work_model.model.diffusion_model, mode="reduce-overhead"
                    )
                    report_lines.append("torch.compile: Enabled (reduce-overhead)")
            except Exception as e:
                report_lines.append(f"torch.compile skipped: {e}")

        report_lines.append(f"Recommended Scheduler Steps: {recommended_steps}")
        return (work_model, work_clip, recommended_steps, "\n".join(report_lines))
