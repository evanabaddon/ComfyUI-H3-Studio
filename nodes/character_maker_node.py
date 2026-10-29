import base64
import io
import json
import os
import re
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

from .session_store import SessionStore, tensor_to_base64_jpeg, tensor_to_pil


CHARACTER_LIBRARY_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "character_library")
os.makedirs(CHARACTER_LIBRARY_DIR, exist_ok=True)


# ============================================================================
# Official PoopMan333/H3_Character_Sheet_Generator Prompt Templates
# ============================================================================
GENERAL_PURPOSE_A_PROMPT_6PANEL = (
    "<Subject 1> is the character shown in <Picture 1>.\n\n"
    "Take from <Picture 1> the character's identity: face shape and features, eye colour, hair colour, length and style, "
    "complete outfit including footwear, and any distinctive markings, tattoos, jewellery, or accessories that are part of who they are.\n\n"
    "Do not carry over anything the character is holding in <Picture 1>.\n"
    "Do not carry over their pose in <Picture 1>.\n"
    "Do not carry over the background or setting of <Picture 1>."
)

GENERAL_PURPOSE_A_PROMPT_EXPRESSIONS = (
    "<Subject 1> is the character shown in <Picture 1>.\n\n"
    "Copy the character's head and face exactly as they appear in <Picture 1>: the same face, the same hair, "
    "the same neckline and collar, and every feature already visible there, unchanged.\n\n"
    "Do not carry over anything the character is holding in <Picture 1>.\n"
    "Do not carry over the background or setting of <Picture 1>."
)

B_PROMPT_STANDARD_ORBIT_6_PANEL = (
    "[STYLE]\n"
    "The output matches the style of <Picture 1>. Sharp detail on eyes and face. The style never changes and never drifts between shots. No shadows.\n\n"
    "[STAGING]\n"
    "Solid light grey seamless backdrop, one flat uniform tone edge to edge, with no gradient, no vignette, no texture and no floor line. "
    "Nothing else is in frame. The subject casts no shadow onto the backdrop and no contact shadow on the ground beneath it, and it does not sit in its own shadow. "
    "Soft form shading on the subject itself is fine and should read its shape. Long telephoto lens, near-orthographic.\n\n"
    "The character holds one relaxed A-pose throughout: arms hanging slightly away from the body, palms toward the thighs, feet shoulder-width apart, "
    "head level, calm neutral expression, eyes open and looking forward.\n"
    "The subject is completely frozen, as rigid and motionless as a statue. Only the camera moves. There is no wind, no breeze, no air movement, "
    "no breathing, no settling, no sway, no secondary motion of any kind. Orientation, surfaces and lighting are identical in every shot, and the subject stays the same size in frame.\n\n"
    "[0-3 seconds] tight full shot of the subject. The camera makes one smooth fixed-speed orbit right around it, a full 360 degrees: "
    "starting square on the front, passing the left side a quarter of the way round, directly behind at halfway, the right side three quarters of the way round, "
    "and returning to the front. The subject does not move at all. Ends back on the front view at 3 seconds.\n\n"
    "[3-4 seconds] Camera snaps into a fast push-in on the character's face. Locked-off head and shoulders close-up, face square to camera, eyes into the lens. Ends on a sharp front-on face.\n\n"
    "[4-5 seconds] camera whip-pans and rotates to an orthogonal angle. Locked-off head and shoulders close-up, head turned to a three-quarter angle, eyes still forward. Ends on a clean three-quarter face.\n\n"
    "[CAMERA] One constant-speed orbit in beat 1, then locked off and static. The camera is the only thing in the scene that moves at any point. "
    "No zoom, no push in, no dolly, no tilt, no roll, no handheld shake, no motion blur, no dissolves.\n"
    "[AUDIO] Silence. No music, no room tone, no voices."
)

B_PROMPT_STANDARD_ORBIT_4_PANEL = (
    "[STYLE]\n"
    "The output matches the style of <Picture 1>. Sharp detail on eyes and face. The style never changes and never drifts between shots. No shadows.\n\n"
    "[STAGING]\n"
    "Solid light grey seamless backdrop, one flat uniform tone edge to edge, with no gradient, no vignette, no texture and no floor line. "
    "Nothing else is in frame. The subject casts no shadow onto the backdrop and no contact shadow on the ground beneath it, and it does not sit in its own shadow. "
    "Soft form shading on the subject itself is fine and should read its shape. Long telephoto lens, near-orthographic.\n\n"
    "The character holds one relaxed A-pose throughout: arms hanging slightly away from the body, palms toward the thighs, feet shoulder-width apart, "
    "head level, calm neutral expression, eyes open and looking forward.\n"
    "The subject is completely frozen, as rigid and motionless as a statue. Only the camera moves. There is no wind, no breeze, no air movement, "
    "no breathing, no settling, no sway, no secondary motion of any kind. Orientation, surfaces and lighting are identical in every shot, and the subject stays the same size in frame.\n\n"
    "[0-2 seconds] tight full shot of the subject. The camera makes one smooth fixed-speed orbit to the left around it, sweeping 180 degrees: "
    "starting square on the back, passing the left side a third of the way through this move, and ending square on the front at 2 seconds. The subject does not move at all. Ends on the back view at 2 seconds.\n\n"
    "[2-3 seconds] Camera whip-pans front and snaps into a fast push-in on the character's upper body. Locked-off head and shoulders close-up, face square to camera, eyes into the lens. Ends on a sharp front-on face at 3 seconds.\n\n"
    "[CAMERA] One constant-speed 180-degree orbit in beat 1, then a hard whip-pan back to front and a push-in for beat 2. No zoom, no dolly, no tilt, no roll, no handheld shake, no motion blur, no dissolves beyond the one whip-pan cut.\n"
    "[AUDIO] Silence. No music, no room tone, no voices."
)

B_PROMPT_ANIME2REAL_6_PANEL = (
    "Completely discard the anime face, large stylized eyes, line art, flat cel-shaded colors from the references. "
    "Generate a brand-new photorealistic human face and completely natural hair and skin.\n\n"
    "[STYLE]\n"
    "Fully photorealistic live-action, unretouched studio photograph. Completely natural bare face and body — zero makeup of any kind. "
    "Natural lip color, natural eyelashes and eyebrows only. Skin shows real texture. Mild natural film grain. Style never drifts.\n\n"
    + B_PROMPT_STANDARD_ORBIT_6_PANEL.split("[STAGING]", 1)[1].replace("", "[STAGING]", 1)
)

B_PROMPT_ANIME2REAL_4_PANEL = (
    "Completely discard the anime face, large stylized eyes, line art, flat cel-shaded colors from the references. "
    "Generate a brand-new photorealistic human face and completely natural hair and skin.\n\n"
    "[STYLE]\n"
    "Fully photorealistic live-action, unretouched studio photograph. Completely natural bare face and body — zero makeup of any kind. "
    "Natural lip color, natural eyelashes and eyebrows only. Skin shows real texture. Mild natural film grain. Style never drifts.\n\n"
    + B_PROMPT_STANDARD_ORBIT_4_PANEL.split("[STAGING]", 1)[1].replace("", "[STAGING]", 1)
)

B_PROMPT_EXPRESSIONS_6_PANEL = (
    "[STYLE]\n"
    "The output matches the style of <Picture 1>. Sharp detail on the eyes, brows and mouth. The style never changes and never drifts between shots. No shadows.\n\n"
    "[STAGING]\n"
    "Solid light grey seamless backdrop, one flat uniform tone edge to edge, with no gradient, no vignette, no texture and no floor line. "
    "Nothing else is in frame. The subject casts no shadow onto the backdrop and does not sit in its own shadow. Soft form shading on the subject itself is fine and should read its shape. Long telephoto lens, near-orthographic.\n\n"
    "Framing is a locked-off portrait from the shoulders to the top of the head: the crown sits just below the top edge of frame, the crop line falls across the shoulders. "
    "Face square to camera, eyes into the lens, head level and centred. This framing is identical in every shot — the head never changes size or position in frame.\n\n"
    "Only the face changes. The head does not turn, tilt, nod, lean or move at any point. The shoulders and body are completely frozen. "
    "There is no wind, no hair movement, no breathing, no sway, no secondary motion of any kind. Lighting is identical in every shot.\n\n"
    "Every expression is a microexpression: the smallest movement that still reads clearly. Only the brows, eyelids, gaze and mouth corners move, and only slightly. "
    "Each expression appears fully formed and is then held perfectly still, like a freeze frame. Changes between expressions happen as a single hard snap lasting under 0.1 seconds.\n\n"
    "[0-0.83 seconds] Expression 1 is already fully formed on the very first frame: GENTLE SMILE. Mouth corners lifted a small amount, lips closed and soft, a quiet warmth in the eyes.\n\n"
    "[0.83-1.67 seconds] Snap to Expression 2: SAD. Inner corners of the brows lifted very slightly, upper eyelids a little heavy, mouth corners barely turned down.\n\n"
    "[1.67-2.5 seconds] Snap to Expression 3: LAUGHING. Eyes closed with the lids curved in easy relaxed crescents, mouth open in a natural unforced laugh.\n\n"
    "[2.5-3.33 seconds] Snap to Expression 4: ANGRY. Brows lowered slightly and drawn a little inward, gaze fixed, steady and cool, lips closed and lightly pressed.\n\n"
    "[3.33-4.17 seconds] Snap to Expression 5: SURPRISED. Brows lifted with the forehead staying smooth, eyes a touch wider than normal, lips just parted.\n\n"
    "[4.17-5.0 seconds] Snap to Expression 6: CONCERN. Brows drawn slightly together with the inner corners raised a small amount, eyes alert and attentive.\n\n"
    "[CAMERA] Completely locked off and static for the entire clip. No orbit, no zoom, no push in, no dolly, no pan, no tilt, no roll, no handheld shake, no motion blur, no cuts, no dissolves.\n"
    "[AUDIO] Silence. No music, no room tone, no voices."
)


def _slugify_char_name(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "Char1").strip())
    return clean.strip("_") or "Char1"


def list_saved_characters() -> List[Dict[str, Any]]:
    """Scan `character_library/` and return metadata + thumbnail base64 for all saved characters."""
    os.makedirs(CHARACTER_LIBRARY_DIR, exist_ok=True)
    items: List[Dict[str, Any]] = []
    for entry in sorted(os.listdir(CHARACTER_LIBRARY_DIR)):
        folder = os.path.join(CHARACTER_LIBRARY_DIR, entry)
        meta_path = os.path.join(folder, "metadata.json")
        if os.path.isdir(folder) and os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                sheet_path = os.path.join(folder, "sheet.png")
                if os.path.exists(sheet_path) and Image is not None:
                    with Image.open(sheet_path) as im:
                        im_thumb = im.copy()
                        im_thumb.thumbnail((360, 240))
                        buf = io.BytesIO()
                        im_thumb.convert("RGB").save(buf, format="JPEG", quality=80)
                        meta["thumb_b64"] = base64.b64encode(buf.getvalue()).decode("utf-8")
                items.append(meta)
            except Exception:
                pass
    return items


def load_saved_character_image_tensor(character_id: str) -> Optional[Any]:
    """Load a saved character sheet PNG from `character_library/<character_id>/sheet.png` as a ComfyUI IMAGE tensor [1, H, W, 3]."""
    if not character_id or Image is None or np is None:
        return None
    safe_id = _slugify_char_name(character_id)
    sheet_path = os.path.join(CHARACTER_LIBRARY_DIR, safe_id, "sheet.png")
    if not os.path.exists(sheet_path):
        return None
    try:
        with Image.open(sheet_path) as im:
            rgb = im.convert("RGB")
            arr = np.asarray(rgb, dtype=np.float32) / 255.0
        if torch is not None:
            return torch.from_numpy(arr).unsqueeze(0)
        return arr[np.newaxis, ...]
    except Exception:
        return None


def stitch_character_sheet_grid(
    images: Any,
    sheet_preset: str,
    border_px: int = 6,
) -> Tuple[Any, List[int]]:
    """
    Extract exact turnaround/expression frames from a MiniMax-H3 video batch and stitch them
    into a clean multi-panel Character Reference Sheet (following PoopMan333/H3_Character_Sheet_Generator):
    - 6-Panel 360 Orbit (124f): indices [2, 21, 42, 63, 84, 113] -> 2 rows x 3 cols
    - 4-Panel 180 Orbit (73f):  indices [2, 24, 45, 68] -> 2 rows x 2 cols
    - 6-Panel Facial Expressions (124f): indices [10, 31, 52, 72, 93, 113] -> 2 rows x 3 cols
    """
    total = int(images.shape[0]) if images is not None else 0
    if total == 0:
        return images, []

    if "4-Panel" in sheet_preset:
        raw_indices = [2, 24, 45, 68]
        rows, cols = 2, 2
    elif "Expressions" in sheet_preset:
        raw_indices = [10, 31, 52, 72, 93, 113]
        rows, cols = 2, 3
    else:
        raw_indices = [2, 21, 42, 63, 84, 113]
        rows, cols = 2, 3

    # Map indices proportionally if batch length differs from 73 / 124
    ref_len = 73 if "4-Panel" in sheet_preset else 124
    picked_indices = []
    for r_idx in raw_indices:
        scaled = int(round((r_idx / float(max(1, ref_len - 1))) * max(0, total - 1)))
        picked_indices.append(max(0, min(scaled, total - 1)))

    if torch is not None and isinstance(images, torch.Tensor):
        panels = [images[i] for i in picked_indices]  # Each [H, W, C]
        h, w, c = panels[0].shape
        b_px = max(0, int(border_px))

        row_tensors = []
        for r in range(rows):
            row_panels = panels[r * cols : (r + 1) * cols]
            if b_px > 0:
                v_sep = torch.zeros((h, b_px, c), dtype=images.dtype, device=images.device)
                interleaved = []
                for p_i, p in enumerate(row_panels):
                    if p_i > 0:
                        interleaved.append(v_sep)
                    interleaved.append(p)
                row_t = torch.cat(interleaved, dim=1)
            else:
                row_t = torch.cat(row_panels, dim=1)
            row_tensors.append(row_t)

        if b_px > 0 and len(row_tensors) > 1:
            row_w = row_tensors[0].shape[1]
            h_sep = torch.zeros((b_px, row_w, c), dtype=images.dtype, device=images.device)
            full_rows = []
            for r_i, rt in enumerate(row_tensors):
                if r_i > 0:
                    full_rows.append(h_sep)
                full_rows.append(rt)
            grid = torch.cat(full_rows, dim=0).unsqueeze(0)
        else:
            grid = torch.cat(row_tensors, dim=0).unsqueeze(0)

        return grid, picked_indices

    return images[0:1], picked_indices


class H3CharacterSheetPromptNode:
    """
    Builds the exact A+B Turnaround / Facial Expression Prompt & Frame Length (73 or 124 frames)
    from `PoopMan333/H3_Character_Sheet_Generator` so users can feed a real face photo (`<Picture 1>`)
    plus optional outfit/accessory references (`<Picture 2..5>`) into `MiniMaxH3ReferenceToVideo`.
    """

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "character_name": ("STRING", {"default": "Char1", "multiline": False}),
                "sheet_preset": (
                    [
                        "6-Panel 360° Turnaround + Face Closeups (124 frames)",
                        "4-Panel 180° Fast Turnaround + Face (73 frames)",
                        "6-Panel Facial Expressions Sheet (124 frames)",
                        "6-Panel Anime/2D to Photorealistic Live-Action (124 frames)",
                        "4-Panel Anime/2D to Photorealistic Live-Action (73 frames)",
                    ],
                    {"default": "6-Panel 360° Turnaround + Face Closeups (124 frames)"},
                ),
                "identity_and_outfit_notes": (
                    "STRING",
                    {
                        "default": "Use the exact real face, eyes, and hair from <Picture 1>. Dress the character in a clean modern dark jacket and casual trousers.",
                        "multiline": True,
                    },
                ),
                "aspect_resolution": (
                    [
                        "768 x 1344 (Portrait 9:16 - Recommended for Full Body Turnaround)",
                        "1024 x 1024 (Square 1:1 - Recommended for Expressions Sheet)",
                        "1344 x 768 (Landscape 16:9)",
                    ],
                    {"default": "768 x 1344 (Portrait 9:16 - Recommended for Full Body Turnaround)"},
                ),
            },
            "optional": {
                "real_face_image": ("IMAGE",),
                "outfit_ref_image_2": ("IMAGE",),
                "accessory_ref_image_3": ("IMAGE",),
                "extra_ref_image_4": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("STRING", "INT", "INT", "INT", "IMAGE", "IMAGE", "IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = (
        "charsheet_h3_prompt",
        "frame_length",
        "width",
        "height",
        "ref_image_0_face",
        "ref_image_1_outfit",
        "ref_image_2_acc",
        "ref_image_3_extra",
        "sheet_preset_mode",
    )
    FUNCTION = "build_sheet_prompt"
    CATEGORY = "MiniMax-H3 Studio/Character Maker (Turnaround Sheet)"

    def build_sheet_prompt(
        self,
        character_name: str = "Char1",
        sheet_preset: str = "6-Panel 360° Turnaround + Face Closeups (124 frames)",
        identity_and_outfit_notes: str = "",
        aspect_resolution: str = "768 x 1344 (Portrait 9:16 - Recommended for Full Body Turnaround)",
        real_face_image: Optional[Any] = None,
        outfit_ref_image_2: Optional[Any] = None,
        accessory_ref_image_3: Optional[Any] = None,
        extra_ref_image_4: Optional[Any] = None,
    ) -> Tuple[str, int, int, int, Any, Any, Any, Any, str]:
        frame_length = 73 if "4-Panel" in sheet_preset else 124

        if "1024 x 1024" in aspect_resolution:
            width, height = 1024, 1024
        elif "1344 x 768" in aspect_resolution:
            width, height = 1344, 768
        else:
            width, height = 768, 1344

        # Build A-Prompt (Subject & Multi-Image Reference Definitions)
        a_lines = []
        if "Expressions" in sheet_preset:
            a_lines.append(GENERAL_PURPOSE_A_PROMPT_EXPRESSIONS)
        else:
            a_lines.append(GENERAL_PURPOSE_A_PROMPT_6PANEL)

        if outfit_ref_image_2 is not None:
            a_lines.append(
                "\n<Picture 2> provides the outfit/clothing reference for <Subject 1>. Dress <Subject 1> in the attire shown in <Picture 2> while keeping the exact face and head identity from <Picture 1>."
            )
        if accessory_ref_image_3 is not None:
            a_lines.append(
                "\n<Picture 3> provides additional accessory/detail reference for <Subject 1>."
            )
        if extra_ref_image_4 is not None:
            a_lines.append(
                "\n<Picture 4> provides supplementary styling reference for <Subject 1>."
            )

        notes_clean = (identity_and_outfit_notes or "").strip()
        if notes_clean:
            a_lines.append(f"\nAdditional Character Specification for {character_name} (<Subject 1>):\n{notes_clean}")

        a_prompt = "\n".join(a_lines)

        # Select B-Prompt (Orbit / Freeze-Statue / Expressions Staging)
        if "Anime/2D" in sheet_preset and "4-Panel" in sheet_preset:
            b_prompt = B_PROMPT_ANIME2REAL_4_PANEL
        elif "Anime/2D" in sheet_preset:
            b_prompt = B_PROMPT_ANIME2REAL_6_PANEL
        elif "4-Panel" in sheet_preset:
            b_prompt = B_PROMPT_STANDARD_ORBIT_4_PANEL
        elif "Expressions" in sheet_preset:
            b_prompt = B_PROMPT_EXPRESSIONS_6_PANEL
        else:
            b_prompt = B_PROMPT_STANDARD_ORBIT_6_PANEL

        if real_face_image is None and torch is not None:
            real_face_image = torch.full((1, height, width, 3), 0.5, dtype=torch.float32)

        full_prompt = f"{a_prompt}\n\n{b_prompt}"
        return (
            full_prompt,
            frame_length,
            width,
            height,
            real_face_image,
            outfit_ref_image_2,
            accessory_ref_image_3,
            extra_ref_image_4,
            sheet_preset,
        )


class H3CharacterSheetStitcherAndSaver:
    """
    Takes the decoded 73-frame or 124-frame turnaround video batch from MiniMax-H3,
    extracts the exact orbit & close-up angles (Front, Left, Back, Right, Face Front, Face 3/4),
    stitches them into a single high-resolution 4-panel or 6-panel Character Sheet image,
    and saves the character into `character_library/<character_name>/` so it can be loaded
    anytime in `H3CharacterReferenceHub` or the NLE Studio Modal!
    """

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "images": ("IMAGE",),
                "character_name": ("STRING", {"default": "Char1", "multiline": False}),
                "sheet_preset": (
                    [
                        "6-Panel 360° Turnaround + Face Closeups (124 frames)",
                        "4-Panel 180° Fast Turnaround + Face (73 frames)",
                        "6-Panel Facial Expressions Sheet (124 frames)",
                        "6-Panel Anime/2D to Photorealistic Live-Action (124 frames)",
                        "4-Panel Anime/2D to Photorealistic Live-Action (73 frames)",
                    ],
                    {"default": "6-Panel 360° Turnaround + Face Closeups (124 frames)"},
                ),
                "visual_traits_summary": (
                    "STRING",
                    {
                        "default": "character with consistent face, hair, and full turnaround outfit from character sheet",
                        "multiline": False,
                    },
                ),
                "speaker_id": ("STRING", {"default": "S1", "multiline": False}),
                "voice_desc": ("STRING", {"default": "clear natural conversational voice", "multiline": False}),
                "border_px": ("INT", {"default": 6, "min": 0, "max": 32, "step": 2}),
                "auto_save_to_library": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("character_sheet_grid", "extracted_panel_frames", "saved_character_id", "library_path")
    FUNCTION = "stitch_and_save"
    CATEGORY = "MiniMax-H3 Studio/Character Maker (Turnaround Sheet)"
    OUTPUT_NODE = True

    def stitch_and_save(
        self,
        images: Any,
        character_name: str = "Char1",
        sheet_preset: str = "6-Panel 360° Turnaround + Face Closeups (124 frames)",
        visual_traits_summary: str = "",
        speaker_id: str = "S1",
        voice_desc: str = "clear natural conversational voice",
        border_px: int = 6,
        auto_save_to_library: bool = True,
    ) -> Dict[str, Any]:
        grid_tensor, picked_indices = stitch_character_sheet_grid(
            images=images,
            sheet_preset=sheet_preset,
            border_px=border_px,
        )

        if torch is not None and isinstance(images, torch.Tensor) and picked_indices:
            panel_batch = torch.stack([images[i] for i in picked_indices], dim=0)
        else:
            panel_batch = grid_tensor

        char_id = _slugify_char_name(character_name)
        char_folder = os.path.join(CHARACTER_LIBRARY_DIR, char_id)
        sheet_file_path = os.path.join(char_folder, "sheet.png")

        if auto_save_to_library:
            os.makedirs(char_folder, exist_ok=True)
            pil_sheet = tensor_to_pil(grid_tensor, index=0)
            if pil_sheet is not None:
                pil_sheet.save(sheet_file_path, format="PNG")
            # Also save individual extracted angle panels
            for idx_num, f_idx in enumerate(picked_indices):
                pil_p = tensor_to_pil(images, index=f_idx)
                if pil_p is not None:
                    pil_p.save(os.path.join(char_folder, f"panel_{idx_num + 1}_f{f_idx}.png"), format="PNG")

            meta = {
                "character_id": char_id,
                "name": character_name.strip() or char_id,
                "sheet_preset": sheet_preset,
                "visual_traits": visual_traits_summary.strip() or f"{character_name} character turnaround sheet",
                "speaker_id": speaker_id.strip() or "S1",
                "voice_desc": voice_desc.strip() or "natural clear voice",
                "picked_frames": picked_indices,
                "sheet_path": sheet_file_path,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(os.path.join(char_folder, "metadata.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
            print(f"[H3-Studio] Saved Character Sheet '{char_id}' to {sheet_file_path}")

        preview_b64 = tensor_to_base64_jpeg(grid_tensor, index=0, max_side=768)
        payload_item = {
            "character_id": char_id,
            "name": character_name,
            "picked_frames": picked_indices,
            "sheet_b64": preview_b64,
            "library_path": sheet_file_path,
            "status": f"Saved '{character_name}' ({char_id}) to Character Library ({len(picked_indices)} panels)",
        }
        return {
            "ui": {
                "h3_charsheet_preview": [payload_item],
                "h3_saved_character": [payload_item],
            },
            "result": (grid_tensor, panel_batch, char_id, sheet_file_path),
        }
