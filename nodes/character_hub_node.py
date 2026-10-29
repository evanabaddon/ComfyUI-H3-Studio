import json
from typing import Any, Dict, List, Optional, Tuple

from .session_store import SessionStore, tensor_to_base64_jpeg


DEFAULT_CHARACTERS_JSON = json.dumps(
    [
        {
            "slot": 1,
            "enabled": True,
            "name": "Char1",
            "visual_traits": "young woman with expressive eyes and consistent outfit from reference photo",
            "retention": "fully_preserved",
            "speaker_id": "S1",
            "voice_desc": "clear youthful female voice, natural conversational pace",
            "use_audio_ref": True,
        },
        {
            "slot": 2,
            "enabled": False,
            "name": "Char2",
            "visual_traits": "young man with short dark hair and casual jacket from reference photo",
            "retention": "fully_preserved",
            "speaker_id": "S2",
            "voice_desc": "calm warm male voice, steady cadence",
            "use_audio_ref": False,
        },
    ]
)


class H3CharacterReferenceHub:
    """
    Multi-Character & Asset Reference Manager for MiniMax-H3 (Ref2VA & Keyframe Hybrid).
    Supports an Unlimited Dynamic Character Roster (1..N characters in the story) with Master On/Off
    and individual per-character On/Off toggles without unplugging wires.
    Up to 6 physical reference image wires (`char_1_image` .. `char_6_image`) can be connected,
    and characters beyond 6 (or without reference photos) still maintain persistent `<Subject N>` visual & vocal definitions!
    Automatically packs the active characters for the current segment into the 5 `<Picture N>` and 3 `<Audio N>` slots
    accepted by MiniMaxH3ReferenceToVideo.
    """

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "use_character_refs": ("BOOLEAN", {"default": True}),
                "auto_fetch_extender_first_frame": ("BOOLEAN", {"default": True}),
                "characters_config_json": ("STRING", {"default": DEFAULT_CHARACTERS_JSON, "multiline": False}),
            },
            "optional": {
                "first_frame_override": ("IMAGE",),
                "char_1_image": ("IMAGE",),
                "char_2_image": ("IMAGE",),
                "char_3_image": ("IMAGE",),
                "char_4_image": ("IMAGE",),
                "char_5_image": ("IMAGE",),
                "char_6_image": ("IMAGE",),
                "scene_bg_image": ("IMAGE",),
                "char_1_audio": ("AUDIO",),
                "char_2_audio": ("AUDIO",),
                "char_3_audio": ("AUDIO",),
                "char_4_audio": ("AUDIO",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = (
        "H3_REF_BUNDLE",
        "IMAGE",
        "IMAGE",
        "IMAGE",
        "IMAGE",
        "IMAGE",
        "AUDIO",
        "AUDIO",
        "AUDIO",
        "BOOLEAN",
    )
    RETURN_NAMES = (
        "h3_ref_bundle",
        "ref_image_0",
        "ref_image_1",
        "ref_image_2",
        "ref_image_3",
        "ref_image_4",
        "ref_audio_0",
        "ref_audio_1",
        "ref_audio_2",
        "is_ref2va_active",
    )
    FUNCTION = "build_reference_bundle"
    CATEGORY = "MiniMax-H3 Studio/Characters & References"

    @classmethod
    def IS_CHANGED(cls, **kwargs) -> Any:
        session = SessionStore.get().get_active_or_latest_session()
        return f"{session.get_total_active_frames()}_{session.locked_ref_segment_idx}_{session.locked_ref_local_frame}_{kwargs.get('use_character_refs')}_{kwargs.get('auto_fetch_extender_first_frame')}_{kwargs.get('characters_config_json')}"

    def build_reference_bundle(
        self,
        use_character_refs: bool = True,
        auto_fetch_extender_first_frame: bool = True,
        characters_config_json: str = DEFAULT_CHARACTERS_JSON,
        first_frame_override: Optional[Any] = None,
        char_1_image: Optional[Any] = None,
        char_2_image: Optional[Any] = None,
        char_3_image: Optional[Any] = None,
        char_4_image: Optional[Any] = None,
        char_5_image: Optional[Any] = None,
        char_6_image: Optional[Any] = None,
        scene_bg_image: Optional[Any] = None,
        char_1_audio: Optional[Dict[str, Any]] = None,
        char_2_audio: Optional[Dict[str, Any]] = None,
        char_3_audio: Optional[Dict[str, Any]] = None,
        char_4_audio: Optional[Dict[str, Any]] = None,
        unique_id: str = "0",
    ) -> Dict[str, Any]:
        try:
            char_configs = json.loads(characters_config_json) if characters_config_json.strip() else []
            if not isinstance(char_configs, list):
                char_configs = []
        except Exception:
            char_configs = []

        slot_images = {
            1: char_1_image,
            2: char_2_image,
            3: char_3_image,
            4: char_4_image,
            5: char_5_image,
            6: char_6_image,
        }
        slot_audios = {
            1: char_1_audio,
            2: char_2_audio,
            3: char_3_audio,
            4: char_4_audio,
        }

        ordered_images: List[Any] = []
        ordered_audios: List[Dict[str, Any]] = []
        base64_thumbnails: List[str] = []
        active_characters_meta: List[Dict[str, Any]] = []
        all_roster_meta: List[Dict[str, Any]] = []
        ui_preview_cards: List[Dict[str, Any]] = []

        # Wireless First-Frame Bridge: if no explicit override wire is connected and auto_fetch_extender_first_frame is True,
        # pull the locked reference frame directly from the H3InteractiveVideoExtender session store (prevents DAG cycle errors!).
        effective_first_frame = first_frame_override
        if effective_first_frame is None and auto_fetch_extender_first_frame:
            ext_session = SessionStore.get().get_active_or_latest_session()
            if ext_session.get_total_active_frames() > 0:
                effective_first_frame = ext_session.get_reference_frame_tensor()

        has_ff_anchor = False
        if auto_fetch_extender_first_frame and effective_first_frame is not None:
            ordered_images.append(effective_first_frame)
            b64_ff = tensor_to_base64_jpeg(effective_first_frame, index=0, max_side=512)
            if b64_ff:
                base64_thumbnails.append(b64_ff)
            has_ff_anchor = True

        # Support unlimited characters from char_configs + any connected physical image slots
        config_by_slot: Dict[int, Dict[str, Any]] = {}
        max_slot = 4
        for idx, cfg in enumerate(char_configs):
            if isinstance(cfg, dict):
                s_num = int(cfg.get("slot", idx + 1))
                config_by_slot[s_num] = cfg
                if s_num > max_slot:
                    max_slot = s_num

        for s_num, img_val in slot_images.items():
            if img_val is not None and s_num > max_slot:
                max_slot = s_num

        for s_num in range(1, max_slot + 1):
            if s_num not in config_by_slot:
                config_by_slot[s_num] = {
                    "slot": s_num,
                    "enabled": slot_images.get(s_num) is not None,
                    "name": f"Char{s_num}",
                    "visual_traits": f"character {s_num} with consistent appearance",
                    "retention": "fully_preserved",
                    "speaker_id": f"S{s_num}",
                    "voice_desc": "natural clear voice",
                    "use_audio_ref": slot_audios.get(s_num) is not None,
                }

        subject_counter = 0
        speaker_counter = 0

        for s_num in sorted(config_by_slot.keys()):
            cfg = config_by_slot[s_num]
            img_tensor = slot_images.get(s_num)
            aud_dict = slot_audios.get(s_num)
            is_enabled = bool(cfg.get("enabled", True))
            thumb_b64 = tensor_to_base64_jpeg(img_tensor, index=0, max_side=384) if img_tensor is not None else None

            roster_item = {
                "slot": s_num,
                "enabled": is_enabled,
                "name": cfg.get("name", f"Char{s_num}").strip() or f"Char{s_num}",
                "visual_traits": cfg.get("visual_traits", "").strip(),
                "retention": cfg.get("retention", "fully_preserved"),
                "speaker_id": (cfg.get("speaker_id", "").strip() or f"S{s_num}").lstrip("(").rstrip(")"),
                "voice_desc": cfg.get("voice_desc", "").strip() or "natural clear voice",
                "has_image_wire": img_tensor is not None,
                "has_audio_wire": aud_dict is not None,
            }
            all_roster_meta.append(roster_item)

            if use_character_refs and is_enabled and (img_tensor is not None or cfg.get("visual_traits", "").strip()):
                subject_counter += 1
                speaker_counter += 1
                subj_tag = f"<Subject {subject_counter}>"

                # Pack up to 5 reference images into MiniMaxH3ReferenceToVideo
                if img_tensor is not None and len(ordered_images) < 5:
                    ordered_images.append(img_tensor)
                    pic_idx = len(ordered_images)
                    pic_tag = f"<Picture {pic_idx}>"
                    if thumb_b64:
                        base64_thumbnails.append(thumb_b64)
                else:
                    pic_tag = f"<Picture {min(5, subject_counter)}>"

                audio_tag = ""
                if bool(cfg.get("use_audio_ref", True)) and aud_dict is not None and len(ordered_audios) < 3:
                    ordered_audios.append(aud_dict)
                    audio_tag = f"<Audio {len(ordered_audios)}>"

                spk_id = cfg.get("speaker_id", "").strip() or f"S{speaker_counter}"
                entry_meta = {
                    "slot": s_num,
                    "subject_tag": subj_tag,
                    "picture_tag": pic_tag,
                    "audio_tag": audio_tag,
                    "name": cfg.get("name", f"Char{s_num}").strip(),
                    "visual_traits": cfg.get("visual_traits", "").strip(),
                    "retention": cfg.get("retention", "fully_preserved"),
                    "speaker_id": spk_id.lstrip("(").rstrip(")"),
                    "voice_desc": cfg.get("voice_desc", "").strip(),
                    "thumb_b64": thumb_b64,
                }
                active_characters_meta.append(entry_meta)
                ui_preview_cards.append({**entry_meta, "enabled": True})
            else:
                ui_preview_cards.append({
                    "slot": s_num,
                    "enabled": False,
                    "name": cfg.get("name", f"Char{s_num}"),
                    "thumb_b64": thumb_b64,
                })

        scene_entry = None
        if use_character_refs and scene_bg_image is not None and len(ordered_images) < 5:
            subject_counter += 1
            ordered_images.append(scene_bg_image)
            pic_idx = len(ordered_images)
            b64_scene = tensor_to_base64_jpeg(scene_bg_image, index=0, max_side=512)
            if b64_scene:
                base64_thumbnails.append(b64_scene)
            scene_entry = {
                "subject_tag": f"<Subject {subject_counter}>",
                "picture_tag": f"<Picture {pic_idx}>",
                "description": "the environment, lighting, and architectural background in the scene reference image",
                "retention": "fully_preserved",
            }

        is_ref2va_active = bool(use_character_refs and (len(active_characters_meta) > 0 or scene_entry is not None))

        ref_bundle = {
            "enabled": is_ref2va_active,
            "has_first_frame_anchor": has_ff_anchor,
            "characters": active_characters_meta,
            "all_roster": all_roster_meta,
            "scene_entry": scene_entry,
            "base64_thumbnails": base64_thumbnails,
            "active_image_count": len(ordered_images),
            "active_audio_count": len(ordered_audios),
        }

        # Cache previews in SessionStore so frontend live prompt generator can also inspect them
        SessionStore.get().character_previews[str(unique_id)] = ref_bundle

        # Pad outputs to fixed 5 image slots and 3 audio slots for MiniMaxH3ReferenceToVideo
        img_outs = [ordered_images[i] if i < len(ordered_images) else None for i in range(5)]
        aud_outs = [ordered_audios[i] if i < len(ordered_audios) else None for i in range(3)]

        return {
            "ui": {"h3_character_cards": ui_preview_cards},
            "result": (
                ref_bundle,
                img_outs[0],
                img_outs[1],
                img_outs[2],
                img_outs[3],
                img_outs[4],
                aud_outs[0],
                aud_outs[1],
                aud_outs[2],
                is_ref2va_active,
            ),
        }
