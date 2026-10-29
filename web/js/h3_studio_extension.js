import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Inject H3 Studio CSS stylesheet into ComfyUI document head
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

function formatTimecode(frameIdx, fps = 24) {
  const sec = Math.max(0, frameIdx) / Math.max(1, fps);
  const mins = Math.floor(sec / 60);
  const rem = (sec % 60).toFixed(2).padStart(5, "0");
  return `${String(mins).padStart(2, "0")}:${rem}s`;
}

// ============================================================================
// 1. H3InteractiveVideoExtender Interactive DOM Widget
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
        <span>H3 TIMELINE & EXTENDER</span>
        <span class="h3-badge" data-role="seg-badge">0 Segs</span>
      </div>
      <span class="h3-badge h3-badge-amber" data-role="dur-badge">0f (0.00s)</span>
    </div>

    <div class="h3-viewport" data-role="viewport">
      <div class="h3-viewport-empty" data-role="empty-msg">
        Belum ada segmen video.<br/>Jalankan Queue atau klik <b>1-Click Build H3 Workflow</b> di bawah.
      </div>
      <img data-role="frame-img" style="display:none;" alt="H3 Frame Preview" />
      <div class="h3-viewport-overlay">
        <span class="h3-timecode" data-role="tc-left">Frame: 0 / 0</span>
        <span class="h3-timecode" data-role="tc-right">00:00.00s</span>
      </div>
    </div>

    <div class="h3-scrubber-row">
      <button type="button" class="h3-btn" data-action="step-prev" title="Mundur 1 Frame (-1f)">-1f</button>
      <button type="button" class="h3-btn" data-action="play-toggle" title="Play / Pause Preview">Play</button>
      <button type="button" class="h3-btn" data-action="step-next" title="Maju 1 Frame (+1f)">+1f</button>
      <input type="range" class="h3-scrubber-slider" data-role="scrubber" min="0" max="0" value="0" />
      <button type="button" class="h3-btn" data-action="jump-end" title="Lompat ke Frame Terakhir">End</button>
    </div>

    <div class="h3-segments-strip" data-role="segments-strip">
      <span class="h3-label" style="padding-left:6px;">Timeline kosong (Segmen klip akan muncul di sini)</span>
    </div>

    <div class="h3-btn-row">
      <button type="button" class="h3-btn h3-btn-primary" data-action="lock-extend" style="flex:1;">
        Lock Playhead as First-Frame Ref & Trim Out
      </button>
      <button type="button" class="h3-btn" data-action="drop-last" title="Hapus segmen terakhir (Re-roll)">
        Undo Seg
      </button>
      <button type="button" class="h3-btn h3-btn-danger" data-action="clear-all" title="Reset seluruh timeline">
        Reset
      </button>
    </div>

    <div class="h3-btn-row" style="border-top:1px solid #232931; padding-top:6px;">
      <button type="button" class="h3-btn h3-btn-accent" data-action="build-i2v-wf" style="flex:1;">
        Auto-Wire H3 I2VA Workflow
      </button>
      <button type="button" class="h3-btn h3-btn-accent" data-action="build-ref2v-wf" style="flex:1;">
        Auto-Wire H3 Ref2VA Studio
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
    segments: [],
    playing: false,
    timer: null,
  };

  function loadFramePreview(frameIdx) {
    if (state.totalFrames <= 0) return;
    const clamped = Math.max(0, Math.min(frameIdx, state.totalFrames - 1));
    state.currentFrame = clamped;
    elScrubber.value = String(clamped);
    elTcLeft.textContent = `Frame: ${clamped} / ${state.totalFrames - 1}`;
    elTcRight.textContent = formatTimecode(clamped, state.fps);
    if (wSelectedFrame) wSelectedFrame.value = clamped;

    const url = `/h3_studio/extender/frame/${encodeURIComponent(node.id)}/${clamped}?t=${Date.now()}`;
    elFrameImg.src = url;
    elFrameImg.style.display = "block";
    elEmptyMsg.style.display = "none";
  }

  function renderSummary(summary) {
    if (!summary) return;
    state.fps = summary.fps || 24;
    state.totalFrames = summary.total_active_frames || 0;
    state.segments = summary.segments || [];

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
      elTcLeft.textContent = "Frame: 0 / 0";
      elTcRight.textContent = "00:00.00s";
    }

    elSegmentsStrip.innerHTML = "";
    if (state.segments.length === 0) {
      elSegmentsStrip.innerHTML = `<span class="h3-label" style="padding-left:6px;">Timeline kosong</span>`;
    } else {
      let runningStart = 0;
      state.segments.forEach((seg, idx) => {
        const pill = document.createElement("div");
        pill.className =
          "h3-segment-pill" + (idx === summary.locked_ref_segment_idx ? " active" : "");
        const segStartGlobal = runningStart;
        const segEndGlobal = runningStart + seg.active_frames - 1;
        runningStart += seg.active_frames;

        pill.innerHTML = `
          <span><b>Seg ${idx + 1}</b>: ${seg.active_frames}f (${seg.duration_sec}s) ${seg.has_audio ? "🔊" : ""}</span>
          <span style="font-size:9px; color:#94a3b8;">In:${seg.trim_start} Out:${seg.trim_end}</span>
        `;
        pill.addEventListener("click", () => {
          loadFramePreview(segEndGlobal);
        });
        elSegmentsStrip.appendChild(pill);
      });
    }
  }

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

  elScrubber.addEventListener("input", (e) => {
    loadFramePreview(parseInt(e.target.value, 10) || 0);
  });

  panel.querySelector('[data-action="step-prev"]').addEventListener("click", () => {
    loadFramePreview(state.currentFrame - 1);
  });

  panel.querySelector('[data-action="step-next"]').addEventListener("click", () => {
    loadFramePreview(state.currentFrame + 1);
  });

  panel.querySelector('[data-action="jump-end"]').addEventListener("click", () => {
    loadFramePreview(Math.max(0, state.totalFrames - 1));
  });

  btnPlay.addEventListener("click", () => {
    if (state.playing) {
      clearInterval(state.timer);
      state.playing = false;
      btnPlay.textContent = "Play";
      return;
    }
    if (state.totalFrames <= 1) return;
    state.playing = true;
    btnPlay.textContent = "Pause";
    state.timer = setInterval(() => {
      const next = (state.currentFrame + 1) % state.totalFrames;
      loadFramePreview(next);
    }, Math.round(1000 / Math.max(1, state.fps)));
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
      renderSummary(output.h3_extender_summary[0]);
    }
  };
}

// ============================================================================
// 2. H3ModelSpeedAndLoraHub Interactive Unlimited LoRA Stack UI
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
        <button type="button" class="h3-btn" data-action="refresh-loras" title="Refresh daftar LoRA">↻</button>
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
    if (wLoraJson) {
      wLoraJson.value = JSON.stringify(loraItems);
    }
    const activeCount = loraItems.filter((x) => x.enabled && x.name && x.name !== "None").length;
    elLoraCount.textContent = `${activeCount} Active`;
  }

  function renderLoraList() {
    elLoraList.innerHTML = "";
    if (loraItems.length === 0) {
      elLoraList.innerHTML = `<div class="h3-label" style="padding:8px; text-align:center;">Belum ada LoRA. Klik <b>+ Add LoRA</b> untuk menambah.</div>`;
      syncLoraWidget();
      return;
    }

    loraItems.forEach((item, idx) => {
      const card = document.createElement("div");
      card.className = "h3-item-card" + (item.enabled ? "" : " disabled");

      const optionsHtml = availableLoras
        .map(
          (l) =>
            `<option value="${l}" ${l === item.name ? "selected" : ""}>${l}</option>`
        )
        .join("");

      card.innerHTML = `
        <div class="h3-item-row">
          <input type="checkbox" class="h3-toggle" data-field="enabled" ${item.enabled ? "checked" : ""} title="On/Off LoRA ini" />
          <select class="h3-select" data-field="name" style="flex:1; min-width:140px;">
            ${optionsHtml}
            ${!availableLoras.includes(item.name) && item.name ? `<option value="${item.name}" selected>${item.name}</option>` : ""}
          </select>
          <button type="button" class="h3-btn h3-btn-danger" data-field="delete" title="Hapus LoRA">✕</button>
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
        renderLoraList();
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
        renderLoraList();
      });

      elLoraList.appendChild(card);
    });
    syncLoraWidget();
  }

  async function fetchLorasFromServer() {
    try {
      const resp = await api.fetchApi("/h3_studio/loras");
      if (resp.ok) {
        const data = await resp.json();
        if (Array.isArray(data.loras) && data.loras.length > 0) {
          availableLoras = data.loras;
          renderLoraList();
        }
      }
    } catch (e) {}
  }

  panel.querySelector('[data-action="add-lora"]').addEventListener("click", () => {
    loraItems.push({
      enabled: true,
      name: availableLoras[1] || "None",
      model_strength: 1.0,
      clip_strength: 1.0,
    });
    renderLoraList();
  });

  panel.querySelector('[data-action="refresh-loras"]').addEventListener("click", () => {
    fetchLorasFromServer();
  });

  node.addDOMWidget("h3_lora_dom", "custom_dom", panel, {
    serialize: false,
    hideOnZoom: false,
  });
  node.setSize([410, 420]);

  renderLoraList();
  fetchLorasFromServer();
}

// ============================================================================
// 3. H3CharacterReferenceHub Interactive Multi-Character Toggle Cards UI
// ============================================================================
function setupCharacterHubNodeUI(node) {
  const wCharsJson = hideBackingWidget(node, "characters_config_json");

  const panel = document.createElement("div");
  panel.className = "h3-studio-panel";
  panel.innerHTML = `
    <div class="h3-studio-header">
      <div class="h3-studio-title">
        <span>MULTI-CHARACTER REFERENCE CARDS</span>
        <span class="h3-badge" data-role="active-chars-badge">1 ON</span>
      </div>
      <span class="h3-label">Auto &lt;Subject N&gt; &amp; (Sx)</span>
    </div>
    <div class="h3-list-container" data-role="char-list" style="max-height:280px;"></div>
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
    },
  ];

  try {
    if (wCharsJson && wCharsJson.value) {
      const parsed = JSON.parse(wCharsJson.value);
      if (Array.isArray(parsed) && parsed.length > 0) {
        charConfigs = parsed;
      }
    }
  } catch (e) {}

  function syncCharWidget() {
    if (wCharsJson) {
      wCharsJson.value = JSON.stringify(charConfigs);
    }
    const active = charConfigs.filter((c) => c.enabled).length;
    elActiveBadge.textContent = `${active} Character(s) ON`;
  }

  function renderCharCards() {
    elCharList.innerHTML = "";
    let activeSubjectIdx = 0;

    charConfigs.forEach((cfg, idx) => {
      if (cfg.enabled) activeSubjectIdx += 1;
      const subjLabel = cfg.enabled ? `<Subject ${activeSubjectIdx}>` : "OFF";

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
            <input type="text" class="h3-input" data-field="name" value="${cfg.name || ""}" placeholder="Mis: Budi" style="width:80px;" />
            <span class="h3-label">Spk:</span>
            <input type="text" class="h3-input" data-field="speaker_id" value="${cfg.speaker_id || `S${idx + 1}`}" style="width:36px;" />
          </div>
        </div>
        <div class="h3-item-row">
          <input type="text" class="h3-input" data-field="visual_traits" value="${cfg.visual_traits || ""}" placeholder="Ciri wajah & pakaian (<Subject N>)..." style="flex:1;" />
          <select class="h3-select" data-field="retention" title="Retention Mode">
            <option value="fully_preserved" ${cfg.retention === "fully_preserved" ? "selected" : ""}>fully_preserved</option>
            <option value="partially_preserved" ${cfg.retention === "partially_preserved" ? "selected" : ""}>partially_preserved</option>
            <option value="attribute_transfer" ${cfg.retention === "attribute_transfer" ? "selected" : ""}>attribute_transfer</option>
            <option value="weak_reference" ${cfg.retention === "weak_reference" ? "selected" : ""}>weak_reference</option>
          </select>
        </div>
        <div class="h3-item-row">
          <input type="text" class="h3-input" data-field="voice_desc" value="${cfg.voice_desc || ""}" placeholder="Suara/Timbre (mis: clear young female voice)..." style="flex:1;" />
          <label class="h3-label" style="display:flex; align-items:center; gap:3px; cursor:pointer;">
            <input type="checkbox" data-field="use_audio_ref" ${cfg.use_audio_ref ? "checked" : ""} />
            Audio Ref
          </label>
        </div>
      `;

      card.querySelector('[data-field="enabled"]').addEventListener("change", (e) => {
        cfg.enabled = e.target.checked;
        renderCharCards();
      });
      card.querySelector('[data-field="name"]').addEventListener("input", (e) => {
        cfg.name = e.target.value;
        syncCharWidget();
      });
      card.querySelector('[data-field="speaker_id"]').addEventListener("input", (e) => {
        cfg.speaker_id = e.target.value;
        syncCharWidget();
      });
      card.querySelector('[data-field="visual_traits"]').addEventListener("input", (e) => {
        cfg.visual_traits = e.target.value;
        syncCharWidget();
      });
      card.querySelector('[data-field="retention"]').addEventListener("change", (e) => {
        cfg.retention = e.target.value;
        syncCharWidget();
      });
      card.querySelector('[data-field="voice_desc"]').addEventListener("input", (e) => {
        cfg.voice_desc = e.target.value;
        syncCharWidget();
      });
      card.querySelector('[data-field="use_audio_ref"]').addEventListener("change", (e) => {
        cfg.use_audio_ref = e.target.checked;
        syncCharWidget();
      });

      elCharList.appendChild(card);
    });

    syncCharWidget();
  }

  node.addDOMWidget("h3_char_hub_dom", "custom_dom", panel, {
    serialize: false,
    hideOnZoom: false,
  });
  node.setSize([440, 490]);

  renderCharCards();
}

// ============================================================================
// 4. H3AIPromptComposer Interactive Dialogue (<d>) Builder & Ollama Live UI
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
        <span>DIALOGUE (&lt;d&gt;) BUILDER &amp; OLLAMA AI</span>
        <span class="h3-badge h3-badge-amber" data-role="calc-badge">124f (5.17s)</span>
      </div>
      <div style="display:flex; gap:4px;">
        <button type="button" class="h3-btn" data-action="fetch-models" title="Ambil daftar model dari ollama.smixapp.com">Models ↻</button>
        <button type="button" class="h3-btn h3-btn-primary" data-action="add-dialogue">+ Add &lt;d&gt; Line</button>
      </div>
    </div>

    <div class="h3-item-row">
      <span class="h3-label">Pilih Model Server:</span>
      <select class="h3-select" data-role="model-select" style="flex:1;">
        <option value="minimax-m3:cloud">minimax-m3:cloud (Vision + Thinking)</option>
        <option value="qwen3.6:27b">qwen3.6:27b (Vision)</option>
        <option value="huihui_ai/Qwen3.8-abliterated:latest">huihui_ai/Qwen3.8-abliterated:latest (Vision)</option>
        <option value="deepseek-v4-flash:cloud">deepseek-v4-flash:cloud</option>
        <option value="glm-5.2:cloud">glm-5.2:cloud</option>
        <option value="gemma3:latest">gemma3:latest</option>
      </select>
    </div>

    <div class="h3-list-container" data-role="dialogue-list" style="max-height:165px;"></div>

    <div class="h3-btn-row">
      <button type="button" class="h3-btn h3-btn-accent" data-action="generate-now" style="flex:1; padding:7px;">
        Generate H3 Prompt Now (via ollama.smixapp.com)
      </button>
    </div>

    <div class="h3-status-bar">
      <span data-role="status-text">Ready — Klik tombol di atas atau langsung Queue Prompt</span>
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
    if (wDialogueJson) {
      wDialogueJson.value = JSON.stringify(dialogueLines);
    }
    updateFrameCalcBadge();
  }

  function renderDialogueList() {
    elDialogueList.innerHTML = "";
    if (dialogueLines.length === 0) {
      elDialogueList.innerHTML = `<div class="h3-label" style="padding:6px; text-align:center;">Tanpa dialog khusus (atau tulis dialog di cerita utama). Klik <b>+ Add &lt;d&gt; Line</b> untuk menambah dialog presisi.</div>`;
      syncDialogueWidget();
      return;
    }

    dialogueLines.forEach((dl, idx) => {
      const card = document.createElement("div");
      card.className = "h3-item-card";
      card.innerHTML = `
        <div class="h3-item-row">
          <input type="text" class="h3-input" data-field="speaker" value="${dl.speaker || `<Subject ${idx + 1}> (S${idx + 1})`}" placeholder="<Subject 1> (S1)" style="width:115px;" title="Speaker ID H3" />
          <select class="h3-select" data-field="language" title="Bahasa asli di dalam <d>[Language] ...</d>">
            ${["Indonesian", "English", "Japanese", "Chinese", "Korean", "Spanish", "French", "German", "Arabic", "Portuguese", "Russian"]
              .map((lang) => `<option value="${lang}" ${dl.language === lang ? "selected" : ""}>[${lang}]</option>`)
              .join("")}
          </select>
          <label class="h3-label" style="display:flex; align-items:center; gap:3px; cursor:pointer;" title="Off-screen voiceover (bibir karakter tetap tertutup)">
            <input type="checkbox" data-field="voiceover" ${dl.voiceover ? "checked" : ""} />
            VO
          </label>
          <button type="button" class="h3-btn h3-btn-danger" data-field="delete" style="margin-left:auto;">✕</button>
        </div>
        <div class="h3-item-row">
          <input type="text" class="h3-input" data-field="text" value="${dl.text || ""}" placeholder="Kalimat dialog verbatim (mis: Ayo kita berangkat sekarang!)..." style="flex:1;" />
        </div>
        <div class="h3-item-row">
          <input type="text" class="h3-input" data-field="delivery" value="${dl.delivery || ""}" placeholder="Nada bicara (mis: calm voice with slight excitement)..." style="flex:1;" />
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
        renderDialogueList();
      });

      elDialogueList.appendChild(card);
    });
    syncDialogueWidget();
  }

  elModelSelect.addEventListener("change", (e) => {
    if (wOllamaModel) wOllamaModel.value = e.target.value;
  });

  async function refreshOllamaModels() {
    const baseUrl = wOllamaUrl ? wOllamaUrl.value : "https://ollama.smixapp.com";
    elStatusText.textContent = `Mengambil daftar model dari ${baseUrl}...`;
    try {
      const resp = await api.fetchApi(
        `/h3_studio/ollama/models?ollama_url=${encodeURIComponent(baseUrl)}`
      );
      if (resp.ok) {
        const data = await resp.json();
        const models = data.models || [];
        if (models.length > 0) {
          elModelSelect.innerHTML = models
            .map(
              (m) =>
                `<option value="${m.name}">${m.name}${m.has_vision ? " [Vision]" : ""}</option>`
            )
            .join("");
          if (wOllamaModel && wOllamaModel.value) {
            elModelSelect.value = wOllamaModel.value;
          } else if (wOllamaModel) {
            wOllamaModel.value = models[0].name;
          }
          elStatusText.textContent = `Terhubung: ${models.length} model siap di ${baseUrl}`;
        }
      }
    } catch (e) {
      elStatusText.textContent = `Gagal memuat daftar model (${e.message})`;
    }
  }

  panel.querySelector('[data-action="fetch-models"]').addEventListener("click", () => {
    refreshOllamaModels();
  });

  panel.querySelector('[data-action="add-dialogue"]').addEventListener("click", () => {
    const nextIdx = dialogueLines.length + 1;
    dialogueLines.push({
      speaker: `<Subject ${nextIdx}> (S${nextIdx})`,
      language: "Indonesian",
      text: "",
      delivery: "natural conversational tone",
      voiceover: false,
    });
    renderDialogueList();
  });

  btnGenerate.addEventListener("click", async () => {
    updateFrameCalcBadge();
    btnGenerate.disabled = true;
    const origLabel = btnGenerate.textContent;
    btnGenerate.textContent = "Generating H3 Prompt via Ollama...";
    elStatusText.textContent = "Memanggil LLM di ollama.smixapp.com...";

    try {
      const payload = {
        user_idea: wUserIdea ? wUserIdea.value : "",
        mode: wMode ? wMode.value : "Auto",
        duration_seconds: wDuration ? parseFloat(wDuration.value) || 5.0 : 5.0,
        visual_style: wStyle ? wStyle.value : "Live-action, cinematic",
        style_embedding: wEmbedding ? wEmbedding.value : "none",
        ollama_url: wOllamaUrl ? wOllamaUrl.value : "https://ollama.smixapp.com",
        ollama_model: wOllamaModel ? wOllamaModel.value : elModelSelect.value,
        dialogue_lines: dialogueLines,
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
        elStatusText.textContent = `${res.status} | Mode: ${res.resolved_mode} | ${res.frame_length}f (${res.effective_duration_sec}s)`;
      } else {
        elStatusText.textContent = `HTTP Error ${resp.status}`;
      }
    } catch (err) {
      elStatusText.textContent = `Error: ${err.message}`;
    } finally {
      btnGenerate.disabled = false;
      btnGenerate.textContent = origLabel;
    }
  });

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

  renderDialogueList();
  refreshOllamaModels();
}

// ============================================================================
// Helper: Load Bundled H3 Complete Workflow JSON into ComfyUI Canvas
// ============================================================================
async function loadBundledWorkflow(templateName) {
  try {
    const resp = await api.fetchApi(`/h3_studio/workflows/${encodeURIComponent(templateName)}`);
    if (!resp.ok) {
      alert(`Gagal memuat workflow template: ${templateName}`);
      return;
    }
    const wfJson = await resp.json();
    await app.loadGraphData(wfJson, true, true, templateName);
  } catch (err) {
    console.error("[H3 Studio] Failed loading workflow:", err);
  }
}

// ============================================================================
// Register Extension with ComfyUI
// ============================================================================
app.registerExtension({
  name: "ComfyUI.H3Studio.InteractiveExtension",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!nodeData) return;

    if (nodeData.name === "H3InteractiveVideoExtender") {
      const origCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        if (origCreated) origCreated.apply(this, arguments);
        setupExtenderNodeUI(this);
      };
    } else if (nodeData.name === "H3ModelSpeedAndLoraHub") {
      const origCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        if (origCreated) origCreated.apply(this, arguments);
        setupModelLoraNodeUI(this);
      };
    } else if (nodeData.name === "H3CharacterReferenceHub") {
      const origCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        if (origCreated) origCreated.apply(this, arguments);
        setupCharacterHubNodeUI(this);
      };
    } else if (nodeData.name === "H3AIPromptComposer") {
      const origCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        if (origCreated) origCreated.apply(this, arguments);
        setupPromptComposerNodeUI(this);
      };
    }
  },
});
