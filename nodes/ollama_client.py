import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_OLLAMA_URL = "https://ollama.smixapp.com"
DEFAULT_OLLAMA_MODEL = "minimax-m3:cloud"

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


def generate_storyboard_plan_via_ollama(
    story_synopsis: str,
    target_total_duration_sec: float = 60.0,
    pacing_mode: str = "auto_adaptive",
    characters_roster: Optional[List[Dict[str, Any]]] = None,
    visual_style: str = "Live-action, cinematic",
    default_language: str = "Indonesian",
    ollama_url: str = DEFAULT_OLLAMA_URL,
    model_name: str = DEFAULT_OLLAMA_MODEL,
    timeout: float = 45.0,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Break a long story or episode script into a multi-segment MiniMax-H3 Storyboard Queue.
    Supports stories up to 10+ minutes (600s) by planning structured acts/scenes, assigning
    active character slots (1..N), writing natural <d> dialogue lines per segment, choosing
    between `CONTINUE_FRAME` (seamless frame extend) and `NEW_SCENE_CUT` (anti-degradation scene reset),
    and computing adaptive segment durations (5s - 15s max per H3 clip).
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

    # Determine segment duration target
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

    est_segments = max(2, min(80, int(round(float(target_total_duration_sec) / avg_seg_sec))))
    # To keep single LLM response fast & valid JSON, cap single batch generation at 24 segments
    # (for a 10-minute movie, users can either generate 24 x 12-15s segments = ~5-6 mins or click "+ Expand Next Act")
    batch_seg_count = min(24, est_segments)

    system_prompt = (
        "You are an Master AI Film Director & Screenwriter for the MiniMax-H3 Omni-Modal Video+Audio Engine.\n"
        "Your job is to break the user's story into a sequential array of video segments.\n"
        "Output ONLY a valid JSON array `[ ... ]` (no markdown fences, no commentary outside JSON).\n\n"
        "Each element in the JSON array MUST be an object with these exact keys:\n"
        "{\n"
        '  "segment_index": 1,\n'
        '  "act_title": "Act I - Opening",\n'
        '  "transition_type": "NEW_SCENE_CUT" or "CONTINUE_FRAME",\n'
        '  "active_character_slots": [1, 2],\n'
        '  "duration_seconds": 8.0,\n'
        '  "visual_action": "Detailed English description of camera motion (Push In/Pull Out/Pan/Tracking), character blocking, and scene action using character names",\n'
        '  "dialogue_lines": [\n'
        '    {"speaker": "<Subject 1> (S1)", "language": "' + default_language + '", "text": "Spoken line here.", "delivery": "warm expressive tone", "voiceover": false}\n'
        "  ]\n"
        "}\n\n"
        "RULES FOR HIGH-QUALITY MULTI-SEGMENT DIRECTION:\n"
        "1. `transition_type`: Segment 1 MUST be `NEW_SCENE_CUT`. Use `CONTINUE_FRAME` when the next segment continues the exact same shot/conversation seamlessly from the previous segment's final frame. "
        "Every 3 to 4 segments (or whenever location/camera angle changes), use `NEW_SCENE_CUT` so the video generator resets visual sharpness while keeping character faces locked via Ref2VA!\n"
        "2. `active_character_slots`: Array of integer slot numbers (from the Character Roster) visible or speaking in this segment. If a new character enters the story in a later segment, activate their slot number in that segment!\n"
        "3. `duration_seconds`: Must be between 5.0 and 15.0 seconds (MiniMax-H3 maximum is 15.0s). Match duration to the length of spoken dialogue (~2.5 words per second).\n"
        f"4. Write `visual_action` in vivid cinematic English, and write `dialogue_lines[].text` in {default_language}."
    )

    user_prompt = (
        f"CHARACTER ROSTER AVAILABLE (1..N):\n{roster_block}\n\n"
        f"VISUAL STYLE: {visual_style}\n"
        f"TARGET TOTAL DURATION: {target_total_duration_sec:.0f} seconds (~{batch_seg_count} segments in this plan, each 5.0s to 15.0s)\n\n"
        f"STORY / EPISODE SYNOPSIS:\n{story_synopsis.strip() or 'Two friends meet at a rainy train station, discover a mysterious map, and embark on a journey together as new allies join them.'}\n\n"
        f"Return ONLY the JSON array of {batch_seg_count} segments:"
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.45},
    }

    url = ollama_url.rstrip("/") + "/api/chat"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "ComfyUI-H3-Studio/1.0"},
        method="POST",
    )

    print(f"[H3-Studio] Generating {batch_seg_count}-segment Storyboard Plan via Ollama ({model_name})...")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_json = json.loads(resp.read().decode("utf-8"))
        raw = resp_json.get("message", {}).get("content", "").strip()
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        # Extract JSON array
        start_idx = raw.find("[")
        end_idx = raw.rfind("]")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            raw_json = raw[start_idx : end_idx + 1]
            parsed = json.loads(raw_json)
            if isinstance(parsed, list) and len(parsed) > 0:
                normalized = _normalize_storyboard_segments(parsed, roster, pacing_mode, avg_seg_sec, default_language)
                print(f"[H3-Studio] Storyboard Plan ready: {len(normalized)} segments.")
                return normalized, f"Planned {len(normalized)} segments via {model_name}"
    except Exception as e:
        err_msg = str(e)
        print(f"[H3-Studio] Storyboard Ollama fallback ({err_msg}). Building deterministic multi-segment plan.")
    else:
        err_msg = "Invalid JSON response"

    fallback_segs = _build_fallback_storyboard(
        story_synopsis=story_synopsis,
        segment_count=batch_seg_count,
        roster=roster,
        avg_seg_sec=avg_seg_sec,
        default_language=default_language,
    )
    return fallback_segs, f"Planned {len(fallback_segs)} segments (Local Storyboard Compiler: {err_msg})"


def _normalize_storyboard_segments(
    raw_list: List[Dict[str, Any]],
    roster: List[Dict[str, Any]],
    pacing_mode: str,
    avg_seg_sec: float,
    default_language: str,
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
        out.append({
            "segment_index": seg_num,
            "act_title": str(item.get("act_title", f"Segment {seg_num}")),
            "transition_type": t_type,
            "active_character_slots": clean_slots,
            "duration_seconds": eff_sec,
            "frame_length": frame_len,
            "visual_action": str(item.get("visual_action", "")).strip() or "The characters continue the scene with natural motion.",
            "dialogue_lines": clean_dlgs,
            "compiled_h3_prompt": "",
            "status": "pending",
        })
    return out


def _build_fallback_storyboard(
    story_synopsis: str,
    segment_count: int,
    roster: List[Dict[str, Any]],
    avg_seg_sec: float,
    default_language: str,
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
        # Every 3rd segment starts a fresh camera angle/cut to prevent long-chain VAE drift
        t_type = "NEW_SCENE_CUT" if (i == 0 or i % 3 == 0) else "CONTINUE_FRAME"
        # Progressively introduce characters across segments
        active_count = min(len(all_slots), 1 + (i // 2))
        active_slots = all_slots[:active_count]

        spk_slot = active_slots[i % len(active_slots)]
        char_obj = next((c for c in roster if int(c.get("slot", 1)) == spk_slot), roster[0])
        spk_idx = active_slots.index(spk_slot) + 1
        spk_id = char_obj.get("speaker_id", f"S{spk_slot}")

        # Extract quoted dialogue if user wrote quotes in their synopsis, otherwise create natural beat line
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

        segs.append({
            "segment_index": seg_num,
            "act_title": f"Part {(i // 3) + 1} - Beat {seg_num}",
            "transition_type": t_type,
            "active_character_slots": active_slots,
            "duration_seconds": eff_sec,
            "frame_length": frame_len,
            "visual_action": beat_text,
            "dialogue_lines": dlgs,
            "compiled_h3_prompt": "",
            "status": "pending",
        })
    return segs
