import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

// ============================================================================
// Inject Precision Broadcast NLE Stylesheet
// ============================================================================
(function injectH3Styles() {
  const id = "comfyui-h3-studio-styles";
  if (document.getElementById(id)) return;
  const link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.type = "text/css";
  link.href = new URL("../css/h3_studio.css", import.meta.url).href;
  document.head.appendChild(link);
})();

function findWidget(node, name) {
  return (node.widgets || []).find((w) => w.name === name);
}

function hideBackingWidget(node, name) {
  const w = findWidget(node, name);
  if (w) {
    w.type = "hidden";
    w.computeSize = () => [0, -4];
  }
  return w;
}

function formatSMPTETimecode(frameIdx, fps = 24) {
  const f = Math.max(0, Math.floor(frameIdx));
  const fpsInt = Math.max(1, Math.round(fps));
  const totalSec = Math.floor(f / fpsInt);
  const remFrames = f % fpsInt;
  const mins = Math.floor(totalSec / 60);
  const secs = totalSec % 60;
  return `00:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}:${String(remFrames).padStart(2, "0")}`;
}

function findGraphNodeByType(typeName) {
  if (!app.graph || !app.graph._nodes) return null;
  return app.graph._nodes.find((n) => n.type === typeName) || null;
}

async function loadBundledWorkflow(templateName) {
  try {
    const resp = await api.fetchApi(`/h3_studio/workflows/${encodeURIComponent(templateName)}`);
    if (!resp.ok) {
      alert(`Failed to load workflow template: ${templateName}`);
      return;
    }
    const wfJson = await resp.json();
    await app.loadGraphData(wfJson, true, true, templateName);
  } catch (err) {
    console.error("[H3 Studio] Failed loading workflow:", err);
  }
}

// ============================================================================
// Global NLE Studio Workspace Modal & Topbar Launcher
// ============================================================================
let nleStudioInstance = null;

function createNLEStudioWorkspace() {
  if (nleStudioInstance) return nleStudioInstance;

  // 1. Floating Topbar Button
  const launcher = document.createElement("button");
  launcher.type = "button";
  launcher.className = "h3-floating-launcher";
  launcher.title = "Open H3 Studio NLE Video Extender & Multi-Modal Deck (Alt+H)";
  launcher.innerHTML = `
    <span class="h3-floating-launcher-dot"></span>
    <span>H3 STUDIO NLE</span>
    <span class="h3-floating-launcher-shortcut">Alt+H</span>
  `;
  document.body.appendChild(launcher);

  // 2. Full NLE Studio Modal Backdrop
  const backdrop = document.createElement("div");
  backdrop.className = "h3-nle-backdrop";
  backdrop.innerHTML = `
    <div class="h3-nle-shell" role="dialog" aria-label="H3 Studio NLE Video Extender">
      <!-- Top Header Bar -->
      <header class="h3-nle-topbar">
        <div class="h3-nle-brand">
          <span class="h3-nle-brand-mark">H3 NLE</span>
          <span class="h3-nle-brand-title">MINIMAX-H3 MULTI-MODAL VIDEO EXTENDER &amp; SCRIPT DECK</span>
          <span class="h3-badge" data-nle="sync-badge">Canvas Linked</span>
        </div>
        <div class="h3-nle-topbar-actions">
          <button type="button" class="h3-btn" data-nle="load-i2v">Load I2VA Workflow</button>
          <button type="button" class="h3-btn" data-nle="load-ref2v">Load Ref2VA Multi-Char</button>
          <button type="button" class="h3-btn h3-btn-accent" data-nle="load-charmaker" title="Open H3 360° Character Sheet Maker Workflow (from Real Face Photo)">Load Character Maker</button>
          <button type="button" class="h3-btn h3-btn-primary" data-nle="queue-now">Queue Generation in ComfyUI</button>
          <button type="button" class="h3-btn h3-btn-danger" data-nle="close-modal">Close [Esc]</button>
        </div>
      </header>

      <!-- 3-Column NLE Workbench -->
      <div class="h3-nle-workbench">
        <!-- LEFT PANE: Character Casting & Unlimited LoRA Rack -->
        <section class="h3-nle-pane">
          <div class="h3-nle-pane-header">
            <span class="h3-nle-pane-title">1. Character Casting &amp; LoRA Rack</span>
            <label class="h3-label" style="display:flex; align-items:center; gap:5px; cursor:pointer;">
              <input type="checkbox" class="h3-toggle" data-nle="master-char-toggle" checked />
              <span>Ref2VA Mode</span>
            </label>
          </div>
          <div class="h3-nle-pane-body">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span class="h3-label">CHARACTER ROSTER (&lt;Subject 1..N&gt;)</span>
              <div style="display:flex; gap:5px; align-items:center;">
                <span class="h3-badge h3-badge-green" data-nle="char-active-count">1 Active</span>
                <button type="button" class="h3-btn h3-btn-primary" data-nle="add-character" title="Add New Character to Story Roster">+ Add Char</button>
              </div>
            </div>
            <div class="h3-list-container" data-nle="char-cards" style="max-height:290px;"></div>

            <div style="border-top:1px solid var(--h3-border-hairline); padding-top:10px; display:flex; justify-content:space-between; align-items:center;">
              <span class="h3-label">UNLIMITED DYNAMIC LoRA STACK</span>
              <button type="button" class="h3-btn h3-btn-primary" data-nle="add-lora">+ Add LoRA</button>
            </div>
            <div class="h3-item-row">
              <span class="h3-label">Fast Attention:</span>
              <select class="h3-select" data-nle="attn-select" style="flex:1;">
                <option value="auto (SageAttn -> FlashAttn2 -> SDPA)">auto (SageAttn -&gt; FlashAttn2 -&gt; SDPA)</option>
                <option value="sage_attention">sage_attention</option>
                <option value="flash_attention_2">flash_attention_2</option>
                <option value="xformers">xformers</option>
                <option value="pytorch_sdpa">pytorch_sdpa</option>
                <option value="comfy_default (no_override)">comfy_default (no_override)</option>
              </select>
            </div>
            <div class="h3-list-container" data-nle="lora-cards" style="max-height:220px;"></div>
          </div>
        </section>

        <!-- CENTER PANE: Cinema Program Monitor & Multi-Track Timeline -->
        <section class="h3-nle-pane">
          <div class="h3-nle-pane-header">
            <span class="h3-nle-pane-title">2. Program Monitor &amp; Seamless Seam Editor</span>
            <div style="display:flex; gap:6px;">
              <span class="h3-badge" data-nle="seg-pill">0 Segments</span>
              <span class="h3-badge h3-badge-amber" data-nle="total-dur-pill">0f (0.00s)</span>
            </div>
          </div>
          <div class="h3-nle-pane-body">
            <figure class="h3-monitor-stage" style="margin:0;">
              <div class="h3-viewport-empty" data-nle="monitor-empty">
                No video segments in timeline yet.<br/>
                Run a generation or load a workflow to scrub frames, trim end-of-clip degradation, and lock your First-Frame Reference (&lt;Picture 1&gt;).
              </div>
              <img data-nle="monitor-img" style="display:none;" alt="Program Monitor Frame" />
              <div class="h3-monitor-hud-top">
                <span class="h3-badge" data-nle="hud-mode">24.00 FPS | STEREO 32kHz</span>
                <span class="h3-badge h3-badge-green" data-nle="hud-ref-lock">First-Frame Anchor Ready</span>
              </div>
              <div class="h3-monitor-hud-bottom">
                <span class="h3-smpte-readout" data-nle="smpte-tc">00:00:00:00</span>
                <span class="h3-smpte-readout" data-nle="frame-counter">FRM 0000 / 0000</span>
              </div>
            </figure>

            <!-- Transport Deck -->
            <div class="h3-transport-deck">
              <div class="h3-scrubber-track-row">
                <span class="h3-label" style="font-family:var(--h3-font-mono);">IN</span>
                <input type="range" class="h3-timeline-ruler-slider" data-nle="scrubber" min="0" max="0" value="0" />
                <span class="h3-label" style="font-family:var(--h3-font-mono);">OUT</span>
              </div>
              <div class="h3-transport-controls">
                <div style="display:flex; gap:4px;">
                  <button type="button" class="h3-btn" data-nle="jump-start" title="Jump to Start">|&lt;</button>
                  <button type="button" class="h3-btn" data-nle="step-prev" title="Step Back 1 Frame">-1f</button>
                  <button type="button" class="h3-btn h3-btn-accent" data-nle="play-toggle" style="min-width:64px;">Play</button>
                  <button type="button" class="h3-btn" data-nle="step-next" title="Step Forward 1 Frame">+1f</button>
                  <button type="button" class="h3-btn" data-nle="jump-end" title="Jump to Last Frame">&gt;|</button>
                </div>
                <div style="display:flex; gap:5px;">
                  <button type="button" class="h3-btn h3-btn-primary" data-nle="lock-extend">
                    Lock Playhead as First-Frame Ref &amp; Trim Out
                  </button>
                  <button type="button" class="h3-btn" data-nle="undo-seg" title="Drop Last Segment (Re-roll)">
                    Undo Last Clip
                  </button>
                  <button type="button" class="h3-btn h3-btn-danger" data-nle="clear-timeline" title="Reset All Segments">
                    Clear
                  </button>
                </div>
              </div>
            </div>

            <!-- Multi-Track NLE Timeline (V1 Video + A1 Stereo Audio) -->
            <div class="h3-multitrack-bay">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="h3-label">MULTI-SEGMENT TIMELINE (CLICK ANY SEGMENT TO INSPECT SEAM)</span>
                <span class="h3-label" style="font-family:var(--h3-font-mono);">Auto-Skip Seam Frame 0: ON | Audio Crossfade: 40ms</span>
              </div>
              <div class="h3-track-lane">
                <div class="h3-track-header v1">
                  <span>V1</span>
                  <span style="font-size:8px; color:var(--h3-amber);">VIDEO</span>
                </div>
                <div class="h3-track-clips" data-nle="v1-track">
                  <span class="h3-label" style="padding:6px;">No video clips loaded</span>
                </div>
              </div>
              <div class="h3-track-lane">
                <div class="h3-track-header a1">
                  <span>A1</span>
                  <span style="font-size:8px; color:var(--h3-teal);">32kHz</span>
                </div>
                <div class="h3-track-clips" data-nle="a1-track">
                  <span class="h3-label" style="padding:6px;">No stereo audio clips loaded</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- RIGHT PANE: AI Director (Single-Shot Deck + Autonomous Multi-Segment Episode Storyboarder) -->
        <section class="h3-nle-pane">
          <div class="h3-nle-pane-header">
            <div style="display:flex; gap:4px; align-items:center;">
              <button type="button" class="h3-btn h3-btn-primary" data-nle="tab-single" style="padding:3px 8px; font-size:10px;">
                Single Segment Deck
              </button>
              <button type="button" class="h3-btn" data-nle="tab-episode" style="padding:3px 8px; font-size:10px;">
                Episode Storyboard (Auto-10m)
              </button>
            </div>
            <span class="h3-badge h3-badge-amber" data-nle="frame-calc-badge">124f (5.17s)</span>
          </div>
          <div class="h3-nle-pane-body">
            <div class="h3-item-row">
              <span class="h3-label" style="width:68px;">Ollama URL:</span>
              <input type="text" class="h3-input" data-nle="ollama-url" value="https://ollama.smixapp.com" style="flex:1;" />
              <button type="button" class="h3-btn" data-nle="refresh-models">Sync</button>
            </div>
            <div class="h3-item-row">
              <span class="h3-label" style="width:68px;">AI Model:</span>
              <select class="h3-select" data-nle="ollama-model" style="flex:1;">
                <option value="minimax-m3:cloud">minimax-m3:cloud [Vision]</option>
                <option value="qwen3.6:27b">qwen3.6:27b [Vision]</option>
                <option value="huihui_ai/Qwen3.8-abliterated:latest">huihui_ai/Qwen3.8-abliterated:latest [Vision]</option>
                <option value="deepseek-v4-flash:cloud">deepseek-v4-flash:cloud</option>
                <option value="glm-5.2:cloud">glm-5.2:cloud</option>
              </select>
            </div>

            <!-- VIEW A: SINGLE SEGMENT DECK -->
            <div data-nle="view-single" style="display:flex; flex-direction:column; gap:10px; flex:1;">
              <div class="h3-item-row">
                <span class="h3-label">Mode:</span>
                <select class="h3-select" data-nle="h3-mode" style="flex:1;">
                  <option value="Auto (Ref2VA if Characters ON, I2VA if First-Frame, else T2VA)">Auto (Ref2VA / I2VA / T2VA)</option>
                  <option value="I2VA (First-Frame / Video Extend)">I2VA (First-Frame Extend)</option>
                  <option value="Ref2VA (Full Multi-Character Reference)">Ref2VA (Full Multi-Character)</option>
                  <option value="T2VA (Text to Video+Audio)">T2VA (Text to Video+Audio)</option>
                  <option value="FL2VA (First & Last Frame)">FL2VA (First &amp; Last Frame)</option>
                  <option value="L2VA (Last Frame Landing)">L2VA (Last Frame Landing)</option>
                </select>
                <span class="h3-label">Dur (s):</span>
                <input type="number" class="h3-input" data-nle="duration-sec" min="2" max="15" step="0.5" value="5.0" style="width:54px;" />
              </div>

              <div>
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                  <span class="h3-label">SCENE ACTION &amp; CAMERA DIRECTION (INDONESIAN / ENGLISH)</span>
                </div>
                <textarea class="h3-textarea" data-nle="user-idea" placeholder="Tulis adegan lanjutan di sini (misal: Char1 menoleh ke arah pintu kafe saat Char2 masuk membawa payung basah)..."></textarea>
              </div>

              <div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                  <span class="h3-label">SYNCHRONIZED DIALOGUE LINES (&lt;d&gt;[Language] ...&lt;/d&gt;)</span>
                  <button type="button" class="h3-btn h3-btn-primary" data-nle="add-dialogue">+ Add &lt;d&gt; Line</button>
                </div>
                <div class="h3-list-container" data-nle="dialogue-list" style="max-height:145px;"></div>
              </div>

              <div style="display:flex; gap:6px;">
                <button type="button" class="h3-btn h3-btn-accent" data-nle="generate-prompt" style="flex:1; padding:8px;">
                  Compile H3 Prompt via Ollama
                </button>
                <button type="button" class="h3-btn h3-btn-primary" data-nle="auto-continue-prompt" style="flex:1; padding:8px;" title="Lock current frame, read previous segment prompt &amp; frame, and let AI write the next seamless segment!">
                  AI Auto-Continue Next Seg
                </button>
              </div>

              <div style="flex:1; display:flex; flex-direction:column; min-height:100px;">
                <span class="h3-label" style="margin-bottom:4px;">COMPILED H3 PROMPT OUTPUT (EDITABLE)</span>
                <textarea class="h3-textarea" data-nle="compiled-prompt" style="flex:1; min-height:100px;" placeholder="Hasil prompt H3 (subject_definitions / integrated_multimodal_description, overall_soundscape, non_diegetic_music) akan tampil di sini..."></textarea>
              </div>
            </div>

            <!-- VIEW B: EPISODE STORYBOARD DIRECTOR (MULTI-SEGMENT AUTO-PLANNER & AUTOPILOT) -->
            <div data-nle="view-episode" style="display:none; flex-direction:column; gap:10px; flex:1;">
              <div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                  <span class="h3-label">LONG STORY / EPISODE SYNOPSIS (MULTI-CHARACTER)</span>
                  <span class="h3-badge" data-nle="sb-plan-summary">0 Segs Planned</span>
                </div>
                <textarea class="h3-textarea" data-nle="sb-synopsis" style="min-height:76px;" placeholder="Tulis alur cerita panjang di sini (bisa melibatkan Char1, Char2, Char3, Char4, dst. AI akan membagi menjadi segmen-segmen 5–15 detik lengkap dengan dialog <d> dan pergantian karakter otomatis)..."></textarea>
              </div>

              <div class="h3-item-row">
                <span class="h3-label">Target Dur:</span>
                <select class="h3-select" data-nle="sb-total-dur" style="width:92px;">
                  <option value="30">30 Sec</option>
                  <option value="60" selected>1 Min (60s)</option>
                  <option value="180">3 Min (180s)</option>
                  <option value="300">5 Min (300s)</option>
                  <option value="600">10 Min (600s)</option>
                </select>
                <span class="h3-label">Pacing:</span>
                <select class="h3-select" data-nle="sb-pacing" style="flex:1;">
                  <option value="auto_adaptive" selected>Auto-Adaptive (5s–15s by &lt;d&gt; length)</option>
                  <option value="fast_5s">Fast Cuts (~5.17s / 124f)</option>
                  <option value="standard_8s">Standard (~8.0s / 192f)</option>
                  <option value="extended_12s">Extended (~12.0s / 294f)</option>
                  <option value="max_15s">Max H3 Clip (15.08s / 362f)</option>
                </select>
              </div>

              <div style="display:flex; gap:6px;">
                <button type="button" class="h3-btn h3-btn-accent" data-nle="sb-plan-btn" style="flex:1; padding:7px;">
                  AI Generate Multi-Segment Storyboard &amp; &lt;d&gt;
                </button>
                <button type="button" class="h3-btn" data-nle="sb-add-seg" title="Add Blank Segment Manually">+ Seg</button>
              </div>

              <div class="h3-list-container" data-nle="sb-segment-list" style="flex:1; max-height:260px; min-height:160px;">
                <div class="h3-label" style="padding:12px; text-align:center;">
                  Belum ada daftar segmen.<br/>Tulis sinopsis cerita di atas lalu klik <b>AI Generate Multi-Segment Storyboard</b>.
                </div>
              </div>

              <div style="display:flex; gap:5px; flex-wrap:wrap; border-top:1px solid var(--h3-border-hairline); padding-top:8px;">
                <button type="button" class="h3-btn" data-nle="sb-run-next" style="flex:1;">
                  Run Next Pending Seg
                </button>
                <button type="button" class="h3-btn h3-btn-primary" data-nle="sb-autopilot-btn" style="flex:1;">
                  Auto-Produce All (Autopilot)
                </button>
              </div>
            </div>

            <div class="h3-status-bar">
              <span data-nle="status-msg">Ready — Connected to Canvas Nodes</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  `;
  document.body.appendChild(backdrop);

  // State & DOM Refs inside NLE Modal
  const elCharCards = backdrop.querySelector('[data-nle="char-cards"]');
  const elCharCount = backdrop.querySelector('[data-nle="char-active-count"]');
  const elMasterCharToggle = backdrop.querySelector('[data-nle="master-char-toggle"]');
  const elLoraCards = backdrop.querySelector('[data-nle="lora-cards"]');
  const elAttnSelect = backdrop.querySelector('[data-nle="attn-select"]');

  const elMonitorImg = backdrop.querySelector('[data-nle="monitor-img"]');
  const elMonitorEmpty = backdrop.querySelector('[data-nle="monitor-empty"]');
  const elSmpteTc = backdrop.querySelector('[data-nle="smpte-tc"]');
  const elFrameCounter = backdrop.querySelector('[data-nle="frame-counter"]');
  const elScrubber = backdrop.querySelector('[data-nle="scrubber"]');
  const elV1Track = backdrop.querySelector('[data-nle="v1-track"]');
  const elA1Track = backdrop.querySelector('[data-nle="a1-track"]');
  const elSegPill = backdrop.querySelector('[data-nle="seg-pill"]');
  const elTotalDurPill = backdrop.querySelector('[data-nle="total-dur-pill"]');
  const btnPlay = backdrop.querySelector('[data-nle="play-toggle"]');

  const elOllamaUrl = backdrop.querySelector('[data-nle="ollama-url"]');
  const elOllamaModel = backdrop.querySelector('[data-nle="ollama-model"]');
  const elH3Mode = backdrop.querySelector('[data-nle="h3-mode"]');
  const elDurationSec = backdrop.querySelector('[data-nle="duration-sec"]');
  const elFrameCalcBadge = backdrop.querySelector('[data-nle="frame-calc-badge"]');
  const elUserIdea = backdrop.querySelector('[data-nle="user-idea"]');
  const elDialogueList = backdrop.querySelector('[data-nle="dialogue-list"]');
  const elCompiledPrompt = backdrop.querySelector('[data-nle="compiled-prompt"]');
  const elStatusMsg = backdrop.querySelector('[data-nle="status-msg"]');

  let nleState = {
    fps: 24,
    totalFrames: 0,
    currentFrame: 0,
    revision: 1,
    nodeId: "latest",
    segments: [],
    playing: false,
    playRaf: null,
    audioEl: new Audio(),
    availableLoras: ["None"],
  };
  nleState.audioEl.preload = "auto";

  function pullFromCanvasNodes() {
    // 1. Sync from H3CharacterReferenceHub
    const charNode = findGraphNodeByType("H3CharacterReferenceHub");
    if (charNode) {
      const wUse = findWidget(charNode, "use_character_refs");
      if (wUse) elMasterCharToggle.checked = Boolean(wUse.value);
      if (charNode._h3RenderNLEChars) charNode._h3RenderNLEChars(elCharCards, elCharCount);
    }

    // 2. Sync from H3ModelSpeedAndLoraHub
    const loraNode = findGraphNodeByType("H3ModelSpeedAndLoraHub");
    if (loraNode) {
      const wAttn = findWidget(loraNode, "attention_backend");
      if (wAttn) elAttnSelect.value = wAttn.value;
      if (loraNode._h3RenderNLELoras) loraNode._h3RenderNLELoras(elLoraCards);
    }

    // 3. Sync from H3AIPromptComposer
    const promptNode = findGraphNodeByType("H3AIPromptComposer");
    if (promptNode) {
      const wIdea = findWidget(promptNode, "user_idea");
      const wMode = findWidget(promptNode, "mode");
      const wDur = findWidget(promptNode, "duration_seconds");
      const wUrl = findWidget(promptNode, "ollama_url");
      const wMod = findWidget(promptNode, "ollama_model");
      const wGen = findWidget(promptNode, "generated_h3_prompt");
      if (wIdea) elUserIdea.value = wIdea.value || "";
      if (wMode) elH3Mode.value = wMode.value;
      if (wDur) elDurationSec.value = wDur.value;
      if (wUrl) elOllamaUrl.value = wUrl.value;
      if (wMod && wMod.value) elOllamaModel.value = wMod.value;
      if (wGen) elCompiledPrompt.value = wGen.value || "";
      if (promptNode._h3RenderNLEDialogues) promptNode._h3RenderNLEDialogues(elDialogueList);
    }

    updateCalcBadge();
    refreshExtenderTimelineFromServer();
  }

  function pushToCanvasPromptNode() {
    const promptNode = findGraphNodeByType("H3AIPromptComposer");
    if (!promptNode) return;
    const wIdea = findWidget(promptNode, "user_idea");
    const wMode = findWidget(promptNode, "mode");
    const wDur = findWidget(promptNode, "duration_seconds");
    const wUrl = findWidget(promptNode, "ollama_url");
    const wMod = findWidget(promptNode, "ollama_model");
    const wGen = findWidget(promptNode, "generated_h3_prompt");
    if (wIdea) wIdea.value = elUserIdea.value;
    if (wMode) wMode.value = elH3Mode.value;
    if (wDur) wDur.value = parseFloat(elDurationSec.value) || 5.0;
    if (wUrl) wUrl.value = elOllamaUrl.value;
    if (wMod) wMod.value = elOllamaModel.value;
    if (wGen) wGen.value = elCompiledPrompt.value;
  }

  function updateCalcBadge() {
    const sec = parseFloat(elDurationSec.value) || 5.0;
    const raw = Math.max(5, Math.round(sec * 24));
    const len = raw + ((5 - (raw % 17)) % 17);
    const eff = (len / 24).toFixed(2);
    elFrameCalcBadge.textContent = `${len}f (${eff}s @ 17k+5)`;
  }

  async function refreshExtenderTimelineFromServer() {
    const extNode = findGraphNodeByType("H3InteractiveVideoExtender");
    const nodeId = extNode ? String(extNode.id) : "latest";
    try {
      const resp = await api.fetchApi(`/h3_studio/extender/state/${encodeURIComponent(nodeId)}`);
      if (resp.ok) {
        const summary = await resp.json();
        renderNLETimeline(summary, nodeId);
      }
    } catch (e) {}
  }

  function buildFrameUrl(nodeId, frameIdx, rev) {
    return api.apiURL(`/h3_studio/extender/frame/${encodeURIComponent(nodeId)}/${frameIdx}?rev=${encodeURIComponent(rev || 1)}`);
  }

  function buildAudioUrl(nodeId, rev) {
    return api.apiURL(`/h3_studio/extender/audio/${encodeURIComponent(nodeId)}?rev=${encodeURIComponent(rev || 1)}`);
  }

  function loadNLEFrame(frameIdx, nodeIdOverride, onDone) {
    if (nleState.totalFrames <= 0) return;
    const extNode = findGraphNodeByType("H3InteractiveVideoExtender");
    const nodeId = nodeIdOverride || nleState.nodeId || (extNode ? String(extNode.id) : "latest");
    const clamped = Math.max(0, Math.min(frameIdx, nleState.totalFrames - 1));
    nleState.currentFrame = clamped;
    elScrubber.value = String(clamped);
    elSmpteTc.textContent = formatSMPTETimecode(clamped, nleState.fps);
    elFrameCounter.textContent = `FRM ${String(clamped).padStart(4, "0")} / ${String(nleState.totalFrames - 1).padStart(4, "0")}`;

    if (extNode) {
      const wSel = findWidget(extNode, "selected_global_frame");
      if (wSel) wSel.value = clamped;
    }

    const nextSrc = buildFrameUrl(nodeId, clamped, nleState.revision);
    if (typeof onDone === "function") {
      const pre = new Image();
      pre.onload = () => {
        elMonitorImg.src = nextSrc;
        elMonitorImg.style.display = "block";
        elMonitorEmpty.style.display = "none";
        onDone();
      };
      pre.onerror = () => onDone();
      pre.src = nextSrc;
    } else {
      elMonitorImg.src = nextSrc;
      elMonitorImg.style.display = "block";
      elMonitorEmpty.style.display = "none";
    }
  }

  function stopNLEPlayback() {
    nleState.playing = false;
    if (nleState.playRaf) {
      clearTimeout(nleState.playRaf);
      nleState.playRaf = null;
    }
    try {
      nleState.audioEl.pause();
    } catch (e) {}
    btnPlay.textContent = "Play";
  }

  function renderNLETimeline(summary, nodeId) {
    if (!summary) return;
    stopNLEPlayback();
    nleState.fps = summary.fps || 24;
    nleState.totalFrames = summary.total_active_frames || 0;
    nleState.revision = summary.revision || 1;
    nleState.nodeId = summary.node_id || nodeId || "latest";
    nleState.segments = summary.segments || [];

    // Preload stitched stereo audio if available
    if (nleState.totalFrames > 0) {
      nleState.audioEl.src = buildAudioUrl(nleState.nodeId, nleState.revision);
    }

    elSegPill.textContent = `${nleState.segments.length} Segments`;
    elTotalDurPill.textContent = `${nleState.totalFrames}f (${(summary.total_duration_sec || 0).toFixed(2)}s)`;
    elScrubber.max = String(Math.max(0, nleState.totalFrames - 1));

    if (nleState.totalFrames > 0) {
      const target =
        typeof summary.playhead_global_frame === "number"
          ? summary.playhead_global_frame
          : nleState.totalFrames - 1;
      loadNLEFrame(target, nodeId);
    } else {
      elMonitorImg.style.display = "none";
      elMonitorEmpty.style.display = "block";
      elSmpteTc.textContent = "00:00:00:00";
      elFrameCounter.textContent = "FRM 0000 / 0000";
    }

    elV1Track.innerHTML = "";
    elA1Track.innerHTML = "";

    if (nleState.segments.length === 0) {
      elV1Track.innerHTML = `<span class="h3-label" style="padding:6px;">No video clips in timeline</span>`;
      elA1Track.innerHTML = `<span class="h3-label" style="padding:6px;">No stereo audio clips in timeline</span>`;
      return;
    }

    let running = 0;
    nleState.segments.forEach((seg, idx) => {
      const segEndGlobal = running + seg.active_frames - 1;
      running += seg.active_frames;

      const vBlock = document.createElement("div");
      vBlock.className = "h3-nle-clip-block" + (idx === summary.locked_ref_segment_idx ? " active" : "");
      vBlock.style.flex = `${Math.max(1, seg.active_frames)} 1 0%`;
      vBlock.innerHTML = `
        <div style="display:flex; justify-content:space-between;">
          <b>SEG ${String(idx + 1).padStart(2, "0")}</b>
          <span>${seg.active_frames}f</span>
        </div>
        <div style="color:var(--h3-text-secondary); font-size:9px;">
          In:${seg.trim_start} Out:${seg.trim_end} (${seg.duration_sec}s)
        </div>
      `;
      vBlock.addEventListener("click", () => loadNLEFrame(segEndGlobal, nodeId));
      elV1Track.appendChild(vBlock);

      const aBlock = document.createElement("div");
      aBlock.className = "h3-nle-audio-block";
      aBlock.style.flex = `${Math.max(1, seg.active_frames)} 1 0%`;
      aBlock.innerHTML = `
        <span>A${idx + 1} Stereo 32kHz</span>
        <span>${seg.duration_sec}s</span>
      `;
      aBlock.addEventListener("click", () => loadNLEFrame(segEndGlobal, nodeId));
      elA1Track.appendChild(aBlock);
    });
  }

  async function sendExtenderAction(payload) {
    const extNode = findGraphNodeByType("H3InteractiveVideoExtender");
    const nodeId = extNode ? String(extNode.id) : "latest";
    try {
      const resp = await api.fetchApi("/h3_studio/extender/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: nodeId, ...payload }),
      });
      if (resp.ok) {
        const summary = await resp.json();
        renderNLETimeline(summary, nodeId);
        if (extNode && extNode._h3RenderSummary) {
          extNode._h3RenderSummary(summary);
        }
      }
    } catch (e) {}
  }

  // Event Listeners inside NLE Modal
  launcher.addEventListener("click", () => {
    backdrop.classList.add("open");
    pullFromCanvasNodes();
  });

  backdrop.querySelector('[data-nle="close-modal"]').addEventListener("click", () => {
    backdrop.classList.remove("open");
  });

  window.addEventListener("keydown", (e) => {
    if (e.altKey && e.key.toLowerCase() === "h") {
      e.preventDefault();
      if (backdrop.classList.contains("open")) {
        backdrop.classList.remove("open");
      } else {
        backdrop.classList.add("open");
        pullFromCanvasNodes();
      }
    } else if (e.key === "Escape" && backdrop.classList.contains("open")) {
      backdrop.classList.remove("open");
    }
  });

  backdrop.querySelector('[data-nle="load-i2v"]').addEventListener("click", async () => {
    await loadBundledWorkflow("H3_I2VA_Interactive_Extender.json");
    setTimeout(pullFromCanvasNodes, 250);
  });

  backdrop.querySelector('[data-nle="load-ref2v"]').addEventListener("click", async () => {
    await loadBundledWorkflow("H3_Ref2VA_MultiCharacter_Studio.json");
    setTimeout(pullFromCanvasNodes, 250);
  });

  backdrop.querySelector('[data-nle="load-charmaker"]').addEventListener("click", async () => {
    await loadBundledWorkflow("H3_Character_Sheet_Maker.json");
    setTimeout(pullFromCanvasNodes, 250);
    elStatusMsg.textContent = "Loaded H3 Character Sheet Maker workflow — upload a real face photo in LoadImage and Queue!";
  });

  backdrop.querySelector('[data-nle="queue-now"]').addEventListener("click", () => {
    pushToCanvasPromptNode();
    app.queuePrompt(0, 1);
    elStatusMsg.textContent = "Queued generation in ComfyUI — segments will auto-append on completion.";
  });

  elMasterCharToggle.addEventListener("change", (e) => {
    const charNode = findGraphNodeByType("H3CharacterReferenceHub");
    if (charNode) {
      const wUse = findWidget(charNode, "use_character_refs");
      if (wUse) wUse.value = e.target.checked;
    }
  });

  elAttnSelect.addEventListener("change", (e) => {
    const loraNode = findGraphNodeByType("H3ModelSpeedAndLoraHub");
    if (loraNode) {
      const wAttn = findWidget(loraNode, "attention_backend");
      if (wAttn) wAttn.value = e.target.value;
    }
  });

  backdrop.querySelector('[data-nle="add-lora"]').addEventListener("click", () => {
    const loraNode = findGraphNodeByType("H3ModelSpeedAndLoraHub");
    if (loraNode && loraNode._h3AddLoraItem) {
      loraNode._h3AddLoraItem();
      loraNode._h3RenderNLELoras(elLoraCards);
    }
  });

  backdrop.querySelector('[data-nle="add-character"]').addEventListener("click", () => {
    const charNode = findGraphNodeByType("H3CharacterReferenceHub");
    if (charNode && charNode._h3AddCharacterSlot) {
      charNode._h3AddCharacterSlot(elCharCards, elCharCount);
    }
  });

  // Tab Switching: Single Segment Deck vs Episode Storyboard (Auto-10m)
  const btnTabSingle = backdrop.querySelector('[data-nle="tab-single"]');
  const btnTabEpisode = backdrop.querySelector('[data-nle="tab-episode"]');
  const viewSingle = backdrop.querySelector('[data-nle="view-single"]');
  const viewEpisode = backdrop.querySelector('[data-nle="view-episode"]');

  btnTabSingle.addEventListener("click", () => {
    btnTabSingle.classList.add("h3-btn-primary");
    btnTabEpisode.classList.remove("h3-btn-primary");
    viewSingle.style.display = "flex";
    viewEpisode.style.display = "none";
  });

  btnTabEpisode.addEventListener("click", () => {
    btnTabEpisode.classList.add("h3-btn-primary");
    btnTabSingle.classList.remove("h3-btn-primary");
    viewSingle.style.display = "none";
    viewEpisode.style.display = "flex";
    renderStoryboardQueue();
  });

  // Episode Storyboard State & Autopilot Engine
  const elSbSynopsis = backdrop.querySelector('[data-nle="sb-synopsis"]');
  const elSbTotalDur = backdrop.querySelector('[data-nle="sb-total-dur"]');
  const elSbPacing = backdrop.querySelector('[data-nle="sb-pacing"]');
  const elSbPlanBtn = backdrop.querySelector('[data-nle="sb-plan-btn"]');
  const elSbAddSegBtn = backdrop.querySelector('[data-nle="sb-add-seg"]');
  const elSbSegList = backdrop.querySelector('[data-nle="sb-segment-list"]');
  const elSbPlanSummary = backdrop.querySelector('[data-nle="sb-plan-summary"]');
  const elSbRunNextBtn = backdrop.querySelector('[data-nle="sb-run-next"]');
  const elSbAutopilotBtn = backdrop.querySelector('[data-nle="sb-autopilot-btn"]');

  let storyboardState = {
    segments: [],
    autopilotActive: false,
    activeRunningIdx: -1,
  };

  function getFullCharactersRoster() {
    const charNode = findGraphNodeByType("H3CharacterReferenceHub");
    if (charNode && charNode._h3GetCharConfigs) {
      return charNode._h3GetCharConfigs();
    }
    return [
      { slot: 1, enabled: true, name: "Char1", speaker_id: "S1", visual_traits: "lead character", voice_desc: "clear voice" },
      { slot: 2, enabled: false, name: "Char2", speaker_id: "S2", visual_traits: "second character", voice_desc: "warm voice" },
    ];
  }

  function renderStoryboardQueue() {
    const segs = storyboardState.segments || [];
    const totalSec = segs.reduce((acc, s) => acc + (parseFloat(s.duration_seconds) || 0), 0);
    elSbPlanSummary.textContent = `${segs.length} Segs (${totalSec.toFixed(1)}s)`;

    if (segs.length === 0) {
      elSbSegList.innerHTML = `
        <div class="h3-label" style="padding:12px; text-align:center;">
          Belum ada daftar segmen.<br/>Tulis sinopsis cerita di atas lalu klik <b>AI Generate Multi-Segment Storyboard</b>.
        </div>
      `;
      return;
    }

    elSbSegList.innerHTML = "";
    segs.forEach((seg, idx) => {
      const card = document.createElement("div");
      card.className = "h3-item-card";
      if (seg.status === "done") {
        card.style.borderColor = "var(--h3-teal)";
      } else if (seg.status === "running") {
        card.style.borderColor = "var(--h3-amber)";
      }

      const statusBadgeClass =
        seg.status === "done" ? "h3-badge-green" : seg.status === "running" ? "h3-badge-amber" : "";
      const slotsStr = (seg.active_character_slots || [1]).join(", ");
      const firstDlg = (seg.dialogue_lines && seg.dialogue_lines[0]) || {
        speaker: "<Subject 1> (S1)",
        language: "Indonesian",
        text: "",
        delivery: "natural conversational tone",
        voiceover: false,
      };

      card.innerHTML = `
        <div class="h3-item-row" style="justify-content:space-between;">
          <div style="display:flex; gap:5px; align-items:center;">
            <b>SEG #${idx + 1}</b>
            <span class="h3-badge ${statusBadgeClass}">${(seg.status || "pending").toUpperCase()}</span>
            <select class="h3-select" data-sb="transition" style="font-size:10px; padding:2px 5px;">
              <option value="CONTINUE_FRAME" ${seg.transition_type === "CONTINUE_FRAME" ? "selected" : ""}>CONTINUE_FRAME (Extend)</option>
              <option value="NEW_SCENE_CUT" ${seg.transition_type === "NEW_SCENE_CUT" ? "selected" : ""}>NEW_SCENE_CUT (Fresh Cut)</option>
            </select>
          </div>
          <div style="display:flex; gap:4px; align-items:center;">
            <span class="h3-label">Chars:</span>
            <input type="text" class="h3-input" data-sb="slots" value="${slotsStr}" title="Active Character Slot Numbers (e.g. 1, 2, 3)" style="width:42px; font-size:10px;" />
            <input type="number" class="h3-input" data-sb="dur" min="3" max="15" step="0.5" value="${seg.duration_seconds || 8.0}" style="width:46px; font-size:10px;" />
            <button type="button" class="h3-btn" data-sb="toggle-prompt" title="View / Edit Compiled 6-Section H3 Prompt">H3 Prompt</button>
            <button type="button" class="h3-btn h3-btn-primary" data-sb="load-one" title="Load this segment &amp; Queue in ComfyUI">Run</button>
            <button type="button" class="h3-btn h3-btn-danger" data-sb="del" style="padding:3px 6px;">X</button>
          </div>
        </div>
        <div class="h3-item-row">
          <input type="text" class="h3-input" data-sb="action" value="${(seg.visual_action || "").replace(/"/g, "&quot;")}" placeholder="Visual camera &amp; character action..." style="flex:1;" />
        </div>
        <div class="h3-item-row">
          <input type="text" class="h3-input" data-sb="spk" value="${firstDlg.speaker || "<Subject 1> (S1)"}" style="width:95px; font-size:10px;" />
          <input type="text" class="h3-input" data-sb="dlg" value="${(firstDlg.text || "").replace(/"/g, "&quot;")}" placeholder="Spoken <d> dialogue in this segment..." style="flex:1;" />
        </div>
        <div data-sb="prompt-box" style="display:none; flex-direction:column; gap:4px; margin-top:4px;">
          <span class="h3-label">FULL COMPILED 6-SECTION H3 PROMPT FOR SEG #${idx + 1}:</span>
          <textarea class="h3-textarea" data-sb="compiled-prompt" style="min-height:110px; font-size:10px; font-family:var(--h3-font-mono);">${seg.compiled_h3_prompt || ""}</textarea>
        </div>
      `;

      const elPromptBox = card.querySelector('[data-sb="prompt-box"]');
      const elCompiledArea = card.querySelector('[data-sb="compiled-prompt"]');
      card.querySelector('[data-sb="toggle-prompt"]').addEventListener("click", () => {
        elPromptBox.style.display = elPromptBox.style.display === "none" ? "flex" : "none";
      });
      elCompiledArea.addEventListener("input", (e) => {
        seg.compiled_h3_prompt = e.target.value;
      });

      card.querySelector('[data-sb="transition"]').addEventListener("change", (e) => {
        seg.transition_type = e.target.value;
      });
      card.querySelector('[data-sb="slots"]').addEventListener("input", (e) => {
        const parsedSlots = e.target.value
          .split(",")
          .map((x) => parseInt(x.trim(), 10))
          .filter((n) => !isNaN(n) && n > 0);
        seg.active_character_slots = parsedSlots.length > 0 ? parsedSlots : [1];
      });
      card.querySelector('[data-sb="dur"]').addEventListener("input", (e) => {
        seg.duration_seconds = Math.max(3, Math.min(15, parseFloat(e.target.value) || 8.0));
        const totalNow = storyboardState.segments.reduce((acc, s) => acc + (parseFloat(s.duration_seconds) || 0), 0);
        elSbPlanSummary.textContent = `${storyboardState.segments.length} Segs (${totalNow.toFixed(1)}s)`;
      });
      card.querySelector('[data-sb="action"]').addEventListener("input", (e) => {
        seg.visual_action = e.target.value;
      });
      const updateDlg = () => {
        const spkVal = card.querySelector('[data-sb="spk"]').value.trim() || "<Subject 1> (S1)";
        const dlgVal = card.querySelector('[data-sb="dlg"]').value.trim();
        if (dlgVal) {
          seg.dialogue_lines = [
            {
              speaker: spkVal,
              language: firstDlg.language || "Indonesian",
              text: dlgVal,
              delivery: firstDlg.delivery || "natural expressive voice",
              voiceover: Boolean(firstDlg.voiceover),
            },
          ];
        } else {
          seg.dialogue_lines = [];
        }
      };
      card.querySelector('[data-sb="spk"]').addEventListener("input", updateDlg);
      card.querySelector('[data-sb="dlg"]').addEventListener("input", updateDlg);

      card.querySelector('[data-sb="load-one"]').addEventListener("click", () => {
        executeStoryboardSegmentAtIndex(idx);
      });
      card.querySelector('[data-sb="del"]').addEventListener("click", () => {
        storyboardState.segments.splice(idx, 1);
        renderStoryboardQueue();
      });

      elSbSegList.appendChild(card);
    });
  }

  async function executeStoryboardSegmentAtIndex(idx) {
    if (idx < 0 || idx >= storyboardState.segments.length) return;
    const seg = storyboardState.segments[idx];
    seg.status = "running";
    storyboardState.activeRunningIdx = idx;
    renderStoryboardQueue();

    // 1. Auto-toggle active character slots for this segment in H3CharacterReferenceHub
    const charNode = findGraphNodeByType("H3CharacterReferenceHub");
    if (charNode && charNode._h3SetActiveSlots) {
      charNode._h3SetActiveSlots(seg.active_character_slots || [1], elCharCards, elCharCount);
      const wFetchFF = findWidget(charNode, "auto_fetch_extender_first_frame");
      if (wFetchFF) wFetchFF.value = seg.transition_type === "CONTINUE_FRAME";
    }

    // 2. If CONTINUE_FRAME and we have frames in timeline, lock the last good frame
    if (seg.transition_type === "CONTINUE_FRAME" && nleState.totalFrames > 0) {
      const targetLockFrame = Math.max(0, nleState.totalFrames - 1);
      await sendExtenderAction({
        action: "lock_playhead",
        global_frame: targetLockFrame,
        trim_at_playhead: false,
      });
    }

    // 3. Populate H3AIPromptComposer with this segment's action, duration, <d> dialogue, and pre-compiled H3 prompt!
    elUserIdea.value = seg.visual_action || "";
    elDurationSec.value = String(seg.duration_seconds || 8.0);
    updateCalcBadge();

    const promptNode = findGraphNodeByType("H3AIPromptComposer");
    if (promptNode) {
      if (promptNode._h3SetDialogueLines) {
        promptNode._h3SetDialogueLines(seg.dialogue_lines || [], elDialogueList);
      }
      if (seg.compiled_h3_prompt && seg.compiled_h3_prompt.trim()) {
        // Use the pre-generated 6-section H3 prompt for this episode segment immediately!
        elCompiledPrompt.value = seg.compiled_h3_prompt;
        pushToCanvasPromptNode();
      } else {
        pushToCanvasPromptNode();
        elStatusMsg.textContent = `[Storyboard Seg #${idx + 1}/${storyboardState.segments.length}] Compiling H3 prompt via Ollama...`;
        await promptNode._h3TriggerOllamaGenerate((res) => {
          if (res && res.prompt) {
            seg.compiled_h3_prompt = res.prompt;
            elCompiledPrompt.value = res.prompt;
            pushToCanvasPromptNode();
          }
        }, seg.transition_type === "CONTINUE_FRAME" && idx > 0);
      }
    }

    // 4. Queue ComfyUI execution for this segment!
    elStatusMsg.textContent = `[Storyboard Seg #${idx + 1}/${storyboardState.segments.length}] Rendering video + stereo audio in ComfyUI...`;
    app.queuePrompt(0, 1);
  }

  elSbPlanBtn.addEventListener("click", async () => {
    const origText = elSbPlanBtn.textContent;
    elSbPlanBtn.disabled = true;
    elSbPlanBtn.textContent = "Planning Multi-Segment Storyboard via Ollama...";
    elStatusMsg.textContent = "Calling Ollama Director to split story into segments & <d> dialogues...";

    try {
      const resp = await api.fetchApi("/h3_studio/ollama/plan_storyboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          story_synopsis: elSbSynopsis.value || elUserIdea.value || "",
          target_total_duration_sec: parseFloat(elSbTotalDur.value) || 60.0,
          pacing_mode: elSbPacing.value || "auto_adaptive",
          characters_roster: getFullCharactersRoster(),
          ollama_url: elOllamaUrl.value || "https://ollama.smixapp.com",
          ollama_model: elOllamaModel.value || "minimax-m3:cloud",
        }),
      });
      if (resp.ok) {
        const data = await resp.json();
        storyboardState.segments = data.segments || [];
        renderStoryboardQueue();
        elStatusMsg.textContent = `${data.status} | Total: ${data.total_planned_sec}s (${data.total_planned_frames} frames)`;
      } else {
        elStatusMsg.textContent = `Storyboard HTTP Error ${resp.status}`;
      }
    } catch (e) {
      elStatusMsg.textContent = `Storyboard Error: ${e.message}`;
    } finally {
      elSbPlanBtn.disabled = false;
      elSbPlanBtn.textContent = origText;
    }
  });

  elSbAddSegBtn.addEventListener("click", () => {
    const nextIdx = storyboardState.segments.length + 1;
    storyboardState.segments.push({
      segment_index: nextIdx,
      act_title: `Segment ${nextIdx}`,
      transition_type: nextIdx === 1 ? "NEW_SCENE_CUT" : "CONTINUE_FRAME",
      active_character_slots: [1],
      duration_seconds: 8.0,
      frame_length: 192,
      visual_action: "",
      dialogue_lines: [],
      status: "pending",
    });
    renderStoryboardQueue();
  });

  elSbRunNextBtn.addEventListener("click", () => {
    const nextPendingIdx = storyboardState.segments.findIndex((s) => s.status !== "done");
    if (nextPendingIdx === -1) {
      elStatusMsg.textContent = "All storyboard segments are already completed!";
      return;
    }
    storyboardState.autopilotActive = false;
    executeStoryboardSegmentAtIndex(nextPendingIdx);
  });

  elSbAutopilotBtn.addEventListener("click", () => {
    if (storyboardState.autopilotActive) {
      storyboardState.autopilotActive = false;
      elSbAutopilotBtn.textContent = "Auto-Produce All (Autopilot)";
      elStatusMsg.textContent = "Autopilot paused after current segment.";
      return;
    }
    const nextPendingIdx = storyboardState.segments.findIndex((s) => s.status !== "done");
    if (nextPendingIdx === -1) {
      elStatusMsg.textContent = "No pending segments in storyboard queue.";
      return;
    }
    storyboardState.autopilotActive = true;
    elSbAutopilotBtn.textContent = "Stop Autopilot [Running]";
    executeStoryboardSegmentAtIndex(nextPendingIdx);
  });

  elScrubber.addEventListener("input", (e) => {
    if (nleState.playing) stopNLEPlayback();
    loadNLEFrame(parseInt(e.target.value, 10) || 0);
  });

  backdrop.querySelector('[data-nle="jump-start"]').addEventListener("click", () => {
    stopNLEPlayback();
    loadNLEFrame(0);
  });
  backdrop.querySelector('[data-nle="step-prev"]').addEventListener("click", () => {
    stopNLEPlayback();
    loadNLEFrame(nleState.currentFrame - 1);
  });
  backdrop.querySelector('[data-nle="step-next"]').addEventListener("click", () => {
    stopNLEPlayback();
    loadNLEFrame(nleState.currentFrame + 1);
  });
  backdrop.querySelector('[data-nle="jump-end"]').addEventListener("click", () => {
    stopNLEPlayback();
    loadNLEFrame(Math.max(0, nleState.totalFrames - 1));
  });

  btnPlay.addEventListener("click", () => {
    if (nleState.playing) {
      stopNLEPlayback();
      return;
    }
    if (nleState.totalFrames <= 1) return;

    // If playhead is already at the very last frame, rewind to frame 0 automatically
    if (nleState.currentFrame >= nleState.totalFrames - 1) {
      nleState.currentFrame = 0;
    }

    nleState.playing = true;
    btnPlay.textContent = "Pause";

    // Start synchronized stereo audio from the current frame timestamp
    const startSec = nleState.currentFrame / Math.max(1, nleState.fps);
    try {
      nleState.audioEl.currentTime = startSec;
      nleState.audioEl.play().catch(() => {});
    } catch (e) {}

    const frameIntervalMs = 1000 / Math.max(1, nleState.fps);
    let lastTick = performance.now();

    function stepPlayback() {
      if (!nleState.playing) return;
      const now = performance.now();
      const elapsed = now - lastTick;
      const framesToAdvance = Math.max(1, Math.floor(elapsed / frameIntervalMs));
      lastTick = now;

      let nextFrame = nleState.currentFrame + framesToAdvance;
      if (nextFrame >= nleState.totalFrames) {
        nextFrame = 0;
        try {
          nleState.audioEl.currentTime = 0;
          nleState.audioEl.play().catch(() => {});
        } catch (e) {}
      }

      loadNLEFrame(nextFrame, nleState.nodeId, () => {
        if (!nleState.playing) return;
        const decodeDuration = performance.now() - lastTick;
        const waitMs = Math.max(4, Math.round(frameIntervalMs - decodeDuration));
        nleState.playRaf = setTimeout(stepPlayback, waitMs);
      });
    }

    stepPlayback();
  });

  backdrop.querySelector('[data-nle="lock-extend"]').addEventListener("click", async () => {
    stopNLEPlayback();
    await sendExtenderAction({
      action: "lock_playhead",
      global_frame: nleState.currentFrame,
      trim_at_playhead: true,
    });
    elStatusMsg.textContent = `Locked Frame ${nleState.currentFrame} as First-Frame Reference (<Picture 1>) & trimmed tail. Ready to extend!`;
  });

  backdrop.querySelector('[data-nle="undo-seg"]').addEventListener("click", async () => {
    await sendExtenderAction({ action: "drop_last" });
    elStatusMsg.textContent = "Removed last segment from timeline.";
  });

  backdrop.querySelector('[data-nle="clear-timeline"]').addEventListener("click", async () => {
    await sendExtenderAction({ action: "clear" });
    elStatusMsg.textContent = "Cleared timeline.";
  });

  elDurationSec.addEventListener("input", () => {
    updateCalcBadge();
    pushToCanvasPromptNode();
  });
  elUserIdea.addEventListener("input", pushToCanvasPromptNode);
  elH3Mode.addEventListener("change", pushToCanvasPromptNode);
  elOllamaUrl.addEventListener("input", pushToCanvasPromptNode);
  elOllamaModel.addEventListener("change", pushToCanvasPromptNode);
  elCompiledPrompt.addEventListener("input", pushToCanvasPromptNode);

  backdrop.querySelector('[data-nle="add-dialogue"]').addEventListener("click", () => {
    const promptNode = findGraphNodeByType("H3AIPromptComposer");
    if (promptNode && promptNode._h3AddDialogueLine) {
      promptNode._h3AddDialogueLine();
      promptNode._h3RenderNLEDialogues(elDialogueList);
    }
  });

  backdrop.querySelector('[data-nle="refresh-models"]').addEventListener("click", async () => {
    const baseUrl = elOllamaUrl.value || "https://ollama.smixapp.com";
    elStatusMsg.textContent = `Fetching models from ${baseUrl}...`;
    try {
      const resp = await api.fetchApi(`/h3_studio/ollama/models?ollama_url=${encodeURIComponent(baseUrl)}`);
      if (resp.ok) {
        const data = await resp.json();
        const models = data.models || [];
        if (models.length > 0) {
          elOllamaModel.innerHTML = models
            .map((m) => `<option value="${m.name}">${m.name}${m.has_vision ? " [Vision]" : ""}</option>`)
            .join("");
          elStatusMsg.textContent = `Loaded ${models.length} models from ${baseUrl}`;
        }
      }
    } catch (e) {
      elStatusMsg.textContent = `Model sync error: ${e.message}`;
    }
  });

  backdrop.querySelector('[data-nle="generate-prompt"]').addEventListener("click", async () => {
    pushToCanvasPromptNode();
    const promptNode = findGraphNodeByType("H3AIPromptComposer");
    if (promptNode && promptNode._h3TriggerOllamaGenerate) {
      elStatusMsg.textContent = "Generating H3 prompt via Ollama...";
      await promptNode._h3TriggerOllamaGenerate((res) => {
        if (res && res.prompt) {
          elCompiledPrompt.value = res.prompt;
          elStatusMsg.textContent = `${res.status} | Mode: ${res.resolved_mode} | ${res.frame_length}f`;
        }
      }, false);
    }
  });

  backdrop.querySelector('[data-nle="auto-continue-prompt"]').addEventListener("click", async () => {
    stopNLEPlayback();
    if (nleState.totalFrames > 0) {
      await sendExtenderAction({
        action: "lock_playhead",
        global_frame: nleState.currentFrame,
        trim_at_playhead: true,
      });
    }
    pushToCanvasPromptNode();
    const promptNode = findGraphNodeByType("H3AIPromptComposer");
    if (promptNode && promptNode._h3TriggerOllamaGenerate) {
      const nextSegNum = (nleState.segments ? nleState.segments.length : 0) + 1;
      elStatusMsg.textContent = `Locking Frame ${nleState.currentFrame} & composing seamless continuation for Segment #${nextSegNum} via Ollama Vision...`;
      await promptNode._h3TriggerOllamaGenerate((res) => {
        if (res && res.prompt) {
          elCompiledPrompt.value = res.prompt;
          elStatusMsg.textContent = `Seg #${nextSegNum} Ready (${res.resolved_mode}, ${res.frame_length}f) — Click 'Queue Generation in ComfyUI' to extend!`;
        }
      }, true);
    }
  });

  nleStudioInstance = {
    open: () => {
      backdrop.classList.add("open");
      pullFromCanvasNodes();
    },
    refreshSummary: (summary, nodeId) => {
      if (backdrop.classList.contains("open")) {
        renderNLETimeline(summary, nodeId);
      }
      // If a Storyboard Segment just finished rendering in ComfyUI, mark it done and trigger next segment if Autopilot is ON!
      if (storyboardState.activeRunningIdx >= 0 && storyboardState.activeRunningIdx < storyboardState.segments.length) {
        const finishedIdx = storyboardState.activeRunningIdx;
        storyboardState.segments[finishedIdx].status = "done";
        storyboardState.activeRunningIdx = -1;
        renderStoryboardQueue();

        if (storyboardState.autopilotActive) {
          const nextIdx = storyboardState.segments.findIndex((s) => s.status !== "done");
          if (nextIdx !== -1) {
            elStatusMsg.textContent = `Segment #${finishedIdx + 1} complete! Autopilot advancing to Segment #${nextIdx + 1}...`;
            setTimeout(() => {
              if (storyboardState.autopilotActive) {
                executeStoryboardSegmentAtIndex(nextIdx);
              }
            }, 900);
          } else {
            storyboardState.autopilotActive = false;
            elSbAutopilotBtn.textContent = "Auto-Produce All (Autopilot)";
            elStatusMsg.textContent = `All ${storyboardState.segments.length} Storyboard Segments rendered & stitched!`;
          }
        }
      }
    },
  };
  return nleStudioInstance;
}

// ============================================================================
// 1. H3InteractiveVideoExtender Canvas Node UI
// ============================================================================
function setupExtenderNodeUI(node) {
  const wSelectedFrame = findWidget(node, "selected_global_frame");
  const wTrimAtSelected = findWidget(node, "trim_out_at_selected");
  hideBackingWidget(node, "timeline_state_json");

  const panel = document.createElement("div");
  panel.className = "h3-studio-panel";
  panel.innerHTML = `
    <div class="h3-studio-header">
      <div class="h3-studio-title">
        <span>H3 TIMELINE &amp; EXTENDER</span>
        <span class="h3-badge" data-role="seg-badge">0 Segs</span>
      </div>
      <div style="display:flex; gap:5px; align-items:center;">
        <span class="h3-badge h3-badge-amber" data-role="dur-badge">0f (0.00s)</span>
        <button type="button" class="h3-btn h3-btn-primary" data-action="open-nle" title="Open Full-Screen NLE Studio (Alt+H)">
          Open Studio NLE
        </button>
      </div>
    </div>

    <div class="h3-viewport" data-role="viewport">
      <div class="h3-viewport-empty" data-role="empty-msg">
        Timeline kosong.<br/>Klik <b>Open Studio NLE</b> di kanan atas atau jalankan Queue untuk mulai extend video.
      </div>
      <img data-role="frame-img" style="display:none;" alt="H3 Frame Preview" />
      <div class="h3-viewport-overlay">
        <span class="h3-timecode" data-role="tc-left">FRM 0000 / 0000</span>
        <span class="h3-timecode" data-role="tc-right">00:00:00:00</span>
      </div>
    </div>

    <div class="h3-scrubber-row">
      <button type="button" class="h3-btn" data-action="step-prev">-1f</button>
      <button type="button" class="h3-btn" data-action="play-toggle">Play</button>
      <button type="button" class="h3-btn" data-action="step-next">+1f</button>
      <input type="range" class="h3-scrubber-slider" data-role="scrubber" min="0" max="0" value="0" />
      <button type="button" class="h3-btn" data-action="jump-end">End</button>
    </div>

    <div class="h3-segments-strip" data-role="segments-strip">
      <span class="h3-label" style="padding-left:6px;">No segments recorded yet</span>
    </div>

    <div class="h3-btn-row">
      <button type="button" class="h3-btn h3-btn-primary" data-action="lock-extend" style="flex:1;">
        Lock Playhead as First-Frame Ref &amp; Trim Out
      </button>
      <button type="button" class="h3-btn" data-action="drop-last">Undo Seg</button>
      <button type="button" class="h3-btn h3-btn-danger" data-action="clear-all">Reset</button>
    </div>

    <div class="h3-btn-row" style="border-top:1px solid var(--h3-border-hairline); padding-top:6px;">
      <button type="button" class="h3-btn h3-btn-accent" data-action="build-i2v-wf" style="flex:1;">
        Load I2VA Workflow
      </button>
      <button type="button" class="h3-btn h3-btn-accent" data-action="build-ref2v-wf" style="flex:1;">
        Load Ref2VA Studio
      </button>
    </div>
  `;

  const elSegBadge = panel.querySelector('[data-role="seg-badge"]');
  const elDurBadge = panel.querySelector('[data-role="dur-badge"]');
  const elEmptyMsg = panel.querySelector('[data-role="empty-msg"]');
  const elFrameImg = panel.querySelector('[data-role="frame-img"]');
  const elTcLeft = panel.querySelector('[data-role="tc-left"]');
  const elTcRight = panel.querySelector('[data-role="tc-right"]');
  const elScrubber = panel.querySelector('[data-role="scrubber"]');
  const elSegmentsStrip = panel.querySelector('[data-role="segments-strip"]');
  const btnPlay = panel.querySelector('[data-action="play-toggle"]');

  let state = {
    fps: 24,
    totalFrames: 0,
    currentFrame: 0,
    revision: 1,
    segments: [],
    playing: false,
    timer: null,
    audioEl: new Audio(),
  };

  function stopCanvasPlayback() {
    state.playing = false;
    if (state.timer) {
      clearTimeout(state.timer);
      state.timer = null;
    }
    try {
      state.audioEl.pause();
    } catch (e) {}
    btnPlay.textContent = "Play";
  }

  function loadFramePreview(frameIdx, onDone) {
    if (state.totalFrames <= 0) return;
    const clamped = Math.max(0, Math.min(frameIdx, state.totalFrames - 1));
    state.currentFrame = clamped;
    elScrubber.value = String(clamped);
    elTcLeft.textContent = `FRM ${String(clamped).padStart(4, "0")} / ${String(state.totalFrames - 1).padStart(4, "0")}`;
    elTcRight.textContent = formatSMPTETimecode(clamped, state.fps);
    if (wSelectedFrame) wSelectedFrame.value = clamped;

    const nextSrc = api.apiURL(`/h3_studio/extender/frame/${encodeURIComponent(node.id)}/${clamped}?rev=${encodeURIComponent(state.revision)}`);
    if (typeof onDone === "function") {
      const pre = new Image();
      pre.onload = () => {
        elFrameImg.src = nextSrc;
        elFrameImg.style.display = "block";
        elEmptyMsg.style.display = "none";
        onDone();
      };
      pre.onerror = () => onDone();
      pre.src = nextSrc;
    } else {
      elFrameImg.src = nextSrc;
      elFrameImg.style.display = "block";
      elEmptyMsg.style.display = "none";
    }
  }

  function renderSummary(summary) {
    if (!summary) return;
    stopCanvasPlayback();
    state.fps = summary.fps || 24;
    state.totalFrames = summary.total_active_frames || 0;
    state.revision = summary.revision || 1;
    state.segments = summary.segments || [];
    if (state.totalFrames > 0) {
      state.audioEl.src = api.apiURL(`/h3_studio/extender/audio/${encodeURIComponent(node.id)}?rev=${encodeURIComponent(state.revision)}`);
    }

    elSegBadge.textContent = `${state.segments.length} Segs`;
    elDurBadge.textContent = `${state.totalFrames}f (${(summary.total_duration_sec || 0).toFixed(2)}s)`;

    elScrubber.max = String(Math.max(0, state.totalFrames - 1));
    if (state.totalFrames > 0) {
      const target =
        typeof summary.playhead_global_frame === "number"
          ? summary.playhead_global_frame
          : state.totalFrames - 1;
      loadFramePreview(target);
    } else {
      elFrameImg.style.display = "none";
      elEmptyMsg.style.display = "block";
      elTcLeft.textContent = "FRM 0000 / 0000";
      elTcRight.textContent = "00:00:00:00";
    }

    elSegmentsStrip.innerHTML = "";
    if (state.segments.length === 0) {
      elSegmentsStrip.innerHTML = `<span class="h3-label" style="padding-left:6px;">No segments recorded yet</span>`;
    } else {
      let runningStart = 0;
      state.segments.forEach((seg, idx) => {
        const pill = document.createElement("div");
        pill.className = "h3-segment-pill" + (idx === summary.locked_ref_segment_idx ? " active" : "");
        const segEndGlobal = runningStart + seg.active_frames - 1;
        runningStart += seg.active_frames;

        pill.innerHTML = `
          <span><b>SEG ${idx + 1}</b>: ${seg.active_frames}f (${seg.duration_sec}s)</span>
          <span style="font-size:9px; color:var(--h3-text-secondary);">In:${seg.trim_start} Out:${seg.trim_end}</span>
        `;
        pill.addEventListener("click", () => loadFramePreview(segEndGlobal));
        elSegmentsStrip.appendChild(pill);
      });
    }
  }

  node._h3RenderSummary = renderSummary;

  async function postExtenderAction(actionPayload) {
    try {
      const resp = await api.fetchApi("/h3_studio/extender/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: String(node.id), ...actionPayload }),
      });
      if (resp.ok) {
        const summary = await resp.json();
        renderSummary(summary);
      }
    } catch (err) {
      console.error("[H3 Studio] Extender action error:", err);
    }
  }

  panel.querySelector('[data-action="open-nle"]').addEventListener("click", () => {
    createNLEStudioWorkspace().open();
  });

  elScrubber.addEventListener("input", (e) => loadFramePreview(parseInt(e.target.value, 10) || 0));
  panel.querySelector('[data-action="step-prev"]').addEventListener("click", () => loadFramePreview(state.currentFrame - 1));
  panel.querySelector('[data-action="step-next"]').addEventListener("click", () => loadFramePreview(state.currentFrame + 1));
  panel.querySelector('[data-action="jump-end"]').addEventListener("click", () => loadFramePreview(Math.max(0, state.totalFrames - 1)));

  btnPlay.addEventListener("click", () => {
    if (state.playing) {
      stopCanvasPlayback();
      return;
    }
    if (state.totalFrames <= 1) return;
    if (state.currentFrame >= state.totalFrames - 1) {
      state.currentFrame = 0;
    }
    state.playing = true;
    btnPlay.textContent = "Pause";
    try {
      state.audioEl.currentTime = state.currentFrame / Math.max(1, state.fps);
      state.audioEl.play().catch(() => {});
    } catch (e) {}

    const frameIntervalMs = 1000 / Math.max(1, state.fps);
    let lastTick = performance.now();

    function stepCanvasPlay() {
      if (!state.playing) return;
      const now = performance.now();
      const elapsed = now - lastTick;
      const advance = Math.max(1, Math.floor(elapsed / frameIntervalMs));
      lastTick = now;

      let nextFrame = state.currentFrame + advance;
      if (nextFrame >= state.totalFrames) {
        nextFrame = 0;
        try {
          state.audioEl.currentTime = 0;
          state.audioEl.play().catch(() => {});
        } catch (e) {}
      }

      loadFramePreview(nextFrame, () => {
        if (!state.playing) return;
        const waitMs = Math.max(4, Math.round(frameIntervalMs - (performance.now() - lastTick)));
        state.timer = setTimeout(stepCanvasPlay, waitMs);
      });
    }

    stepCanvasPlay();
  });

  panel.querySelector('[data-action="lock-extend"]').addEventListener("click", async () => {
    if (wSelectedFrame) wSelectedFrame.value = state.currentFrame;
    if (wTrimAtSelected) wTrimAtSelected.value = true;
    await postExtenderAction({
      action: "lock_playhead",
      global_frame: state.currentFrame,
      trim_at_playhead: true,
    });
  });

  panel.querySelector('[data-action="drop-last"]').addEventListener("click", async () => {
    await postExtenderAction({ action: "drop_last" });
  });

  panel.querySelector('[data-action="clear-all"]').addEventListener("click", async () => {
    if (wSelectedFrame) wSelectedFrame.value = -1;
    await postExtenderAction({ action: "clear" });
  });

  panel.querySelector('[data-action="build-i2v-wf"]').addEventListener("click", () => {
    loadBundledWorkflow("H3_I2VA_Interactive_Extender.json");
  });

  panel.querySelector('[data-action="build-ref2v-wf"]').addEventListener("click", () => {
    loadBundledWorkflow("H3_Ref2VA_MultiCharacter_Studio.json");
  });

  node.addDOMWidget("h3_extender_dom", "custom_dom", panel, {
    serialize: false,
    hideOnZoom: false,
  });
  node.setSize([430, 520]);

  const origOnExecuted = node.onExecuted;
  node.onExecuted = function (output) {
    if (origOnExecuted) origOnExecuted.apply(this, arguments);
    if (output && output.h3_extender_summary && output.h3_extender_summary[0]) {
      const summary = output.h3_extender_summary[0];
      renderSummary(summary);
      createNLEStudioWorkspace().refreshSummary(summary, String(node.id));
    }
  };
}

// ============================================================================
// 2. H3ModelSpeedAndLoraHub Canvas Node UI
// ============================================================================
function setupModelLoraNodeUI(node) {
  const wLoraJson = hideBackingWidget(node, "lora_stack_json");

  const panel = document.createElement("div");
  panel.className = "h3-studio-panel";
  panel.innerHTML = `
    <div class="h3-studio-header">
      <div class="h3-studio-title">
        <span>UNLIMITED DYNAMIC LoRA STACK</span>
        <span class="h3-badge h3-badge-green" data-role="lora-count">1 Active</span>
      </div>
      <div style="display:flex; gap:4px;">
        <button type="button" class="h3-btn" data-action="refresh-loras" title="Refresh LoRA files">Sync</button>
        <button type="button" class="h3-btn h3-btn-primary" data-action="add-lora">+ Add LoRA</button>
      </div>
    </div>
    <div class="h3-list-container" data-role="lora-list"></div>
  `;

  const elLoraList = panel.querySelector('[data-role="lora-list"]');
  const elLoraCount = panel.querySelector('[data-role="lora-count"]');

  let availableLoras = [
    "None",
    "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
    "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors",
    "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
  ];

  let loraItems = [
    {
      enabled: true,
      name: "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
      model_strength: 1.0,
      clip_strength: 1.0,
    },
  ];

  try {
    if (wLoraJson && wLoraJson.value) {
      const parsed = JSON.parse(wLoraJson.value);
      if (Array.isArray(parsed)) loraItems = parsed;
    }
  } catch (e) {}

  function syncLoraWidget() {
    if (wLoraJson) wLoraJson.value = JSON.stringify(loraItems);
    const activeCount = loraItems.filter((x) => x.enabled && x.name && x.name !== "None").length;
    elLoraCount.textContent = `${activeCount} Active`;
  }

  function renderLoraListInto(targetContainer) {
    targetContainer.innerHTML = "";
    if (loraItems.length === 0) {
      targetContainer.innerHTML = `<div class="h3-label" style="padding:8px; text-align:center;">No LoRAs added. Click <b>+ Add LoRA</b>.</div>`;
      syncLoraWidget();
      return;
    }

    loraItems.forEach((item, idx) => {
      const card = document.createElement("div");
      card.className = "h3-item-card" + (item.enabled ? "" : " disabled");

      const optionsHtml = availableLoras
        .map((l) => `<option value="${l}" ${l === item.name ? "selected" : ""}>${l}</option>`)
        .join("");

      card.innerHTML = `
        <div class="h3-item-row">
          <input type="checkbox" class="h3-toggle" data-field="enabled" ${item.enabled ? "checked" : ""} />
          <select class="h3-select" data-field="name" style="flex:1; min-width:130px;">
            ${optionsHtml}
            ${!availableLoras.includes(item.name) && item.name ? `<option value="${item.name}" selected>${item.name}</option>` : ""}
          </select>
          <button type="button" class="h3-btn h3-btn-danger" data-field="delete">Del</button>
        </div>
        <div class="h3-item-row">
          <span class="h3-label">Model Str:</span>
          <input type="number" class="h3-input" data-field="model_strength" step="0.05" min="-2" max="2" value="${item.model_strength ?? 1.0}" style="width:65px;" />
          <span class="h3-label">CLIP Str:</span>
          <input type="number" class="h3-input" data-field="clip_strength" step="0.05" min="-2" max="2" value="${item.clip_strength ?? 1.0}" style="width:65px;" />
        </div>
      `;

      card.querySelector('[data-field="enabled"]').addEventListener("change", (e) => {
        item.enabled = e.target.checked;
        renderLoraListInto(elLoraList);
        if (targetContainer !== elLoraList) renderLoraListInto(targetContainer);
      });
      card.querySelector('[data-field="name"]').addEventListener("change", (e) => {
        item.name = e.target.value;
        syncLoraWidget();
      });
      card.querySelector('[data-field="model_strength"]').addEventListener("input", (e) => {
        item.model_strength = parseFloat(e.target.value) || 0.0;
        syncLoraWidget();
      });
      card.querySelector('[data-field="clip_strength"]').addEventListener("input", (e) => {
        item.clip_strength = parseFloat(e.target.value) || 0.0;
        syncLoraWidget();
      });
      card.querySelector('[data-field="delete"]').addEventListener("click", () => {
        loraItems.splice(idx, 1);
        renderLoraListInto(elLoraList);
        if (targetContainer !== elLoraList) renderLoraListInto(targetContainer);
      });

      targetContainer.appendChild(card);
    });
    syncLoraWidget();
  }

  node._h3RenderNLELoras = renderLoraListInto;
  node._h3AddLoraItem = () => {
    loraItems.push({
      enabled: true,
      name: availableLoras[1] || "None",
      model_strength: 1.0,
      clip_strength: 1.0,
    });
    renderLoraListInto(elLoraList);
  };

  async function fetchLorasFromServer() {
    try {
      const resp = await api.fetchApi("/h3_studio/loras");
      if (resp.ok) {
        const data = await resp.json();
        if (Array.isArray(data.loras) && data.loras.length > 0) {
          availableLoras = data.loras;
          renderLoraListInto(elLoraList);
        }
      }
    } catch (e) {}
  }

  panel.querySelector('[data-action="add-lora"]').addEventListener("click", () => {
    node._h3AddLoraItem();
  });
  panel.querySelector('[data-action="refresh-loras"]').addEventListener("click", fetchLorasFromServer);

  node.addDOMWidget("h3_lora_dom", "custom_dom", panel, {
    serialize: false,
    hideOnZoom: false,
  });
  node.setSize([410, 420]);

  renderLoraListInto(elLoraList);
  fetchLorasFromServer();
}

// ============================================================================
// 3. H3CharacterReferenceHub Canvas Node UI + Character Library Loader
// ============================================================================
let cachedSavedCharacters = [];

async function fetchSavedCharacterLibrary() {
  try {
    const resp = await api.fetchApi("/h3_studio/characters/library");
    if (resp.ok) {
      const data = await resp.json();
      if (Array.isArray(data.characters)) {
        cachedSavedCharacters = data.characters;
      }
    }
  } catch (e) {}
  return cachedSavedCharacters;
}

function setupCharacterHubNodeUI(node) {
  const wCharsJson = hideBackingWidget(node, "characters_config_json");

  const panel = document.createElement("div");
  panel.className = "h3-studio-panel";
  panel.innerHTML = `
    <div class="h3-studio-header">
      <div class="h3-studio-title">
        <span>MULTI-CHARACTER ROSTER (&lt;Subject 1..N&gt;)</span>
        <span class="h3-badge h3-badge-green" data-role="active-chars-badge">1 ON</span>
      </div>
      <div style="display:flex; gap:4px;">
        <button type="button" class="h3-btn" data-action="sync-lib" title="Refresh Saved Character Library">Lib</button>
        <button type="button" class="h3-btn h3-btn-primary" data-action="add-char">+ Add Char</button>
        <button type="button" class="h3-btn" data-action="open-nle">Studio View</button>
      </div>
    </div>
    <div class="h3-list-container" data-role="char-list" style="max-height:295px;"></div>
  `;

  const elCharList = panel.querySelector('[data-role="char-list"]');
  const elActiveBadge = panel.querySelector('[data-role="active-chars-badge"]');

  let charConfigs = [
    {
      slot: 1,
      enabled: true,
      name: "Char1",
      visual_traits: "young woman with expressive eyes and consistent outfit from reference photo",
      retention: "fully_preserved",
      speaker_id: "S1",
      voice_desc: "clear youthful female voice, natural conversational pace",
      use_audio_ref: true,
      saved_character_id: "",
    },
    {
      slot: 2,
      enabled: false,
      name: "Char2",
      visual_traits: "young man with short dark hair and casual jacket from reference photo",
      retention: "fully_preserved",
      speaker_id: "S2",
      voice_desc: "calm warm male voice, steady cadence",
      use_audio_ref: false,
      saved_character_id: "",
    },
    {
      slot: 3,
      enabled: false,
      name: "Char3",
      visual_traits: "",
      retention: "fully_preserved",
      speaker_id: "S3",
      voice_desc: "",
      use_audio_ref: false,
      saved_character_id: "",
    },
    {
      slot: 4,
      enabled: false,
      name: "Char4",
      visual_traits: "",
      retention: "fully_preserved",
      speaker_id: "S4",
      voice_desc: "",
      use_audio_ref: false,
      saved_character_id: "",
    },
  ];

  try {
    if (wCharsJson && wCharsJson.value) {
      const parsed = JSON.parse(wCharsJson.value);
      if (Array.isArray(parsed) && parsed.length > 0) charConfigs = parsed;
    }
  } catch (e) {}

  function syncCharWidget(badgeOverride) {
    if (wCharsJson) wCharsJson.value = JSON.stringify(charConfigs);
    const active = charConfigs.filter((c) => c.enabled).length;
    elActiveBadge.textContent = `${active} ON`;
    if (badgeOverride) badgeOverride.textContent = `${active} Active`;
  }

  function renderCharCardsInto(targetContainer, badgeOverride) {
    targetContainer.innerHTML = "";
    let activeSubjectIdx = 0;

    charConfigs.forEach((cfg, idx) => {
      if (cfg.enabled) activeSubjectIdx += 1;
      const subjLabel = cfg.enabled ? `<Subject ${activeSubjectIdx}>` : "OFF";
      const savedLibId = cfg.saved_character_id || "";

      const libOptionsHtml = [
        `<option value="">-- Wire Input / Manual --</option>`,
        ...cachedSavedCharacters.map(
          (libChar) =>
            `<option value="${libChar.character_id}" ${libChar.character_id === savedLibId ? "selected" : ""}>[Sheet] ${libChar.name} (${libChar.character_id})</option>`
        ),
      ].join("");

      const thumbUrl = savedLibId
        ? api.apiURL(`/h3_studio/characters/sheet/${encodeURIComponent(savedLibId)}`)
        : "";

      const card = document.createElement("div");
      card.className = "h3-item-card" + (cfg.enabled ? "" : " disabled");
      card.innerHTML = `
        <div class="h3-item-row" style="justify-content:space-between;">
          <div style="display:flex; align-items:center; gap:6px;">
            <input type="checkbox" class="h3-toggle" data-field="enabled" ${cfg.enabled ? "checked" : ""} />
            <b>Slot ${cfg.slot || idx + 1}</b>
            <span class="h3-badge ${cfg.enabled ? "h3-badge-green" : ""}">${subjLabel}</span>
          </div>
          <div style="display:flex; align-items:center; gap:4px;">
            <span class="h3-label">Alias:</span>
            <input type="text" class="h3-input" data-field="name" value="${cfg.name || ""}" style="width:76px;" />
            <span class="h3-label">Spk:</span>
            <input type="text" class="h3-input" data-field="speaker_id" value="${cfg.speaker_id || `S${idx + 1}`}" style="width:34px;" />
          </div>
        </div>
        <div class="h3-item-row">
          <span class="h3-label">Char Lib:</span>
          <select class="h3-select" data-field="saved_character_id" style="flex:1; font-size:10px;">
            ${libOptionsHtml}
          </select>
          ${
            thumbUrl
              ? `<img src="${thumbUrl}" alt="Sheet" title="Loaded 360° Character Sheet from Library" style="width:36px; height:24px; object-fit:cover; border-radius:3px; border:1px solid var(--h3-amber);" />`
              : ""
          }
        </div>
        <div class="h3-item-row">
          <input type="text" class="h3-input" data-field="visual_traits" value="${cfg.visual_traits || ""}" placeholder="Visual appearance traits (<Subject N>)..." style="flex:1;" />
          <select class="h3-select" data-field="retention">
            <option value="fully_preserved" ${cfg.retention === "fully_preserved" ? "selected" : ""}>fully_preserved</option>
            <option value="partially_preserved" ${cfg.retention === "partially_preserved" ? "selected" : ""}>partially_preserved</option>
            <option value="attribute_transfer" ${cfg.retention === "attribute_transfer" ? "selected" : ""}>attribute_transfer</option>
            <option value="weak_reference" ${cfg.retention === "weak_reference" ? "selected" : ""}>weak_reference</option>
          </select>
        </div>
        <div class="h3-item-row">
          <input type="text" class="h3-input" data-field="voice_desc" value="${cfg.voice_desc || ""}" placeholder="Voice timbre description..." style="flex:1;" />
          <label class="h3-label" style="display:flex; align-items:center; gap:3px; cursor:pointer;">
            <input type="checkbox" data-field="use_audio_ref" ${cfg.use_audio_ref ? "checked" : ""} />
            Audio
          </label>
        </div>
      `;

      card.querySelector('[data-field="enabled"]').addEventListener("change", (e) => {
        cfg.enabled = e.target.checked;
        renderCharCardsInto(elCharList);
        if (targetContainer !== elCharList) renderCharCardsInto(targetContainer, badgeOverride);
      });
      card.querySelector('[data-field="saved_character_id"]').addEventListener("change", (e) => {
        const chosenId = e.target.value;
        cfg.saved_character_id = chosenId;
        if (chosenId) {
          const found = cachedSavedCharacters.find((c) => c.character_id === chosenId);
          if (found) {
            cfg.enabled = true;
            if (found.name) cfg.name = found.name;
            if (found.visual_traits) cfg.visual_traits = found.visual_traits;
            if (found.voice_desc) cfg.voice_desc = found.voice_desc;
          }
        }
        renderCharCardsInto(elCharList);
        if (targetContainer !== elCharList) renderCharCardsInto(targetContainer, badgeOverride);
      });
      card.querySelector('[data-field="name"]').addEventListener("input", (e) => {
        cfg.name = e.target.value;
        syncCharWidget(badgeOverride);
      });
      card.querySelector('[data-field="speaker_id"]').addEventListener("input", (e) => {
        cfg.speaker_id = e.target.value;
        syncCharWidget(badgeOverride);
      });
      card.querySelector('[data-field="visual_traits"]').addEventListener("input", (e) => {
        cfg.visual_traits = e.target.value;
        syncCharWidget(badgeOverride);
      });
      card.querySelector('[data-field="retention"]').addEventListener("change", (e) => {
        cfg.retention = e.target.value;
        syncCharWidget(badgeOverride);
      });
      card.querySelector('[data-field="voice_desc"]').addEventListener("input", (e) => {
        cfg.voice_desc = e.target.value;
        syncCharWidget(badgeOverride);
      });
      card.querySelector('[data-field="use_audio_ref"]').addEventListener("change", (e) => {
        cfg.use_audio_ref = e.target.checked;
        syncCharWidget(badgeOverride);
      });

      targetContainer.appendChild(card);
    });

    syncCharWidget(badgeOverride);
  }

  node._h3RenderNLEChars = async (extContainer, extBadge) => {
    await fetchSavedCharacterLibrary();
    renderCharCardsInto(extContainer, extBadge);
  };
  node._h3GetCharConfigs = () => charConfigs;
  node._h3AddCharacterSlot = (extContainer, extBadge) => {
    const nextSlot = charConfigs.length + 1;
    charConfigs.push({
      slot: nextSlot,
      enabled: true,
      name: `Char${nextSlot}`,
      visual_traits: `character ${nextSlot} with distinct appearance`,
      retention: "fully_preserved",
      speaker_id: `S${nextSlot}`,
      voice_desc: "natural expressive voice",
      use_audio_ref: false,
      saved_character_id: "",
    });
    renderCharCardsInto(elCharList);
    if (extContainer && extContainer !== elCharList) {
      renderCharCardsInto(extContainer, extBadge);
    }
  };
  node._h3SetActiveSlots = (activeSlotNums, extContainer, extBadge) => {
    const setNums = new Set((activeSlotNums || []).map((n) => parseInt(n, 10)));
    charConfigs.forEach((cfg, idx) => {
      const sNum = parseInt(cfg.slot || idx + 1, 10);
      cfg.enabled = setNums.has(sNum);
    });
    renderCharCardsInto(elCharList);
    if (extContainer && extContainer !== elCharList) {
      renderCharCardsInto(extContainer, extBadge);
    }
  };

  panel.querySelector('[data-action="sync-lib"]').addEventListener("click", async () => {
    await fetchSavedCharacterLibrary();
    renderCharCardsInto(elCharList);
  });

  panel.querySelector('[data-action="add-char"]').addEventListener("click", () => {
    node._h3AddCharacterSlot();
  });

  panel.querySelector('[data-action="open-nle"]').addEventListener("click", () => {
    createNLEStudioWorkspace().open();
  });

  node.addDOMWidget("h3_char_hub_dom", "custom_dom", panel, {
    serialize: false,
    hideOnZoom: false,
  });
  node.setSize([450, 520]);

  fetchSavedCharacterLibrary().then(() => {
    renderCharCardsInto(elCharList);
  });
}

// ============================================================================
// 4. H3AIPromptComposer Canvas Node UI
// ============================================================================
function setupPromptComposerNodeUI(node) {
  const wDialogueJson = hideBackingWidget(node, "dialogue_lines_json");
  const wUserIdea = findWidget(node, "user_idea");
  const wMode = findWidget(node, "mode");
  const wDuration = findWidget(node, "duration_seconds");
  const wStyle = findWidget(node, "visual_style");
  const wEmbedding = findWidget(node, "style_embedding");
  const wOllamaUrl = findWidget(node, "ollama_url");
  const wOllamaModel = findWidget(node, "ollama_model");
  const wGeneratedPrompt = findWidget(node, "generated_h3_prompt");

  const panel = document.createElement("div");
  panel.className = "h3-studio-panel";
  panel.innerHTML = `
    <div class="h3-studio-header">
      <div class="h3-studio-title">
        <span>DIALOGUE (&lt;d&gt;) &amp; OLLAMA AI</span>
        <span class="h3-badge h3-badge-amber" data-role="calc-badge">124f (5.17s)</span>
      </div>
      <div style="display:flex; gap:4px;">
        <button type="button" class="h3-btn" data-action="fetch-models">Models</button>
        <button type="button" class="h3-btn h3-btn-primary" data-action="add-dialogue">+ Add &lt;d&gt;</button>
      </div>
    </div>

    <div class="h3-item-row">
      <span class="h3-label">Ollama Model:</span>
      <select class="h3-select" data-role="model-select" style="flex:1;">
        <option value="minimax-m3:cloud">minimax-m3:cloud [Vision]</option>
        <option value="qwen3.6:27b">qwen3.6:27b [Vision]</option>
        <option value="huihui_ai/Qwen3.8-abliterated:latest">huihui_ai/Qwen3.8-abliterated:latest [Vision]</option>
        <option value="deepseek-v4-flash:cloud">deepseek-v4-flash:cloud</option>
        <option value="glm-5.2:cloud">glm-5.2:cloud</option>
      </select>
    </div>

    <div class="h3-list-container" data-role="dialogue-list" style="max-height:165px;"></div>

    <div class="h3-btn-row">
      <button type="button" class="h3-btn h3-btn-accent" data-action="generate-now" style="flex:1; padding:7px;">
        Compile H3 Prompt
      </button>
      <button type="button" class="h3-btn h3-btn-primary" data-action="auto-continue-now" style="flex:1; padding:7px;" title="Read previous segment prompt &amp; locked last frame to write next seamless segment">
        AI Auto-Continue Seg
      </button>
    </div>

    <div class="h3-status-bar">
      <span data-role="status-text">Ready — Connected to ollama.smixapp.com</span>
    </div>
  `;

  const elDialogueList = panel.querySelector('[data-role="dialogue-list"]');
  const elModelSelect = panel.querySelector('[data-role="model-select"]');
  const elCalcBadge = panel.querySelector('[data-role="calc-badge"]');
  const elStatusText = panel.querySelector('[data-role="status-text"]');
  const btnGenerate = panel.querySelector('[data-action="generate-now"]');

  let dialogueLines = [
    {
      speaker: "<Subject 1> (S1)",
      language: "Indonesian",
      text: "Akhirnya kamu datang juga, kopinya masih hangat.",
      delivery: "clear youthful female voice with a warm tone",
      voiceover: false,
    },
  ];

  try {
    if (wDialogueJson && wDialogueJson.value) {
      const parsed = JSON.parse(wDialogueJson.value);
      if (Array.isArray(parsed)) dialogueLines = parsed;
    }
  } catch (e) {}

  function updateFrameCalcBadge() {
    const sec = wDuration ? parseFloat(wDuration.value) || 5.0 : 5.0;
    const raw = Math.max(5, Math.round(sec * 24));
    const len = raw + ((5 - (raw % 17)) % 17);
    const eff = (len / 24).toFixed(2);
    elCalcBadge.textContent = `${len}f (${eff}s @ 17k+5)`;
  }

  function syncDialogueWidget() {
    if (wDialogueJson) wDialogueJson.value = JSON.stringify(dialogueLines);
    updateFrameCalcBadge();
  }

  function renderDialogueListInto(targetContainer) {
    targetContainer.innerHTML = "";
    if (dialogueLines.length === 0) {
      targetContainer.innerHTML = `<div class="h3-label" style="padding:6px; text-align:center;">No structured dialogue lines. Click <b>+ Add &lt;d&gt;</b> to add lip-synced or VO speech.</div>`;
      syncDialogueWidget();
      return;
    }

    dialogueLines.forEach((dl, idx) => {
      const card = document.createElement("div");
      card.className = "h3-item-card";
      card.innerHTML = `
        <div class="h3-item-row">
          <input type="text" class="h3-input" data-field="speaker" value="${dl.speaker || `<Subject ${idx + 1}> (S${idx + 1})`}" style="width:112px;" />
          <select class="h3-select" data-field="language">
            ${["Indonesian", "English", "Japanese", "Chinese", "Korean", "Spanish", "French", "German", "Arabic", "Portuguese", "Russian"]
              .map((lang) => `<option value="${lang}" ${dl.language === lang ? "selected" : ""}>[${lang}]</option>`)
              .join("")}
          </select>
          <label class="h3-label" style="display:flex; align-items:center; gap:3px; cursor:pointer;">
            <input type="checkbox" data-field="voiceover" ${dl.voiceover ? "checked" : ""} />
            VO
          </label>
          <button type="button" class="h3-btn h3-btn-danger" data-field="delete" style="margin-left:auto;">Del</button>
        </div>
        <div class="h3-item-row">
          <input type="text" class="h3-input" data-field="text" value="${dl.text || ""}" placeholder="Spoken dialogue line inside <d>..." style="flex:1;" />
        </div>
        <div class="h3-item-row">
          <input type="text" class="h3-input" data-field="delivery" value="${dl.delivery || ""}" placeholder="Vocal delivery / emotion..." style="flex:1;" />
        </div>
      `;

      card.querySelector('[data-field="speaker"]').addEventListener("input", (e) => {
        dl.speaker = e.target.value;
        syncDialogueWidget();
      });
      card.querySelector('[data-field="language"]').addEventListener("change", (e) => {
        dl.language = e.target.value;
        syncDialogueWidget();
      });
      card.querySelector('[data-field="voiceover"]').addEventListener("change", (e) => {
        dl.voiceover = e.target.checked;
        syncDialogueWidget();
      });
      card.querySelector('[data-field="text"]').addEventListener("input", (e) => {
        dl.text = e.target.value;
        syncDialogueWidget();
      });
      card.querySelector('[data-field="delivery"]').addEventListener("input", (e) => {
        dl.delivery = e.target.value;
        syncDialogueWidget();
      });
      card.querySelector('[data-field="delete"]').addEventListener("click", () => {
        dialogueLines.splice(idx, 1);
        renderDialogueListInto(elDialogueList);
        if (targetContainer !== elDialogueList) renderDialogueListInto(targetContainer);
      });

      targetContainer.appendChild(card);
    });
    syncDialogueWidget();
  }

  node._h3RenderNLEDialogues = renderDialogueListInto;
  node._h3SetDialogueLines = (newLines, extContainer) => {
    dialogueLines = Array.isArray(newLines) ? JSON.parse(JSON.stringify(newLines)) : [];
    renderDialogueListInto(elDialogueList);
    if (extContainer && extContainer !== elDialogueList) {
      renderDialogueListInto(extContainer);
    }
  };
  node._h3AddDialogueLine = () => {
    const nextIdx = dialogueLines.length + 1;
    dialogueLines.push({
      speaker: `<Subject ${nextIdx}> (S${nextIdx})`,
      language: "Indonesian",
      text: "",
      delivery: "natural conversational tone",
      voiceover: false,
    });
    renderDialogueListInto(elDialogueList);
  };

  elModelSelect.addEventListener("change", (e) => {
    if (wOllamaModel) wOllamaModel.value = e.target.value;
  });

  async function refreshOllamaModels() {
    const baseUrl = wOllamaUrl ? wOllamaUrl.value : "https://ollama.smixapp.com";
    elStatusText.textContent = `Syncing models from ${baseUrl}...`;
    try {
      const resp = await api.fetchApi(`/h3_studio/ollama/models?ollama_url=${encodeURIComponent(baseUrl)}`);
      if (resp.ok) {
        const data = await resp.json();
        const models = data.models || [];
        if (models.length > 0) {
          elModelSelect.innerHTML = models
            .map((m) => `<option value="${m.name}">${m.name}${m.has_vision ? " [Vision]" : ""}</option>`)
            .join("");
          if (wOllamaModel && wOllamaModel.value) {
            elModelSelect.value = wOllamaModel.value;
          } else if (wOllamaModel) {
            wOllamaModel.value = models[0].name;
          }
          elStatusText.textContent = `Connected: ${models.length} models ready`;
        }
      }
    } catch (e) {
      elStatusText.textContent = `Model sync error: ${e.message}`;
    }
  }

  async function triggerOllamaGenerate(onCompleteCallback, autoContinueStory = false) {
    updateFrameCalcBadge();
    btnGenerate.disabled = true;
    const origLabel = btnGenerate.textContent;
    btnGenerate.textContent = autoContinueStory ? "Extending Story..." : "Compiling H3 Prompt...";
    elStatusText.textContent = autoContinueStory
      ? "Reading locked frame & previous segment prompt via Ollama..."
      : "Calling Ollama LLM...";

    try {
      const extNode = findGraphNodeByType("H3InteractiveVideoExtender");
      const charNode = findGraphNodeByType("H3CharacterReferenceHub");
      const payload = {
        user_idea: wUserIdea ? wUserIdea.value : "",
        mode: wMode ? wMode.value : "Auto",
        duration_seconds: wDuration ? parseFloat(wDuration.value) || 5.0 : 5.0,
        visual_style: wStyle ? wStyle.value : "Live-action, cinematic",
        style_embedding: wEmbedding ? wEmbedding.value : "none",
        ollama_url: wOllamaUrl ? wOllamaUrl.value : "https://ollama.smixapp.com",
        ollama_model: wOllamaModel ? wOllamaModel.value : elModelSelect.value,
        dialogue_lines: dialogueLines,
        extender_node_id: extNode ? String(extNode.id) : "latest",
        char_node_id: charNode ? String(charNode.id) : null,
        auto_continue_story: Boolean(autoContinueStory),
      };

      const resp = await api.fetchApi("/h3_studio/ollama/generate_prompt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (resp.ok) {
        const res = await resp.json();
        if (wGeneratedPrompt && res.prompt) {
          wGeneratedPrompt.value = res.prompt;
        }
        elStatusText.textContent = `${res.status} | ${res.resolved_mode} | ${res.frame_length}f`;
        if (onCompleteCallback) onCompleteCallback(res);
      } else {
        elStatusText.textContent = `HTTP Error ${resp.status}`;
      }
    } catch (err) {
      elStatusText.textContent = `Error: ${err.message}`;
    } finally {
      btnGenerate.disabled = false;
      btnGenerate.textContent = origLabel;
    }
  }

  node._h3TriggerOllamaGenerate = triggerOllamaGenerate;

  panel.querySelector('[data-action="fetch-models"]').addEventListener("click", refreshOllamaModels);
  panel.querySelector('[data-action="add-dialogue"]').addEventListener("click", () => node._h3AddDialogueLine());
  btnGenerate.addEventListener("click", () => triggerOllamaGenerate(null, false));
  const btnAutoContinue = panel.querySelector('[data-action="auto-continue-now"]');
  if (btnAutoContinue) {
    btnAutoContinue.addEventListener("click", () => triggerOllamaGenerate(null, true));
  }

  node.addDOMWidget("h3_prompt_composer_dom", "custom_dom", panel, {
    serialize: false,
    hideOnZoom: false,
  });
  node.setSize([460, 620]);

  const origOnExecuted = node.onExecuted;
  node.onExecuted = function (output) {
    if (origOnExecuted) origOnExecuted.apply(this, arguments);
    if (output) {
      if (output.h3_composed_prompt && output.h3_composed_prompt[0] && wGeneratedPrompt) {
        wGeneratedPrompt.value = output.h3_composed_prompt[0];
      }
      if (output.h3_ai_status && output.h3_ai_status[0]) {
        elStatusText.textContent = output.h3_ai_status[0];
      }
    }
  };

  renderDialogueListInto(elDialogueList);
  refreshOllamaModels();
}

// ============================================================================
// 5. H3CharacterSheetStitcherAndSaver Canvas Node UI
// ============================================================================
function setupCharacterSheetStitcherUI(node) {
  const panel = document.createElement("div");
  panel.className = "h3-studio-panel";
  panel.innerHTML = `
    <div class="h3-studio-header">
      <div class="h3-studio-title">
        <span>360° CHARACTER SHEET LIBRARY</span>
        <span class="h3-badge h3-badge-green" data-role="sheet-badge">Ready</span>
      </div>
      <button type="button" class="h3-btn h3-btn-primary" data-action="open-nle">Open Studio NLE</button>
    </div>
    <div class="h3-viewport" style="height:210px;">
      <div class="h3-viewport-empty" data-role="empty-msg">
        Run workflow untuk mengekstrak 6-panel 360° Character Sheet dari video orbit dan menyimpannya ke Character Library.
      </div>
      <img data-role="sheet-img" style="display:none; width:100%; height:100%; object-fit:contain;" alt="Stitched Character Sheet" />
    </div>
    <div class="h3-status-bar">
      <span data-role="status-text">Saved characters auto-appear in H3 Character Reference Hub &amp; NLE Studio</span>
    </div>
  `;

  const elBadge = panel.querySelector('[data-role="sheet-badge"]');
  const elEmpty = panel.querySelector('[data-role="empty-msg"]');
  const elImg = panel.querySelector('[data-role="sheet-img"]');
  const elStatus = panel.querySelector('[data-role="status-text"]');

  panel.querySelector('[data-action="open-nle"]').addEventListener("click", () => {
    createNLEStudioWorkspace().open();
  });

  node.addDOMWidget("h3_char_sheet_dom", "custom_dom", panel, {
    serialize: false,
    hideOnZoom: false,
  });
  node.setSize([440, 480]);

  const origOnExecuted = node.onExecuted;
  node.onExecuted = function (output) {
    if (origOnExecuted) origOnExecuted.apply(this, arguments);
    if (output && output.h3_saved_character && output.h3_saved_character[0]) {
      const info = output.h3_saved_character[0];
      if (info.character_id) {
        elBadge.textContent = info.character_id;
        elStatus.textContent = info.status || `Saved '${info.name}' to Character Library`;
        elImg.src = api.apiURL(`/h3_studio/characters/sheet/${encodeURIComponent(info.character_id)}?t=${Date.now()}`);
        elImg.style.display = "block";
        elEmpty.style.display = "none";
        fetchSavedCharacterLibrary();
      }
    }
  };
}

// ============================================================================
// Register Extension with ComfyUI (Supports both Legacy LiteGraph & Node 2.0)
// ============================================================================
app.registerExtension({
  name: "ComfyUI.H3Studio.InteractiveExtension",
  async setup() {
    createNLEStudioWorkspace();
  },
  async nodeCreated(node) {
    if (!node) return;
    const t = node.comfyClass || node.type || "";
    if (t === "H3InteractiveVideoExtender" && !node._h3UiInitialized) {
      node._h3UiInitialized = true;
      setupExtenderNodeUI(node);
    } else if (t === "H3ModelSpeedAndLoraHub" && !node._h3UiInitialized) {
      node._h3UiInitialized = true;
      setupModelLoraNodeUI(node);
    } else if (t === "H3CharacterReferenceHub" && !node._h3UiInitialized) {
      node._h3UiInitialized = true;
      setupCharacterHubNodeUI(node);
    } else if (t === "H3AIPromptComposer" && !node._h3UiInitialized) {
      node._h3UiInitialized = true;
      setupPromptComposerNodeUI(node);
    } else if (t === "H3CharacterSheetStitcherAndSaver" && !node._h3UiInitialized) {
      node._h3UiInitialized = true;
      setupCharacterSheetStitcherUI(node);
    }
  },
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!nodeData) return;

    if (nodeData.name === "H3InteractiveVideoExtender") {
      const origCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        if (origCreated) origCreated.apply(this, arguments);
        if (!this._h3UiInitialized) {
          this._h3UiInitialized = true;
          setupExtenderNodeUI(this);
        }
      };
    } else if (nodeData.name === "H3ModelSpeedAndLoraHub") {
      const origCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        if (origCreated) origCreated.apply(this, arguments);
        if (!this._h3UiInitialized) {
          this._h3UiInitialized = true;
          setupModelLoraNodeUI(this);
        }
      };
    } else if (nodeData.name === "H3CharacterReferenceHub") {
      const origCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        if (origCreated) origCreated.apply(this, arguments);
        if (!this._h3UiInitialized) {
          this._h3UiInitialized = true;
          setupCharacterHubNodeUI(this);
        }
      };
    } else if (nodeData.name === "H3AIPromptComposer") {
      const origCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        if (origCreated) origCreated.apply(this, arguments);
        if (!this._h3UiInitialized) {
          this._h3UiInitialized = true;
          setupPromptComposerNodeUI(this);
        }
      };
    } else if (nodeData.name === "H3CharacterSheetStitcherAndSaver") {
      const origCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        if (origCreated) origCreated.apply(this, arguments);
        if (!this._h3UiInitialized) {
          this._h3UiInitialized = true;
          setupCharacterSheetStitcherUI(this);
        }
      };
    }
  },
});
