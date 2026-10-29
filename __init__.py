"""
ComfyUI-H3-Studio
Interactive Video + Audio Extender, Multi-Character Reference Hub (On/Off),
AI Prompt Composer (Ollama @ https://ollama.smixapp.com/ with <d> dialogue rules),
and Fast Attention + Unlimited Dynamic LoRA Stack for MiniMax-H3.
"""

import json
import os
from typing import Any, Dict

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .nodes.model_lora_node import get_available_loras
from .nodes.ollama_client import (
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL,
    fetch_ollama_models,
    generate_h3_prompt_via_ollama,
)
from .nodes.session_store import SessionStore, compute_h3_frame_length

WEB_DIRECTORY = "./web"

# Register custom HTTP API routes on ComfyUI's PromptServer if running inside ComfyUI
try:
    from aiohttp import web
    from server import PromptServer

    routes = PromptServer.instance.routes

    @routes.get("/h3_studio/extender/state/{node_id}")
    async def api_get_extender_state(request: "web.Request") -> "web.Response":
        node_id = request.match_info.get("node_id", "0")
        session = SessionStore.get().get_node_session(node_id)
        return web.json_response(session.to_summary())

    @routes.get("/h3_studio/extender/frame/{node_id}/{frame_idx}")
    async def api_get_extender_frame(request: "web.Request") -> "web.Response":
        node_id = request.match_info.get("node_id", "0")
        frame_idx = int(request.match_info.get("frame_idx", "0"))
        session = SessionStore.get().get_node_session(node_id)
        jpeg_bytes = session.get_frame_jpeg_bytes(frame_idx, max_side=640)
        if jpeg_bytes is None:
            return web.Response(status=404, text="No frame in session")
        return web.Response(body=jpeg_bytes, content_type="image/jpeg")

    @routes.post("/h3_studio/extender/action")
    async def api_post_extender_action(request: "web.Request") -> "web.Response":
        data: Dict[str, Any] = await request.json()
        node_id = str(data.get("node_id", "0"))
        action = str(data.get("action", ""))
        session = SessionStore.get().get_node_session(node_id)

        if action == "clear":
            session.clear()
        elif action == "drop_last":
            session.drop_last_segment()
        elif action == "lock_playhead":
            g_frame = int(data.get("global_frame", 0))
            trim_here = bool(data.get("trim_at_playhead", False))
            session.set_trim_and_lock_reference(global_frame=g_frame, trim_at_playhead=trim_here)
        elif action == "update_segment_trim":
            seg_idx = int(data.get("segment_idx", 0))
            t_start = data.get("trim_start")
            t_end = data.get("trim_end")
            session.set_trim_and_lock_reference(
                segment_idx=seg_idx,
                trim_start=t_start,
                trim_end=t_end,
            )

        return web.json_response(session.to_summary())

    @routes.get("/h3_studio/loras")
    async def api_get_loras(request: "web.Request") -> "web.Response":
        return web.json_response({"loras": get_available_loras()})

    @routes.get("/h3_studio/ollama/models")
    async def api_get_ollama_models(request: "web.Request") -> "web.Response":
        base_url = request.query.get("ollama_url", DEFAULT_OLLAMA_URL)
        models = fetch_ollama_models(base_url=base_url)
        return web.json_response({"models": models, "ollama_url": base_url})

    @routes.post("/h3_studio/ollama/generate_prompt")
    async def api_post_generate_prompt(request: "web.Request") -> "web.Response":
        data: Dict[str, Any] = await request.json()
        user_idea = str(data.get("user_idea", ""))
        mode = str(data.get("mode", "I2VA")).split(" ")[0].strip()
        duration_sec = float(data.get("duration_seconds", 5.0))
        visual_style = str(data.get("visual_style", "Live-action, cinematic"))
        style_embedding = str(data.get("style_embedding", "none"))
        ollama_url = str(data.get("ollama_url", DEFAULT_OLLAMA_URL))
        ollama_model = str(data.get("ollama_model", DEFAULT_OLLAMA_MODEL))
        dialogue_lines = data.get("dialogue_lines", [])
        ref_bundle = data.get("ref_bundle", None)
        extender_node_id = data.get("extender_node_id", None)
        char_node_id = data.get("char_node_id", None)

        frame_length, effective_sec = compute_h3_frame_length(duration_sec, fps=24.0)

        # Pull cached character bundle and reference frame if available in SessionStore
        store = SessionStore.get()
        if ref_bundle is None and char_node_id and str(char_node_id) in store.character_previews:
            ref_bundle = store.character_previews[str(char_node_id)]

        b64_images = []
        if extender_node_id:
            ext_session = store.get_node_session(str(extender_node_id))
            ref_tensor = ext_session.get_reference_frame_tensor()
            if ref_tensor is not None:
                from .nodes.session_store import tensor_to_base64_jpeg
                b64_ff = tensor_to_base64_jpeg(ref_tensor, index=0, max_side=512)
                if b64_ff:
                    b64_images.append(b64_ff)

        if ref_bundle and isinstance(ref_bundle, dict):
            for tb in ref_bundle.get("base64_thumbnails", []):
                if tb and tb not in b64_images:
                    b64_images.append(tb)

        if mode.upper() == "AUTO":
            if ref_bundle and ref_bundle.get("enabled"):
                mode = "Ref2VA"
            elif b64_images:
                mode = "I2VA"
            else:
                mode = "T2VA"

        prompt_text, status = generate_h3_prompt_via_ollama(
            user_idea=user_idea,
            mode=mode,
            effective_duration_sec=effective_sec,
            visual_style=visual_style,
            ref_bundle=ref_bundle,
            dialogue_lines=dialogue_lines if isinstance(dialogue_lines, list) else [],
            base64_images=b64_images if b64_images else None,
            ollama_url=ollama_url,
            model_name=ollama_model,
            style_embedding=style_embedding,
        )
        return web.json_response(
            {
                "prompt": prompt_text,
                "status": status,
                "frame_length": frame_length,
                "effective_duration_sec": effective_sec,
                "resolved_mode": mode,
            }
        )

    @routes.get("/h3_studio/workflows/{name}")
    async def api_get_workflow_template(request: "web.Request") -> "web.Response":
        name = request.match_info.get("name", "H3_All_In_One_Studio.json")
        safe_name = os.path.basename(name)
        wf_path = os.path.join(os.path.dirname(__file__), "example_workflows", safe_name)
        if not os.path.exists(wf_path):
            return web.Response(status=404, text="Workflow template not found")
        with open(wf_path, "r", encoding="utf-8") as f:
            content = json.load(f)
        return web.json_response(content)

except Exception:
    # Not running inside ComfyUI server runtime (e.g. unit testing / CLI check)
    pass

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
