from .extender_node import H3InteractiveVideoExtender
from .model_lora_node import H3ModelSpeedAndLoraHub
from .character_hub_node import H3CharacterReferenceHub
from .prompt_composer_node import H3AIPromptComposer
from .character_maker_node import H3CharacterSheetPromptNode, H3CharacterSheetStitcherAndSaver

NODE_CLASS_MAPPINGS = {
    "H3InteractiveVideoExtender": H3InteractiveVideoExtender,
    "H3ModelSpeedAndLoraHub": H3ModelSpeedAndLoraHub,
    "H3CharacterReferenceHub": H3CharacterReferenceHub,
    "H3AIPromptComposer": H3AIPromptComposer,
    "H3CharacterSheetPromptNode": H3CharacterSheetPromptNode,
    "H3CharacterSheetStitcherAndSaver": H3CharacterSheetStitcherAndSaver,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3InteractiveVideoExtender": "H3 Interactive Video & Audio Extender (Timeline)",
    "H3ModelSpeedAndLoraHub": "H3 Model Speed & Unlimited LoRA Hub",
    "H3CharacterReferenceHub": "H3 Character & Multi-Reference Hub (On/Off)",
    "H3AIPromptComposer": "H3 AI Prompt Composer (Ollama smixapp.com + <d>)",
    "H3CharacterSheetPromptNode": "H3 Character Maker (A+B Turnaround Sheet Prompt)",
    "H3CharacterSheetStitcherAndSaver": "H3 Character Sheet Stitcher & Library Saver",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
