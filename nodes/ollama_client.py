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
    Construct the authoritative system prompt for MiniMax-H3 using the official bundled
    SKILL.md, base-en.txt, and ref-en.txt guides.
    """
    skill_md = _read_rule_file("SKILL.md")
    if mode.upper() == "REF2VA":
        guide_txt = _read_rule_file("ref-en.txt")
        mode_instruction = (
            "You are an expert MiniMax-H3 Video Prompt Writer operating in Full-Reference Mode (Ref2VA).\n"
            "You MUST output ONLY the final rewritten MiniMax-H3 prompt with the exact 6 sections in order:\n"
            "1. subject_definitions:\n"
            "2. summary:\n"
            "3. retention_analysis:\n"
            "4. detailed_description:\n"
            "5. overall_soundscape:\n"
            "6. non_diegetic_music:\n\n"
            "CRITICAL DIALOGUE (<d>) RULES:\n"
            "- Write all narrative/visual descriptions in English.\n"
            "- Preserve dialogue and lyrics in their ORIGINAL language inside <d>[Language] ...</d> (e.g., <d>[Indonesian] ...</d> or <d>[English] ...</d>).\n"
            "- Assign stable speaker IDs (S1), (S2) in order of vocal appearance. When a referenced character speaks, write `<Subject N> (Sx)` outside `<d>`.\n"
            "- State lip closure after a character finishes speaking (e.g. 'She closes her lips...'), or use `says in an off-screen voiceover: <d>[Language] ...</d> while his lips remain completely closed.` for voiceover.\n"
            "- Do NOT include markdown code fences (```), commentary, or explanations—output ONLY the raw H3 prompt text."
        )
    else:
        guide_txt = _read_rule_file("base-en.txt")
        mode_instruction = (
            f"You are an expert MiniMax-H3 Video Prompt Writer operating in Base Mode ({mode.upper()}).\n"
            "You MUST output ONLY the final rewritten MiniMax-H3 prompt following the exact structure in the guide:\n"
            "- For I2VA / FL2VA / L2VA: Begin with the exact required alignment instruction line on line 1, followed by a blank line.\n"
            "- Then provide the three core fields in exact order:\n"
            "  integrated_multimodal_description: [Shot 1] ...\n\n"
            "  overall_soundscape: ...\n\n"
            "  non_diegetic_music: ...\n\n"
            "CRITICAL DIALOGUE (<d>) RULES:\n"
            "- Write all narrative/visual descriptions in English.\n"
            "- Preserve any spoken dialogue or lyrics verbatim in their ORIGINAL language inside <d>[Language] ...</d> (e.g., <d>[Indonesian] ...</d> or <d>[English] ...</d>).\n"
            "- Assign stable speaker IDs (S1), (S2) to speaking characters and describe their voice timbre and lip closure.\n"
            "- Do NOT include markdown code fences (```), commentary, or explanations—output ONLY the raw H3 prompt text."
        )

    return f"{mode_instruction}\n\n=== OFFICIAL SKILL OVERVIEW ===\n{skill_md}\n\n=== OFFICIAL FORMAT GUIDE ===\n{guide_txt}"


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

    lines.append("\n=== USER STORY / SCENE REQUEST ===")
    lines.append(user_idea.strip() if user_idea.strip() else "Create a natural, vivid continuation of the reference frame/characters with lifelike motion and ambient sound.")
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
    temperature: float = 0.4,
    timeout: float = 90.0,
) -> Tuple[str, str]:
    """
    Call https://ollama.smixapp.com/api/chat to generate a compliant MiniMax-H3 prompt.
    Returns (formatted_prompt, status_message).
    Falls back to a deterministic rule-compliant H3 prompt builder if network/model fails.
    """
    system_prompt = build_h3_system_prompt(mode)
    user_msg = build_h3_user_message(
        user_idea=user_idea,
        mode=mode,
        effective_duration_sec=effective_duration_sec,
        visual_style=visual_style,
        ref_bundle=ref_bundle,
        dialogue_lines=dialogue_lines,
        style_embedding=style_embedding,
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
