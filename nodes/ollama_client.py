import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_OLLAMA_URL = "https://ollama.smixapp.com"
DEFAULT_OLLAMA_MODEL = "qwen3.6:27b"

PROMPT_RULES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompt_rules")


def _read_rule_file(filename: str) -> str:
    path = os.path.join(PROMPT_RULES_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def fetch_ollama_models(base_url: str = DEFAULT_OLLAMA_URL, timeout: float = 8.0) -> List[Dict[str, Any]]:
    """
    Fetch available models from https://ollama.smixapp.com/api/tags and filter out internal test entries.
    Returns a list of dicts with 'name' and 'capabilities'.
    """
    url = base_url.rstrip("/") + "/api/tags"
    req = urllib.request.Request(url, headers={"User-Agent": "ComfyUI-H3-Studio/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            if not name:
                continue
            # Filter out SSRF/probe artifacts or embedding-only models
            if any(bad in name for bad in ("rem_http", "rh_lo", "rh_ollamacom", "rce-test", "nomic-embed")):
                continue
            caps = m.get("capabilities", []) or []
            models.append({
                "name": name,
                "capabilities": caps,
                "has_vision": "vision" in caps,
            })
        return models
    except Exception:
        return [
            {"name": "minimax-m3:cloud", "capabilities": ["completion", "vision"], "has_vision": True},
            {"name": "qwen3.6:27b", "capabilities": ["completion", "vision"], "has_vision": True},
            {"name": "huihui_ai/Qwen3.8-abliterated:latest", "capabilities": ["completion", "vision"], "has_vision": True},
            {"name": "deepseek-v4-flash:cloud", "capabilities": ["completion"], "has_vision": False},
            {"name": "glm-5.2:cloud", "capabilities": ["completion"], "has_vision": False},
            {"name": "gemma3:latest", "capabilities": ["completion", "vision"], "has_vision": True},
        ]


def _get_failover_model_candidates(base_url: str, primary_model: str) -> List[str]:
    """
    Return an ordered list of failover models from the Ollama server (`GET /api/tags`),
    prioritizing local non-cloud models when a `:cloud` proxy model returns HTTP 500,
    as well as strong general models.
    """
    tags = fetch_ollama_models(base_url=base_url, timeout=5.0)
    server_names = [m["name"] for m in tags if m.get("name") and m["name"] != primary_model]

    # Prefer local models first (since `:cloud` models on Ollama can return 500 if cloud auth/upstream is down),
    # then other available models on the server
    preferred_order = [
        "qwen3.6:27b",
        "huihui_ai/Qwen3.8-abliterated:latest",
        "gemma3:latest",
        "qwen2.5:14b",
        "qwen2.5:7b",
        "llama3.3:latest",
        "llama3.1:latest",
        "deepseek-v4-flash:cloud",
        "glm-5.2:cloud",
        "minimax-m3:cloud",
    ]
    candidates: List[str] = []
    for p in preferred_order:
        if p != primary_model and p in server_names and p not in candidates:
            candidates.append(p)
    for s in server_names:
        if s != primary_model and s not in candidates:
            candidates.append(s)
    # If /api/tags had no extra models, still include top local defaults
    for fallback_default in ("qwen3.6:27b", "huihui_ai/Qwen3.8-abliterated:latest", "gemma3:latest"):
        if fallback_default != primary_model and fallback_default not in candidates:
            candidates.append(fallback_default)
    return candidates[:5]


def _call_ollama_text(
    ollama_url: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.45,
    timeout: float = 65.0,
) -> Tuple[Optional[str], str, str]:
    """
    Resilient Ollama text completion caller that tries:
    1. `/api/chat` on the requested `model_name`
    2. `/api/generate` on the requested `model_name` (in case chat template returns 500)
    3. Automatic failover across `_get_failover_model_candidates()` if the chosen model
       returns HTTP 500 Internal Server Error / 404 / 502 / 503.
    Returns `(response_text_or_None, used_model_name, error_or_status_detail)`.
    """
    base = ollama_url.rstrip("/")
    models_to_try = [model_name] + _get_failover_model_candidates(ollama_url, model_name)
    last_err = "Unknown error"

    for idx, m_name in enumerate(models_to_try):
        # Attempt A: /api/chat
        chat_url = base + "/api/chat"
        chat_payload = {
            "model": m_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": float(temperature)},
        }
        try:
            req = urllib.request.Request(
                chat_url,
                data=json.dumps(chat_payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "ComfyUI-H3-Studio/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
            raw = resp_json.get("message", {}).get("content", "").strip()
            if not raw and "response" in resp_json:
                raw = str(resp_json["response"]).strip()
            if raw:
                return raw, m_name, ("OK" if idx == 0 else f"Auto-Failover from {model_name} to {m_name}")
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="ignore")[:200]
            except Exception:
                pass
            last_err = f"HTTP {e.code} on {m_name}" + (f" ({err_body})" if err_body else f": {e.reason}")
            print(f"[H3-Studio] /api/chat failed for '{m_name}': {last_err}")
        except Exception as e:
            last_err = f"{m_name}: {e}"
            print(f"[H3-Studio] /api/chat exception for '{m_name}': {last_err}")

        # Attempt B: /api/generate (bypasses broken model chat templates on some Ollama builds)
        gen_url = base + "/api/generate"
        gen_payload = {
            "model": m_name,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {"temperature": float(temperature)},
        }
        try:
            req_g = urllib.request.Request(
                gen_url,
                data=json.dumps(gen_payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "ComfyUI-H3-Studio/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req_g, timeout=timeout) as resp_g:
                resp_g_json = json.loads(resp_g.read().decode("utf-8"))
            raw_g = str(resp_g_json.get("response", "")).strip()
            if raw_g:
                return raw_g, m_name, (
                    "OK (/api/generate)" if idx == 0 else f"Auto-Failover to {m_name} (/api/generate)"
                )
        except Exception as eg:
            print(f"[H3-Studio] /api/generate also failed for '{m_name}': {eg}")

    return None, model_name, last_err


def sanitize_dialogue_tags(prompt_text: str) -> str:
    """
    Ensure every <d>[Language] ...</d> tag strictly adheres to MiniMax-H3 dialogue punctuation rules:
    - No repeated tildes (~), emoji, bullets, or repeated exclamation/question marks
    - Ends with '.', '?', or '!' before </d>
    """
    def _clean_match(match: re.Match) -> str:
        lang = match.group(1).strip()
        body = match.group(2).strip()
        # Strip emojis and decorative characters
        body = re.sub(r"[~•●★☆✨🔥]+", "", body)
        body = re.sub(r"!{2,}", "!", body)
        body = re.sub(r"\?{2,}", "?", body)
        body = re.sub(r"\.{2,}", ".", body)
        body = body.strip()
        if body and body[-1] not in (".", "?", "!"):
            body += "."
        return f"<d>[{lang}] {body}</d>"

    return re.sub(r"<d>\s*\[([^\]]+)\]\s*(.*?)\s*</d>", _clean_match, prompt_text, flags=re.DOTALL)


def build_h3_system_prompt(mode: str) -> str:
    """
    Construct a concise, high-speed, authoritative system prompt for MiniMax-H3
    distilled from the official SKILL.md, base-en.txt, and ref-en.txt guides.
    Keeps token count compact (~1.5k tokens instead of 12k) so Ollama responds in seconds.
    """
    if mode.upper() == "REF2VA":
        return (
            "You are an expert MiniMax-H3 Video Prompt Writer operating in Full-Reference Mode (Ref2VA).\n"
            "Output ONLY the final MiniMax-H3 prompt containing these exact 6 sections in order (no markdown fences, no commentary):\n\n"
            "subject_definitions:\n"
            "(Define each active <Subject N>, <Picture N>, <Video N>, and <Audio N> on its own line. "
            "Example: `<Subject 1> is the young woman in <Picture 1>, wearing a blue cardigan.` "
            "If <Picture 1> is the opening frame anchor, write: `<Picture 1> is the first frame of [Shot 1], showing ...` "
            "If audio is used for a speaker: `<Audio 1> is the voice-timbre reference for <Subject 1> (S1).`)\n\n"
            "summary:\n"
            "([task_type] One short English paragraph summarizing the target video using the defined <Subject N>, <Picture N>, <Audio N> tags. "
            "Valid task types joined by ' + ': `keyframe completion`, `reference generation`, `video continuation`, `audio reuse`, `audio reference`.)\n\n"
            "retention_analysis:\n"
            "(One line per label stating where it appears and its retention marker: `fully_preserved`, `partially_preserved`, `attribute_transfer`, or `weak_reference` for visuals; `fully_copy`, `partially_copy`, `reference` for audio. "
            "Example: `<Subject 1> (appears in [Shot 1]): fully_preserved - facial identity, hair, and outfit are retained.`)\n\n"
            "detailed_description:\n"
            "(First write 1 sentence establishing visual style before [Shot 1]. Then write `[Shot 1] ...` in detailed chronological order. "
            "For later cuts use `[Shot 2] At 00:03.000, the camera cuts to ...`. "
            "Describe camera motion naturally using: Zoom In/Out, Push In/Pull Out, Pan Left/Right, Truck Left/Right, Tilt Up/Down, Tracking Shot, Static Shot + optional `with small/large amplitude` and `at slow/fast speed`.)\n\n"
            "overall_soundscape:\n"
            "(1-3 English sentences summarizing ambient sound and physical action sounds across the video.)\n\n"
            "non_diegetic_music:\n"
            "(1-2 English sentences describing background score instrumentation and tempo audible only to the audience, or `N/A`.)\n\n"
            "CRITICAL DIALOGUE (<d>) RULES:\n"
            "- Write all visual/narrative descriptions in English, but preserve spoken dialogue/lyrics verbatim in their ORIGINAL language inside `<d>[Language] ...</d>`.\n"
            "- Assign stable speaker IDs `(S1)`, `(S2)`. When a referenced character speaks, write `<Subject 1> (S1) says in a [voice description]: <d>[Indonesian] ...</d> She then closes her lips.`\n"
            "- For off-screen voiceover, write: `says in an off-screen voiceover: <d>[Language] ...</d> while his lips remain completely closed.`\n"
            "- Never repeat dialogue inside overall_soundscape or non_diegetic_music."
        )

    return (
        f"You are an expert MiniMax-H3 Video Prompt Writer operating in Base Mode ({mode.upper()}).\n"
        "Output ONLY the final MiniMax-H3 prompt (no markdown code fences, no explanations) following this exact structure:\n\n"
        "1. Opening Alignment Instruction Line (ONLY for I2VA, FL2VA, L2VA — omit for T2VA):\n"
        "- If I2VA: `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.`\n"
        "- If FL2VA: `How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.`\n"
        "- If L2VA: `How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.`\n"
        "(Follow the instruction line with one blank line.)\n\n"
        "2. Three Core Fields in Exact Order:\n"
        "integrated_multimodal_description: [Shot 1] <Visual style>, <composition, subjects, environment, camera motion (Push In/Pull Out/Pan/Truck/Tilt/Tracking/Static with small/large amplitude at slow/fast speed), actions, and synchronized diegetic audio>. "
        "(For I2VA, anchor [Shot 1] to `<Picture 1>` at 0.00s and develop the motion forward. For later cuts use `[Shot 2] At 00:03.000, the camera cuts to...`)\n\n"
        "overall_soundscape: <1-3 English sentences summarizing ambient and physical action sounds across the full video.>\n\n"
        "non_diegetic_music: <1-2 English sentences describing background music instrumentation and tempo, or N/A.>\n\n"
        "CRITICAL DIALOGUE (<d>) RULES:\n"
        "- Write narrative descriptions in English, but keep spoken dialogue verbatim in its ORIGINAL language inside `<d>[Language] ...</d>` (e.g. `the young woman with a soft voice (S1) says: <d>[Indonesian] Aku turun di stasiun berikutnya.</d> She closes her lips.`).\n"
        "- For voiceover, use `says in an off-screen voiceover: <d>[Language] ...</d> while their lips remain completely closed.`"
    )


def build_h3_user_message(
    user_idea: str,
    mode: str,
    effective_duration_sec: float,
    visual_style: str,
    ref_bundle: Optional[Dict[str, Any]] = None,
    dialogue_lines: Optional[List[Dict[str, str]]] = None,
    has_first_frame: bool = False,
    has_last_frame: bool = False,
    style_embedding: str = "none",
    continuity_context: Optional[Dict[str, Any]] = None,
    auto_continue_story: bool = False,
) -> str:
    """
    Assemble the structured user context describing active characters (<Subject N>),
    reference images (<Picture N>), audio references (<Audio N>), dialogue lines (<d>),
    and target video duration.
    """
    lines = [
        f"TARGET H3 MODE: {mode.upper()}",
        f"EFFECTIVE VIDEO DURATION: {effective_duration_sec:.2f} seconds (format S.SS = {effective_duration_sec:.2f})",
        f"VISUAL STYLE: {visual_style}",
    ]
    if style_embedding and style_embedding != "none":
        lines.append(f"STYLE EMBEDDING TOKEN TO INCLUDE AT START OF DESCRIPTION: {style_embedding}")

    if mode.upper() == "I2VA":
        lines.append(
            "MANDATORY FIRST LINE:\n"
            "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
        )
    elif mode.upper() == "FL2VA":
        lines.append(
            "MANDATORY FIRST LINE (replace N with actual final shot number):\n"
            f"How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the {effective_duration_sec:.2f}-second mark of the target video."
        )
    elif mode.upper() == "L2VA":
        lines.append(
            "MANDATORY FIRST LINE (replace N with actual final shot number):\n"
            f"How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the {effective_duration_sec:.2f}-second mark of the target video."
        )

    if ref_bundle and ref_bundle.get("enabled", False):
        lines.append("\n=== ACTIVE REFERENCE ASSETS & CHARACTER MAPPING ===")
        if ref_bundle.get("has_first_frame_anchor", False):
            lines.append(
                "- <Picture 1>: The actual first frame of [Shot 1] (video continuation / keyframe anchor from previous video segment)."
            )
        for char_entry in ref_bundle.get("characters", []):
            subj_tag = char_entry["subject_tag"]
            pic_tag = char_entry["picture_tag"]
            name_alias = char_entry.get("name", "").strip()
            traits = char_entry.get("visual_traits", "").strip()
            retention = char_entry.get("retention", "fully_preserved")
            speaker_id = char_entry.get("speaker_id", "")
            voice_desc = char_entry.get("voice_desc", "")
            audio_tag = char_entry.get("audio_tag", "")

            alias_note = f' (User calls this character "{name_alias}" in their idea — ALWAYS replace "{name_alias}" with {subj_tag} in the output!)' if name_alias else ""
            lines.append(
                f"- {subj_tag} (source: {pic_tag}){alias_note}: {traits or 'character shown in reference image'}. "
                f"Retention marker: {retention}."
            )
            if speaker_id or voice_desc:
                lines.append(
                    f"  Speaker & Voice info for {subj_tag}: Speaker ID = ({speaker_id or 'S1'}), Voice = {voice_desc or 'natural clear voice'}."
                )
            if audio_tag:
                lines.append(
                    f"  {audio_tag}: Voice-timbre reference for {subj_tag} ({speaker_id or 'S1'}). Retention marker: reference."
                )

        if ref_bundle.get("scene_entry"):
            sc = ref_bundle["scene_entry"]
            lines.append(
                f"- {sc['subject_tag']} (source: {sc['picture_tag']}): Scene/environment reference — {sc.get('description', 'environment in reference picture')}. Retention: {sc.get('retention', 'fully_preserved')}."
            )

    if dialogue_lines:
        lines.append("\n=== STRUCTURED DIALOGUE LINES TO INCORPORATE WITH <d> TAGS ===")
        for idx, dl in enumerate(dialogue_lines, start=1):
            spk = dl.get("speaker", "(S1)")
            lang = dl.get("language", "Indonesian")
            text = dl.get("text", "").strip()
            delivery = dl.get("delivery", "natural conversational tone")
            is_vo = dl.get("voiceover", False)
            if text:
                vo_str = " [OFF-SCREEN VOICEOVER - lips must remain completely closed]" if is_vo else " [ON-SCREEN LIP-SYNC]"
                lines.append(
                    f"{idx}. Speaker: {spk} | Delivery: {delivery}{vo_str} | Mandatory tag: <d>[{lang}] {text}</d>"
                )

    if continuity_context and continuity_context.get("is_continuation"):
        next_seg_num = continuity_context.get("next_segment_number", 2)
        last_prompt = (continuity_context.get("last_prompt") or "").strip()
        last_idea = (continuity_context.get("last_idea") or "").strip()
        lines.append(f"\n=== MULTI-SEGMENT CONTINUITY CONTEXT (EXTENDING TO SEGMENT #{next_seg_num}) ===")
        lines.append(
            "CRITICAL CONTINUITY RULE: This segment is a direct, seamless continuation starting at 0.00s from `<Picture 1>` "
            "(which is the exact final locked frame of the previous segment). "
            "Maintain the exact environment, lighting, camera focal length, subject clothing, and ambient soundscape so the cut between Segment "
            f"{next_seg_num - 1} and Segment {next_seg_num} is invisible."
        )
        if last_idea:
            lines.append(f"Previous Segment User Direction: {last_idea}")
        if last_prompt:
            lines.append(f"Previous Segment Compiled H3 Prompt (match its environment, lighting, and overall_soundscape):\n{last_prompt}")

    lines.append("\n=== USER STORY / SCENE REQUEST ===")
    if auto_continue_story and continuity_context and continuity_context.get("is_continuation"):
        direction_hint = user_idea.strip()
        lines.append(
            "AUTO-CONTINUE MODE: Inspect the attached `<Picture 1>` (final frame of the previous segment) and the Previous Segment H3 Prompt above. "
            "Write the natural next 5-second beat of action, subtle camera progression, and lifelike motion that evolves smoothly from `<Picture 1>` "
            "without teleporting subjects or changing the room/lighting."
            + (f" Incorporate this additional user direction for the new segment: {direction_hint}" if direction_hint else "")
        )
    else:
        lines.append(
            user_idea.strip()
            if user_idea.strip()
            else "Create a natural, vivid continuation of the reference frame/characters with lifelike motion and ambient sound."
        )
    lines.append(
        "\nNow write ONLY the complete MiniMax-H3 prompt strictly following all formatting, label, camera motion, and <d> dialogue rules."
    )
    return "\n".join(lines)


def generate_h3_prompt_via_ollama(
    user_idea: str,
    mode: str = "I2VA",
    effective_duration_sec: float = 5.0,
    visual_style: str = "Live-action, cinematic",
    ref_bundle: Optional[Dict[str, Any]] = None,
    dialogue_lines: Optional[List[Dict[str, str]]] = None,
    base64_images: Optional[List[str]] = None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    model_name: str = DEFAULT_OLLAMA_MODEL,
    style_embedding: str = "none",
    continuity_context: Optional[Dict[str, Any]] = None,
    auto_continue_story: bool = False,
    temperature: float = 0.4,
    timeout: float = 25.0,
) -> Tuple[str, str]:
    """
    Call https://ollama.smixapp.com/api/chat to generate a compliant MiniMax-H3 prompt.
    Returns (formatted_prompt, status_message).
    Falls back to a deterministic rule-compliant H3 prompt builder if network/model fails.
    """
    print(f"[H3-Studio] Requesting AI prompt rewrite via Ollama ({model_name} @ {ollama_url}, mode={mode})...")
    system_prompt = build_h3_system_prompt(mode)
    user_msg = build_h3_user_message(
        user_idea=user_idea,
        mode=mode,
        effective_duration_sec=effective_duration_sec,
        visual_style=visual_style,
        ref_bundle=ref_bundle,
        dialogue_lines=dialogue_lines,
        style_embedding=style_embedding,
        continuity_context=continuity_context,
        auto_continue_story=auto_continue_story,
    )

    user_message_obj: Dict[str, Any] = {
        "role": "user",
        "content": user_msg,
    }
    if base64_images:
        user_message_obj["images"] = [img for img in base64_images if img]

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            user_message_obj,
        ],
        "stream": False,
        "options": {
            "temperature": float(temperature),
        },
    }

    url = ollama_url.rstrip("/") + "/api/chat"
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ComfyUI-H3-Studio/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_json = json.loads(resp.read().decode("utf-8"))
        content = resp_json.get("message", {}).get("content", "").strip()
        if not content and "response" in resp_json:
            content = str(resp_json["response"]).strip()

        # Strip accidental <think>...</think> blocks or markdown code fences
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
        content = re.sub(r"\n?```$", "", content).strip()

        content = sanitize_dialogue_tags(content)
        if content:
            print(f"[H3-Studio] Ollama prompt generated successfully ({len(content)} chars).")
            return content, f"OK ({model_name} @ {ollama_url})"
    except urllib.error.HTTPError as e:
        # If vision images caused a 400 on a non-vision model, retry once without images
        if base64_images and e.code in (400, 422, 500):
            try:
                user_message_obj.pop("images", None)
                req2 = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "User-Agent": "ComfyUI-H3-Studio/1.0"},
                    method="POST",
                )
                with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                    resp_json2 = json.loads(resp2.read().decode("utf-8"))
                content2 = resp_json2.get("message", {}).get("content", "").strip()
                content2 = re.sub(r"<think>.*?</think>", "", content2, flags=re.DOTALL).strip()
                content2 = sanitize_dialogue_tags(content2)
                if content2:
                    return content2, f"OK (text-only fallback on {model_name})"
            except Exception:
                pass
        err_msg = f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        err_msg = str(e)

    # Multi-model automatic failover if primary model returns HTTP 500 / 404 / 502 / 503
    if any(code in err_msg for code in ("500", "404", "502", "503", "Internal Server Error")):
        raw_alt, used_alt, alt_status = _call_ollama_text(
            ollama_url=ollama_url,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_msg,
            temperature=temperature,
            timeout=timeout,
        )
        if raw_alt:
            content_alt = re.sub(r"<think>.*?</think>", "", raw_alt, flags=re.DOTALL).strip()
            content_alt = re.sub(r"^```[a-zA-Z]*\n?", "", content_alt)
            content_alt = re.sub(r"\n?```$", "", content_alt).strip()
            content_alt = sanitize_dialogue_tags(content_alt)
            if content_alt:
                return content_alt, f"OK ({alt_status})"

    # Local deterministic fallback so workflow never crashes if offline
    print(f"[H3-Studio] Ollama unavailable or timed out ({err_msg}). Using instant local H3 rule compiler.")
    fallback = build_local_fallback_h3_prompt(
        user_idea=user_idea,
        mode=mode,
        effective_duration_sec=effective_duration_sec,
        visual_style=visual_style,
        ref_bundle=ref_bundle,
        dialogue_lines=dialogue_lines,
        style_embedding=style_embedding,
    )
    return fallback, f"Fallback Template (Ollama error: {err_msg})"


def build_local_fallback_h3_prompt(
    user_idea: str,
    mode: str,
    effective_duration_sec: float,
    visual_style: str,
    ref_bundle: Optional[Dict[str, Any]] = None,
    dialogue_lines: Optional[List[Dict[str, str]]] = None,
    style_embedding: str = "none",
) -> str:
    """Deterministic MiniMax-H3 compliant prompt builder when offline."""
    emb_prefix = f"{style_embedding} " if (style_embedding and style_embedding != "none") else ""
    idea_clean = user_idea.strip() or "The subject moves naturally forward with fluid motion as the camera pushes in with small amplitude at slow speed."

    dlg_snippets = []
    if dialogue_lines:
        for dl in dialogue_lines:
            spk = dl.get("speaker", "(S1)")
            lang = dl.get("language", "Indonesian")
            txt = dl.get("text", "").strip()
            deliv = dl.get("delivery", "a natural conversational voice")
            if txt:
                if dl.get("voiceover"):
                    dlg_snippets.append(
                        f"{spk} says in an off-screen voiceover: <d>[{lang}] {txt}</d> while their lips remain completely closed."
                    )
                else:
                    dlg_snippets.append(
                        f"{spk} speaks in {deliv}: <d>[{lang}] {txt}</d> and then closes their lips naturally."
                    )
    dlg_block = (" " + " ".join(dlg_snippets)) if dlg_snippets else ""

    if mode.upper() == "REF2VA" and ref_bundle and ref_bundle.get("enabled"):
        subj_defs = []
        ret_lines = []
        has_ff = ref_bundle.get("has_first_frame_anchor", False)
        if has_ff:
            subj_defs.append("<Picture 1> is the first frame of [Shot 1], establishing the opening composition and scene state.")
            ret_lines.append("<Picture 1> ([Shot 1] first frame): fully_preserved - the initial framing, lighting, and subject placement are retained at 0.00 seconds.")

        for c in ref_bundle.get("characters", []):
            st = c["subject_tag"]
            pt = c["picture_tag"]
            traits = c.get("visual_traits") or "the character with distinct facial features and attire"
            ret = c.get("retention", "fully_preserved")
            subj_defs.append(f"{st} is {traits} in {pt}.")
            ret_lines.append(f"{st} (appears in [Shot 1]): {ret} - character identity, facial features, and clothing are preserved.")
            if c.get("audio_tag"):
                at = c["audio_tag"]
                spk = c.get("speaker_id", "S1")
                subj_defs.append(f"{at} is the voice-timbre reference for {st} ({spk}).")
                ret_lines.append(f"{at}: reference - vocal timbre guides the spoken delivery of {st} without copying the raw signal.")

        task_types = ["reference generation"]
        if has_ff:
            task_types.insert(0, "keyframe completion")
        if any(c.get("audio_tag") for c in ref_bundle.get("characters", [])):
            task_types.append("audio reference")
        task_prefix = "[" + " + ".join(task_types) + "]"

        ff_open = "The shot begins from <Picture 1>. " if has_ff else ""
        prompt = (
            "subject_definitions:\n"
            + "\n".join(subj_defs)
            + "\n\nsummary:\n"
            + f"{task_prefix} The target video depicts the requested scene over {effective_duration_sec:.2f} seconds using the defined reference subjects.\n\n"
            + "retention_analysis:\n"
            + "\n".join(ret_lines)
            + "\n\ndetailed_description:\n"
            + f"{emb_prefix}The target video uses a {visual_style.lower()} style.\n"
            + f"[Shot 1] {ff_open}{idea_clean}{dlg_block}\n\n"
            + "overall_soundscape:\nNatural ambient room tone and subtle physical movement sounds accompany the scene throughout the video.\n\n"
            + "non_diegetic_music:\nN/A"
        )
        return sanitize_dialogue_tags(prompt)

    header = ""
    if mode.upper() == "I2VA":
        header = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n"
    elif mode.upper() == "FL2VA":
        header = (
            f"How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; "
            f"Picture 2 (from Shot 1) aligns with the {effective_duration_sec:.2f}-second mark of the target video.\n\n"
        )
    elif mode.upper() == "L2VA":
        header = (
            f"How the reference pictures align with the target video — <Picture 1> (from [Shot 1]) aligns with the {effective_duration_sec:.2f}-second mark of the target video.\n\n"
        )

    anchor_phrase = "beginning from the composition and subject state shown in <Picture 1>, " if mode.upper() == "I2VA" else ""
    body = (
        f"{header}integrated_multimodal_description: [Shot 1] {emb_prefix}{visual_style}, {anchor_phrase}{idea_clean}{dlg_block}\n\n"
        "overall_soundscape: Natural environmental ambience and synchronized physical movement sounds continue throughout the video.\n\n"
        "non_diegetic_music: N/A"
    )
    return sanitize_dialogue_tags(body)


def compute_adaptive_segment_duration(
    dialogue_lines: List[Dict[str, Any]],
    preferred_sec: float = 6.0,
    min_sec: float = 5.0,
    max_sec: float = 15.0,
) -> float:
    """
    Calculate the ideal MiniMax-H3 segment duration (clamped to [5.0 .. 15.0] seconds)
    so spoken <d> dialogue lines fit naturally at ~2.4 words/sec plus action breathing room.
    """
    total_words = 0
    for dl in dialogue_lines or []:
        txt = str(dl.get("text", "")).strip()
        if txt:
            total_words += len(txt.split())
    if total_words == 0:
        return max(min_sec, min(max_sec, float(preferred_sec)))
    # ~2.4 words per second + 1.8s visual establish/reaction buffer
    speech_sec = (total_words / 2.4) + 1.8
    target = max(float(preferred_sec), speech_sec)
    # Round to nearest 0.5s within [min_sec .. 15.0s]
    rounded = round(target * 2.0) / 2.0
    return max(min_sec, min(max_sec, rounded))


def compile_segment_h3_prompt(
    seg_item: Dict[str, Any],
    roster: List[Dict[str, Any]],
    visual_style: str = "Live-action, cinematic",
) -> str:
    """
    Build a complete, ready-to-render 6-section MiniMax-H3 Ref2VA (or I2VA/T2VA) prompt
    for a single storyboard segment based on its active_character_slots, transition_type,
    visual_action, dialogue_lines, soundscape, and duration_seconds.
    """
    t_type = str(seg_item.get("transition_type", "NEW_SCENE_CUT")).upper()
    has_ff = t_type == "CONTINUE_FRAME"
    eff_sec = float(seg_item.get("duration_seconds", 8.0))
    active_slots = seg_item.get("active_character_slots", [1])
    if not isinstance(active_slots, list) or not active_slots:
        active_slots = [1]

    # Map active_slots to dynamic <Subject 1..K> and <Picture 1..M>
    pic_idx = 1
    subj_defs: List[str] = []
    ret_lines: List[str] = []
    alias_to_subj: Dict[str, Tuple[str, str]] = {}

    if has_ff:
        subj_defs.append(
            f"<Picture {pic_idx}> is the first frame of [Shot 1], establishing the opening composition and scene state."
        )
        ret_lines.append(
            f"<Picture {pic_idx}> ([Shot 1] first frame): fully_preserved - the initial framing, lighting, and subject placement are retained at 0.00 seconds."
        )
        pic_idx += 1

    active_subj_idx = 0
    has_any_audio_ref = False
    audio_idx = 1

    for slot_num in active_slots:
        char_obj = next((c for c in roster if int(c.get("slot", 1)) == int(slot_num)), None)
        if not char_obj:
            char_obj = {
                "slot": slot_num,
                "name": f"Char{slot_num}",
                "speaker_id": f"S{slot_num}",
                "visual_traits": f"character {slot_num} with consistent appearance",
                "retention": "fully_preserved",
                "voice_desc": "natural expressive voice",
                "use_audio_ref": False,
            }
        active_subj_idx += 1
        st = f"<Subject {active_subj_idx}>"
        pt = f"<Picture {pic_idx}>"
        pic_idx += 1

        c_name = str(char_obj.get("name", f"Char{slot_num}")).strip()
        spk_id = str(char_obj.get("speaker_id", f"S{active_subj_idx}")).strip()
        traits = str(char_obj.get("visual_traits", "")).strip() or "the character with distinct facial features and attire"
        ret = str(char_obj.get("retention", "fully_preserved")).strip() or "fully_preserved"

        alias_to_subj[c_name.lower()] = (st, spk_id)
        alias_to_subj[f"char{slot_num}".lower()] = (st, spk_id)
        alias_to_subj[f"slot {slot_num}".lower()] = (st, spk_id)

        subj_defs.append(f"{st} is {traits} in {pt}.")
        ret_lines.append(
            f"{st} (appears in [Shot 1]): {ret} - character identity, facial features, and clothing are preserved."
        )

        if char_obj.get("use_audio_ref"):
            has_any_audio_ref = True
            at = f"<Audio {audio_idx}>"
            audio_idx += 1
            subj_defs.append(f"{at} is the voice-timbre reference for {st} ({spk_id}).")
            ret_lines.append(
                f"{at}: reference - vocal timbre guides the spoken delivery of {st} without copying the raw signal."
            )

    # Replace character names in visual_action with <Subject K> where helpful
    action_text = str(seg_item.get("visual_action", "")).strip()
    for alias_key, (st, _spk) in alias_to_subj.items():
        if alias_key and len(alias_key) >= 3:
            action_text = re.sub(rf"\b{re.escape(alias_key)}\b", st, action_text, flags=re.IGNORECASE)

    # Format <d> dialogue lines
    dlg_snippets: List[str] = []
    for d_idx, dl in enumerate(seg_item.get("dialogue_lines", []) or []):
        txt = str(dl.get("text", "")).strip()
        if not txt:
            continue
        raw_spk = str(dl.get("speaker", f"<Subject 1> (S1)")).strip()
        # Map speaker name if it matches an alias
        for alias_key, (st, spk_id) in alias_to_subj.items():
            if alias_key and alias_key in raw_spk.lower():
                raw_spk = f"{st} ({spk_id})"
                break
        lang = str(dl.get("language", "Indonesian")).strip() or "Indonesian"
        deliv = str(dl.get("delivery", "a natural expressive voice")).strip()
        if dl.get("voiceover"):
            dlg_snippets.append(
                f"{raw_spk} says in an off-screen voiceover: <d>[{lang}] {txt}</d> while their lips remain completely closed."
            )
        else:
            dlg_snippets.append(
                f"{raw_spk} speaks in {deliv}: <d>[{lang}] {txt}</d> and then closes their lips naturally."
            )

    dlg_block = (" " + " ".join(dlg_snippets)) if dlg_snippets else ""
    soundscape = (
        str(seg_item.get("soundscape", "")).strip()
        or "Natural environmental room tone, subtle footsteps, and cloth movement sounds accompany the scene throughout the video."
    )
    music = str(seg_item.get("music", "")).strip() or "N/A"
    summary_text = (
        str(seg_item.get("summary_line", "")).strip()
        or f"The target video depicts Segment {seg_item.get('segment_index', 1)} ({seg_item.get('act_title', 'Scene')}) over {eff_sec:.2f} seconds."
    )

    task_types = ["reference generation"]
    if has_ff:
        task_types.insert(0, "keyframe completion")
    if has_any_audio_ref:
        task_types.append("audio reference")
    task_prefix = "[" + " + ".join(task_types) + "]"

    ff_open = "The shot begins seamlessly from <Picture 1>. " if has_ff else ""
    full_prompt = (
        "subject_definitions:\n"
        + "\n".join(subj_defs)
        + "\n\nsummary:\n"
        + f"{task_prefix} {summary_text}\n\n"
        + "retention_analysis:\n"
        + "\n".join(ret_lines)
        + "\n\ndetailed_description:\n"
        + f"The target video uses a {visual_style.lower()} style.\n"
        + f"[Shot 1] {ff_open}{action_text}{dlg_block}\n\n"
        + f"overall_soundscape:\n{soundscape}\n\n"
        + f"non_diegetic_music:\n{music}"
    )
    return sanitize_dialogue_tags(full_prompt)


def _extract_json_array_robust(raw_text: str) -> Optional[List[Dict[str, Any]]]:
    """
    Robustly parse a JSON array of segment objects from LLM output even if wrapped in
    markdown blocks, trailing commas, or truncated at the end.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
    cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    start_idx = cleaned.find("[")
    if start_idx == -1:
        return None

    end_idx = cleaned.rfind("]")
    candidate = cleaned[start_idx : end_idx + 1] if (end_idx != -1 and end_idx > start_idx) else cleaned[start_idx:]
    # Remove trailing commas before } or ]
    candidate_fixed = re.sub(r",\s*([}\]])", r"\1", candidate)

    try:
        parsed = json.loads(candidate_fixed)
        if isinstance(parsed, list) and len(parsed) > 0:
            return parsed
    except Exception:
        pass

    # Fallback: extract individual top-level `{ ... }` segment objects if the array was truncated
    objects: List[Dict[str, Any]] = []
    depth = 0
    obj_start = -1
    in_str = False
    esc = False
    for idx, ch in enumerate(cleaned[start_idx:]):
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            if depth == 0:
                obj_start = start_idx + idx
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start != -1:
                frag = cleaned[obj_start : start_idx + idx + 1]
                frag = re.sub(r",\s*([}\]])", r"\1", frag)
                try:
                    obj = json.loads(frag)
                    if isinstance(obj, dict) and ("visual_action" in obj or "dialogue_lines" in obj):
                        objects.append(obj)
                except Exception:
                    pass
                obj_start = -1
    return objects if objects else None


def _split_long_story_into_acts(story_text: str, total_Acts: int) -> List[str]:
    """
    Split a potentially huge story manuscript (up to 10,000+ words) into `total_Acts`
    balanced narrative chunks along paragraph or sentence boundaries so each LLM call
    receives a clean, focused ~1,500–2,500 char chapter without overflowing Ollama's context.
    """
    cleaned = (story_text or "").strip()
    if not cleaned:
        return ["Two characters meet at a mysterious neon-lit cafe during a rainstorm to exchange a secret digital key, when a third rival character arrives."]
    if total_Acts <= 1 or len(cleaned) <= 2200:
        return [cleaned]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", cleaned) if p.strip()]
    if len(paragraphs) < total_Acts:
        paragraphs = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", cleaned) if s.strip()]

    if not paragraphs:
        return [cleaned[:2500]]

    acts: List[str] = []
    total_items = len(paragraphs)
    chunk_size = max(1, (total_items + total_Acts - 1) // total_Acts)
    for i in range(0, total_items, chunk_size):
        chunk_str = "\n\n".join(paragraphs[i : i + chunk_size]).strip()
        if chunk_str:
            # Cap single act chunk at 3800 chars so Ollama never hits 500 OOM on KV cache
            acts.append(chunk_str[:3800])
    return acts if acts else [cleaned[:2500]]


def generate_storyboard_plan_via_ollama(
    story_synopsis: str,
    target_total_duration_sec: float = 60.0,
    pacing_mode: str = "auto_adaptive",
    characters_roster: Optional[List[Dict[str, Any]]] = None,
    visual_style: str = "Live-action, cinematic",
    default_language: str = "Indonesian",
    ollama_url: str = DEFAULT_OLLAMA_URL,
    model_name: str = DEFAULT_OLLAMA_MODEL,
    timeout: float = 75.0,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Multi-Act Chunked AI Episode Prompt Generator:
    Handles both short premises and massive 5,000+ word story manuscripts!
    1. Splits long text into digestible Act chunks (~2,000–3,500 chars each) so Ollama never hits HTTP 500 OOM.
    2. Requests 6–8 segments per Act batch so JSON output is fast and never truncated.
    3. Compiles a complete 6-section MiniMax-H3 prompt (`compiled_h3_prompt`) for every single segment.
    """
    roster = characters_roster or [
        {"slot": 1, "name": "Char1", "speaker_id": "S1", "visual_traits": "lead character", "voice_desc": "clear natural voice"}
    ]
    roster_desc_lines = []
    for c in roster:
        s_num = c.get("slot", 1)
        c_name = c.get("name", f"Char{s_num}")
        spk = c.get("speaker_id", f"S{s_num}")
        traits = c.get("visual_traits", "character")
        v_desc = c.get("voice_desc", "natural voice")
        roster_desc_lines.append(
            f"- Slot {s_num}: Name='{c_name}', SpeakerID='({spk})', Visuals='{traits}', Voice='{v_desc}'"
        )
    roster_block = "\n".join(roster_desc_lines)

    if pacing_mode == "fast_5s":
        avg_seg_sec = 5.0
    elif pacing_mode == "standard_8s":
        avg_seg_sec = 8.0
    elif pacing_mode == "extended_12s":
        avg_seg_sec = 12.0
    elif pacing_mode == "max_15s":
        avg_seg_sec = 15.0
    else:
        avg_seg_sec = 8.0

    est_total_segments = max(2, min(48, int(round(float(target_total_duration_sec) / avg_seg_sec))))
    # Each LLM batch generates at most 6 segments (~1.5k output tokens) so Ollama responds fast and cleanly.
    # For longer durations or huge story manuscripts, we run up to 4 sequential Act batches (up to 24 segments per click).
    segs_per_batch = 6
    num_batches = max(1, min(4, (est_total_segments + segs_per_batch - 1) // segs_per_batch))
    if len(story_synopsis or "") > 3500 and num_batches < 2:
        num_batches = min(4, max(2, len(story_synopsis) // 2500))

    act_chunks = _split_long_story_into_acts(story_synopsis, num_batches)
    num_batches = len(act_chunks)

    system_prompt = (
        "You are an AI Episode Screenwriter & MiniMax-H3 Prompt Director.\n"
        "Transform the provided story act into a sequential JSON array of cinematic video segments.\n"
        "Invent vivid camera movements, dramatic progression, facial expressions, environmental soundscapes, and natural spoken dialogue lines for each segment.\n"
        "Output ONLY a valid JSON array `[ ... ]` with no markdown commentary.\n\n"
        "Each element in the JSON array MUST follow this schema:\n"
        "{\n"
        '  "segment_index": 1,\n'
        '  "act_title": "Act I - Scene Title",\n'
        '  "transition_type": "NEW_SCENE_CUT" or "CONTINUE_FRAME",\n'
        '  "active_character_slots": [1, 2],\n'
        '  "duration_seconds": 8.0,\n'
        '  "visual_action": "Detailed cinematic English description of camera motion (Push In / Tracking Shot / Pan), character blocking, micro-expressions, and physical action.",\n'
        '  "soundscape": "Specific ambient sounds and foley.",\n'
        '  "music": "N/A or background music mood",\n'
        '  "dialogue_lines": [\n'
        '    {"speaker": "<Subject 1> (S1)", "language": "' + default_language + '", "text": "Spoken dialogue line for this segment.", "delivery": "warm expressive tone", "voiceover": false}\n'
        "  ]\n"
        "}\n\n"
        "RULES:\n"
        "1. First segment of a new scene MUST be `NEW_SCENE_CUT`. Use `CONTINUE_FRAME` when continuing the exact same camera shot. Use `NEW_SCENE_CUT` every 3-4 segments.\n"
        "2. `active_character_slots`: Array of slot numbers (from Character Roster) visible/speaking in this segment.\n"
        f"3. Write `dialogue_lines[].text` in {default_language} and `visual_action` in cinematic English."
    )

    all_parsed_items: List[Dict[str, Any]] = []
    used_model_final = model_name
    last_err = ""
    prev_summary_tail = ""

    for batch_idx, act_text in enumerate(act_chunks):
        remaining_segs = est_total_segments - len(all_parsed_items)
        this_batch_count = max(2, min(segs_per_batch, remaining_segs if batch_idx == num_batches - 1 else segs_per_batch))

        continuity_note = (
            f"\nPREVIOUS ACT ENDING CONTEXT:\n{prev_summary_tail}\nContinue seamlessly into Act {batch_idx + 1}.\n"
            if prev_summary_tail
            else ""
        )
        user_prompt = (
            f"CHARACTER ROSTER (Slots 1..{len(roster)}):\n{roster_block}\n\n"
            f"VISUAL STYLE: {visual_style}\n"
            f"ACT {batch_idx + 1} OF {num_batches}: Generate {this_batch_count} sequential segments (~{avg_seg_sec:.0f}s each, between 5s and 15s).\n"
            f"{continuity_note}\n"
            f"STORY TEXT FOR ACT {batch_idx + 1}:\n{act_text}\n\n"
            f"Output ONLY the JSON array of {this_batch_count} segments:"
        )

        print(
            f"[H3-Studio] Generating Act {batch_idx + 1}/{num_batches} ({this_batch_count} segments, {len(act_text)} chars) via Ollama ({used_model_final})..."
        )
        raw_resp, used_model, status_detail = _call_ollama_text(
            ollama_url=ollama_url,
            model_name=used_model_final,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.5,
            timeout=timeout,
        )
        used_model_final = used_model
        if raw_resp:
            parsed = _extract_json_array_robust(raw_resp)
            if parsed and len(parsed) > 0:
                all_parsed_items.extend(parsed)
                last_item = parsed[-1]
                prev_summary_tail = f"Last segment action: {last_item.get('visual_action', '')}"
                continue
            last_err = f"Model {used_model} returned non-JSON text"
        else:
            last_err = status_detail
            break

    if all_parsed_items:
        normalized = _normalize_storyboard_segments(
            all_parsed_items, roster, pacing_mode, avg_seg_sec, default_language, visual_style
        )
        print(
            f"[H3-Studio] AI Episode Storyboard ready: {len(normalized)} full H3 prompts compiled across {num_batches} act(s) via {used_model_final}."
        )
        return normalized, f"AI Episode Generated ({len(normalized)} full H3 prompts across {num_batches} Act(s) via {used_model_final})"

    fallback_segs = _build_fallback_storyboard(
        story_synopsis=story_synopsis,
        segment_count=min(12, est_total_segments),
        roster=roster,
        avg_seg_sec=avg_seg_sec,
        default_language=default_language,
        visual_style=visual_style,
    )
    return fallback_segs, f"Offline Fallback ({last_err})"


def _normalize_storyboard_segments(
    raw_list: List[Dict[str, Any]],
    roster: List[Dict[str, Any]],
    pacing_mode: str,
    avg_seg_sec: float,
    default_language: str,
    visual_style: str = "Live-action, cinematic",
) -> List[Dict[str, Any]]:
    from .session_store import compute_h3_frame_length

    valid_slots = [int(c.get("slot", i + 1)) for i, c in enumerate(roster)] or [1]
    out: List[Dict[str, Any]] = []

    for idx, item in enumerate(raw_list):
        if not isinstance(item, dict):
            continue
        seg_num = idx + 1
        t_type = str(item.get("transition_type", "CONTINUE_FRAME" if idx > 0 else "NEW_SCENE_CUT")).upper()
        if idx == 0 or "NEW" in t_type or "CUT" in t_type:
            t_type = "NEW_SCENE_CUT"
        else:
            t_type = "CONTINUE_FRAME"

        slots = item.get("active_character_slots", [valid_slots[0]])
        if not isinstance(slots, list) or not slots:
            slots = [valid_slots[0]]
        clean_slots = [int(s) for s in slots if isinstance(s, (int, float, str)) and str(s).isdigit()]
        if not clean_slots:
            clean_slots = [valid_slots[0]]

        raw_dlgs = item.get("dialogue_lines", [])
        clean_dlgs = []
        if isinstance(raw_dlgs, list):
            for d_idx, dl in enumerate(raw_dlgs):
                if isinstance(dl, dict) and str(dl.get("text", "")).strip():
                    clean_dlgs.append({
                        "speaker": str(dl.get("speaker", f"<Subject {d_idx + 1}> (S{d_idx + 1})")),
                        "language": str(dl.get("language", default_language)),
                        "text": str(dl.get("text", "")).strip(),
                        "delivery": str(dl.get("delivery", "natural expressive voice")),
                        "voiceover": bool(dl.get("voiceover", False)),
                    })

        raw_dur = float(item.get("duration_seconds", avg_seg_sec))
        if pacing_mode == "auto_adaptive":
            dur_sec = compute_adaptive_segment_duration(clean_dlgs, preferred_sec=raw_dur)
        else:
            dur_sec = max(5.0, min(15.0, raw_dur))

        frame_len, eff_sec = compute_h3_frame_length(dur_sec, fps=24.0)
        seg_dict: Dict[str, Any] = {
            "segment_index": seg_num,
            "act_title": str(item.get("act_title", f"Segment {seg_num}")),
            "transition_type": t_type,
            "active_character_slots": clean_slots,
            "duration_seconds": eff_sec,
            "frame_length": frame_len,
            "visual_action": str(item.get("visual_action", "")).strip() or "The characters continue the scene with natural motion.",
            "soundscape": str(item.get("soundscape", "")).strip(),
            "music": str(item.get("music", "N/A")).strip(),
            "dialogue_lines": clean_dlgs,
            "status": "pending",
        }
        seg_dict["compiled_h3_prompt"] = compile_segment_h3_prompt(seg_dict, roster, visual_style=visual_style)
        out.append(seg_dict)
    return out


def _build_fallback_storyboard(
    story_synopsis: str,
    segment_count: int,
    roster: List[Dict[str, Any]],
    avg_seg_sec: float,
    default_language: str,
    visual_style: str = "Live-action, cinematic",
) -> List[Dict[str, Any]]:
    from .session_store import compute_h3_frame_length

    text = (story_synopsis or "").strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    if not sentences:
        sentences = [
            "Establishing shot of the main character arriving at the location with a cinematic slow push-in.",
            "The character looks around thoughtfully and speaks the opening line as ambient sounds fill the space.",
            "A second character enters the frame, reacting warmly and joining the conversation.",
            "Both characters walk forward together as the camera tracks alongside them smoothly.",
        ]

    all_slots = [int(c.get("slot", i + 1)) for i, c in enumerate(roster)] or [1]
    segs: List[Dict[str, Any]] = []

    for i in range(max(2, segment_count)):
        seg_num = i + 1
        beat_text = sentences[i % len(sentences)]
        t_type = "NEW_SCENE_CUT" if (i == 0 or i % 3 == 0) else "CONTINUE_FRAME"
        active_count = min(len(all_slots), 1 + (i // 2))
        active_slots = all_slots[:active_count]

        spk_slot = active_slots[i % len(active_slots)]
        char_obj = next((c for c in roster if int(c.get("slot", 1)) == spk_slot), roster[0])
        spk_idx = active_slots.index(spk_slot) + 1
        spk_id = char_obj.get("speaker_id", f"S{spk_slot}")

        quote_match = re.search(r'["“”]([^"“”]{3,140})["“”]', beat_text)
        dlg_text = quote_match.group(1).strip() if quote_match else ""

        dlgs = []
        if dlg_text:
            dlgs.append({
                "speaker": f"<Subject {spk_idx}> ({spk_id})",
                "language": default_language,
                "text": dlg_text,
                "delivery": char_obj.get("voice_desc", "natural conversational tone"),
                "voiceover": False,
            })

        dur_sec = compute_adaptive_segment_duration(dlgs, preferred_sec=avg_seg_sec)
        frame_len, eff_sec = compute_h3_frame_length(dur_sec, fps=24.0)

        seg_dict: Dict[str, Any] = {
            "segment_index": seg_num,
            "act_title": f"Part {(i // 3) + 1} - Beat {seg_num}",
            "transition_type": t_type,
            "active_character_slots": active_slots,
            "duration_seconds": eff_sec,
            "frame_length": frame_len,
            "visual_action": beat_text,
            "dialogue_lines": dlgs,
            "status": "pending",
        }
        seg_dict["compiled_h3_prompt"] = compile_segment_h3_prompt(seg_dict, roster, visual_style=visual_style)
        segs.append(seg_dict)
    return segs
