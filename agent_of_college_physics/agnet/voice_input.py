from __future__ import annotations

import streamlit as st


VOICE_HTML = """
<div class="voice-controller" aria-hidden="true"></div>
"""


VOICE_CSS = """
.voice-controller { width: 0; height: 0; overflow: visible; }
"""


VOICE_JS = r"""
export default function(component) {
  const data = component.data || {};
  const controllerKey = '__physicsVoiceInputController';
  const previousController = window[controllerKey];
  if (previousController && typeof previousController.dispose === 'function') {
    try { previousController.dispose(); } catch (_) {}
  }

  // Controllers created by an older build did not publish a disposer.  Keep
  // their nodes connected in an invisible retirement bin so their observers
  // cannot reinsert duplicate microphone buttons during this hot upgrade.
  let retirementBin = document.getElementById('physics-voice-retired-portals');
  if (!retirementBin) {
    retirementBin = document.createElement('div');
    retirementBin.id = 'physics-voice-retired-portals';
    retirementBin.setAttribute('aria-hidden', 'true');
    retirementBin.style.setProperty('display', 'none', 'important');
    document.body.appendChild(retirementBin);
  }
  document.querySelectorAll('.physics-voice-button, .physics-voice-popover').forEach((node) => {
    if (!retirementBin.contains(node)) retirementBin.appendChild(node);
  });

  const instanceId = (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function')
    ? globalThis.crypto.randomUUID()
    : String(Date.now()) + '-' + Math.random().toString(16).slice(2);
  let disposed = false;

  const portalStyle = document.createElement('style');
  portalStyle.textContent = `
    .physics-voice-button {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      flex: 0 0 auto;
      width: 2rem;
      height: 2rem;
      margin: 0;
      padding: 0;
      border: 0;
      border-radius: .58rem;
      background: transparent;
      color: color-mix(in srgb, var(--st-text-color) 72%, transparent);
      cursor: pointer;
      transition: color .16s ease, background .16s ease, transform .16s ease;
    }
    .physics-voice-button:hover:not(:disabled),
    .physics-voice-button:focus-visible {
      color: var(--st-primary-color);
      background: color-mix(in srgb, var(--st-primary-color) 12%, transparent);
      outline: none;
    }
    .physics-voice-button:focus-visible {
      box-shadow: 0 0 0 2px color-mix(in srgb, var(--st-primary-color) 48%, transparent);
    }
    .physics-voice-button:disabled { cursor: not-allowed; opacity: .42; }
    .physics-voice-button.recording {
      color: #ff5964;
      background: color-mix(in srgb, #ff5964 13%, transparent);
    }
    .physics-voice-button.unavailable { color: #e05b64; }
    .physics-voice-button svg { width: 1.08rem; height: 1.08rem; pointer-events: none; }
    .physics-voice-button.recording::after {
      content: '';
      position: absolute;
      inset: .18rem;
      border: 2px solid currentColor;
      border-radius: .46rem;
      animation: physics-voice-pulse 1.25s infinite;
      pointer-events: none;
    }
    .physics-voice-sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .physics-voice-popover {
      position: absolute;
      right: .65rem;
      bottom: calc(100% + .52rem);
      z-index: 1000002;
      width: max-content;
      max-width: min(32rem, calc(100vw - 1rem));
      padding: .52rem .72rem;
      border: 1px solid color-mix(in srgb, var(--st-border-color) 82%, transparent);
      border-radius: .72rem;
      background: color-mix(in srgb, var(--st-secondary-background-color) 96%, transparent);
      box-shadow: 0 .45rem 1.45rem rgba(0, 0, 0, .18);
      color: var(--st-text-color);
      font-size: .8rem;
      line-height: 1.38;
      opacity: 0;
      visibility: hidden;
      transform: translateY(.2rem);
      transition: opacity .16s ease, transform .16s ease, visibility .16s ease;
      pointer-events: none;
    }
    .physics-voice-popover.visible {
      opacity: 1;
      visibility: visible;
      transform: translateY(0);
    }
    .physics-voice-status.error { color: #e05b64; }
    .physics-voice-partial {
      display: none;
      max-width: min(30rem, calc(100vw - 2.5rem));
      margin-top: .18rem;
      overflow: hidden;
      color: color-mix(in srgb, var(--st-text-color) 72%, transparent);
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .physics-voice-partial:not(:empty) { display: block; }
    @keyframes physics-voice-pulse {
      0% { opacity: .8; transform: scale(.82); }
      75%, 100% { opacity: 0; transform: scale(1.28); }
    }
    @media (prefers-reduced-motion: reduce) {
      .physics-voice-button, .physics-voice-popover { transition: none; }
      .physics-voice-button.recording::after { animation: none; }
    }
    @media (forced-colors: active) {
      .physics-voice-button { color: ButtonText; }
      .physics-voice-button.recording, .physics-voice-button.unavailable { color: Highlight; }
      .physics-voice-popover { border: 1px solid CanvasText; background: Canvas; }
    }
  `;
  document.head.appendChild(portalStyle);

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'physics-voice-button';
  button.setAttribute('aria-pressed', 'false');
  button.setAttribute('aria-label', '语音输入');
  button.title = '语音输入';
  button.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
         stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <rect x="9" y="2" width="6" height="12" rx="3"></rect>
      <path d="M5 10a7 7 0 0 0 14 0"></path>
      <path d="M12 17v5"></path>
      <path d="M8 22h8"></path>
    </svg>
    <span class="physics-voice-sr-only">语音输入</span>`;
  const label = button.querySelector('.physics-voice-sr-only');

  const popover = document.createElement('div');
  popover.className = 'physics-voice-popover';
  popover.setAttribute('role', 'status');
  popover.setAttribute('aria-live', 'polite');
  popover.innerHTML = `
    <div class="physics-voice-status">正在检查语音服务……</div>
    <div class="physics-voice-partial"></div>`;
  const status = popover.querySelector('.physics-voice-status');
  const partial = popover.querySelector('.physics-voice-partial');
  let portalObserver = null;
  let portalFrame = 0;
  let statusTimer = null;
  const targetRate = 16000;
  let socket = null;
  let mediaStream = null;
  let audioContext = null;
  let sourceNode = null;
  let recorderNode = null;
  let muteNode = null;
  let workletUrl = null;
  let recording = false;
  let stopping = false;
  let terminalReceived = false;
  let timeoutHandle = null;
  let baseText = '';
  let sourceBuffer = new Float32Array(0);
  let sourcePosition = 0;
  let outboundParts = [];
  let outboundCount = 0;

  function dispose() {
    if (disposed) return;
    disposed = true;
    terminalReceived = true;
    if (statusTimer) window.clearTimeout(statusTimer);
    if (portalFrame) window.cancelAnimationFrame(portalFrame);
    if (portalObserver) portalObserver.disconnect();
    button.onclick = null;
    if (recorderNode) recorderNode.port.onmessage = null;
    stopCapture();
    const activeSocket = socket;
    socket = null;
    if (activeSocket) {
      activeSocket.onopen = null;
      activeSocket.onmessage = null;
      activeSocket.onerror = null;
      activeSocket.onclose = null;
      if (activeSocket.readyState < WebSocket.CLOSING) activeSocket.close();
    }
    button.remove();
    popover.remove();
    portalStyle.remove();
    if (window[controllerKey]?.instanceId === instanceId) {
      delete window[controllerKey];
    }
  }

  window[controllerKey] = {instanceId, dispose};

  function setButtonLabel(message) {
    label.textContent = message;
    button.setAttribute('aria-label', message);
    button.title = message;
  }

  function setStatus(message, isError, sticky = false) {
    status.textContent = message;
    status.classList.toggle('error', Boolean(isError));
    popover.classList.toggle('visible', Boolean(message));
    if (statusTimer) window.clearTimeout(statusTimer);
    statusTimer = null;
    if (message && !sticky) {
      statusTimer = window.setTimeout(() => popover.classList.remove('visible'), isError ? 6500 : 3200);
    }
  }

  function retireDuplicatePortals() {
    document.querySelectorAll('.physics-voice-button, .physics-voice-popover').forEach((node) => {
      if (node !== button && node !== popover && !retirementBin.contains(node)) {
        retirementBin.appendChild(node);
      }
    });
  }

  function ensurePortal() {
    if (disposed) return;
    retireDuplicatePortals();
    const chat = document.querySelector('[data-testid="stChatInput"]');
    if (!chat) return;
    const submit = chat.querySelector(
      '[data-testid="stChatInputSubmitButton"], [data-testid="stChatInputStopButton"]'
    );
    const actions = submit && submit.parentElement;
    if (actions && button.parentElement !== actions) actions.insertBefore(button, submit);
    if (popover.parentElement !== chat) chat.appendChild(popover);
  }

  function schedulePortal() {
    if (disposed || portalFrame) return;
    portalFrame = window.requestAnimationFrame(() => {
      portalFrame = 0;
      ensurePortal();
    });
  }

  function chatDraft() {
    const textarea = document.querySelector('[data-testid="stChatInput"] textarea');
    return textarea ? textarea.value.trim() : '';
  }

  function fillChatDraft(value) {
    const textarea = document.querySelector('[data-testid="stChatInput"] textarea')
      || document.querySelector('[data-testid="stChatInputTextArea"]');
    if (!textarea) return;
    const setter = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype, 'value'
    )?.set;
    if (setter) setter.call(textarea, value);
    else textarea.value = value;
    textarea.dispatchEvent(new Event('input', {bubbles: true}));
    textarea.dispatchEvent(new Event('change', {bubbles: true}));
  }

  function combinedText(spoken) {
    const clean = (spoken || '').trim();
    if (!baseText) return clean;
    if (!clean) return baseText;
    return baseText + ' ' + clean;
  }

  function runtimeAsrPath() {
    const pagePath = (window.location.pathname || '/').replace(/\/+$/, '');
    if (!pagePath || pagePath === '/') return '/asr/ws';
    return pagePath + '/asr/ws';
  }

  function websocketUrl() {
    const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return scheme + '//' + window.location.host + runtimeAsrPath();
  }

  function appendSource(input) {
    const merged = new Float32Array(sourceBuffer.length + input.length);
    merged.set(sourceBuffer, 0);
    merged.set(input, sourceBuffer.length);
    const ratio = audioContext.sampleRate / targetRate;
    const output = [];
    while (sourcePosition + 1 < merged.length) {
      const index = Math.floor(sourcePosition);
      const fraction = sourcePosition - index;
      output.push(merged[index] + (merged[index + 1] - merged[index]) * fraction);
      sourcePosition += ratio;
    }
    const consumed = Math.min(Math.floor(sourcePosition), merged.length);
    sourceBuffer = merged.slice(consumed);
    sourcePosition -= consumed;
    if (output.length) queueForSend(new Float32Array(output));
  }

  function queueForSend(samples) {
    outboundParts.push(samples);
    outboundCount += samples.length;
    if (outboundCount >= 1600) flushAudio();
  }

  function flushAudio() {
    if (!outboundCount) return true;
    const combined = new Float32Array(outboundCount);
    let offset = 0;
    for (const part of outboundParts) {
      combined.set(part, offset);
      offset += part.length;
    }
    outboundParts = [];
    outboundCount = 0;
    if (socket && socket.readyState === WebSocket.OPEN) {
      if (socket.bufferedAmount > 1024 * 1024) {
        terminalReceived = true;
        stopCapture();
        socket.close(1009, 'audio backlog');
        setStatus('网络发送积压过多，请检查连接后重试', true);
        return false;
      }
      socket.send(combined.buffer);
    }
    return true;
  }

  async function startAudio() {
    const acquiredStream = await navigator.mediaDevices.getUserMedia({
      audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true},
      video: false
    });
    if (disposed) {
      acquiredStream.getTracks().forEach((track) => track.stop());
      throw new DOMException('语音组件已更新', 'AbortError');
    }
    mediaStream = acquiredStream;
    audioContext = new AudioContext({latencyHint: 'interactive'});
    await audioContext.resume();
    if (disposed) {
      stopCapture();
      throw new DOMException('语音组件已更新', 'AbortError');
    }
    if (audioContext.state !== 'running') throw new Error('浏览器未允许启动音频设备');
    const workletSource = [
      'class PhysicsVoiceProcessor extends AudioWorkletProcessor {',
      '  process(inputs) {',
      '    const input = inputs[0] && inputs[0][0];',
      '    if (input) { const copy = new Float32Array(input); this.port.postMessage(copy, [copy.buffer]); }',
      '    return true;',
      '  }',
      '}',
      "registerProcessor('physics-voice-processor', PhysicsVoiceProcessor);"
    ].join('\n');
    workletUrl = URL.createObjectURL(new Blob([workletSource], {type: 'text/javascript'}));
    await audioContext.audioWorklet.addModule(workletUrl);
    if (disposed) {
      stopCapture();
      throw new DOMException('语音组件已更新', 'AbortError');
    }
    sourceNode = audioContext.createMediaStreamSource(mediaStream);
    recorderNode = new AudioWorkletNode(audioContext, 'physics-voice-processor');
    muteNode = audioContext.createGain();
    muteNode.gain.value = 0;
    recorderNode.port.onmessage = (event) => {
      if (!disposed && recording && event.data) appendSource(new Float32Array(event.data));
    };
    sourceNode.connect(recorderNode);
    recorderNode.connect(muteNode);
    muteNode.connect(audioContext.destination);
    recording = true;
    button.classList.add('recording');
    button.setAttribute('aria-pressed', 'true');
    setButtonLabel('停止录音并填入提问框');
    setStatus('正在识别，点击麦克风即可停止', false, true);
    const maximum = Math.max(10, Number(data.maxSeconds || 180));
    timeoutHandle = window.setTimeout(() => finishRecording(), maximum * 1000);
  }

  function stopCapture() {
    recording = false;
    if (timeoutHandle) window.clearTimeout(timeoutHandle);
    timeoutHandle = null;
    if (sourceNode) sourceNode.disconnect();
    if (recorderNode) recorderNode.disconnect();
    if (muteNode) muteNode.disconnect();
    if (mediaStream) mediaStream.getTracks().forEach((track) => track.stop());
    if (audioContext && audioContext.state !== 'closed') audioContext.close();
    if (workletUrl) URL.revokeObjectURL(workletUrl);
    sourceNode = null;
    recorderNode = null;
    muteNode = null;
    mediaStream = null;
    audioContext = null;
    workletUrl = null;
    button.classList.remove('recording');
    button.setAttribute('aria-pressed', 'false');
    setButtonLabel('语音输入');
  }

  async function beginRecording() {
    if (data.disabled || disposed) return;
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatus('当前页面不是安全来源；请使用 HTTPS 后启用麦克风', true);
      return;
    }
    baseText = chatDraft();
    sourceBuffer = new Float32Array(0);
    sourcePosition = 0;
    outboundParts = [];
    outboundCount = 0;
    stopping = false;
    terminalReceived = false;
    partial.textContent = '';
    setStatus('正在连接 Paraformer 语音服务……', false, true);
    button.disabled = true;
    socket = new WebSocket(websocketUrl());
    socket.binaryType = 'arraybuffer';
    socket.onopen = () => {
      if (disposed) return;
      socket.send(JSON.stringify({type: 'start', sample_rate: targetRate, format: 'pcm_f32le'}));
    };
    socket.onmessage = async (event) => {
      if (disposed) return;
      let message;
      try { message = JSON.parse(event.data); } catch (_) { return; }
      if (message.type === 'ready') {
        try {
          await startAudio();
          if (disposed) return;
          button.disabled = false;
        } catch (error) {
          if (disposed) return;
          terminalReceived = true;
          stopCapture();
          setStatus('无法取得麦克风权限：' + (error.message || error), true);
          if (socket) socket.close();
          button.disabled = false;
        }
      } else if (message.type === 'partial') {
        partial.textContent = message.text || '';
      } else if (message.type === 'final') {
        terminalReceived = true;
        stopCapture();
        stopping = false;
        button.disabled = Boolean(data.disabled);
        const text = combinedText(message.text || '');
        if (text && text !== baseText) {
          partial.textContent = message.text || '';
          setStatus('识别完成，文字已填入提问框', false);
          fillChatDraft(text);
          component.setTriggerValue('commit', {
            id: message.id || String(Date.now()),
            text: text
          });
        } else {
          setStatus('没有识别到清晰语音，请重试', true);
        }
      } else if (message.type === 'error') {
        terminalReceived = true;
        stopCapture();
        stopping = false;
        button.disabled = Boolean(data.disabled);
        setStatus(message.message || '语音识别失败', true);
      }
    };
    socket.onerror = () => {
      if (disposed) return;
      terminalReceived = true;
      stopCapture();
      stopping = false;
      button.disabled = Boolean(data.disabled);
      setStatus('无法连接 Paraformer 语音服务', true);
    };
    socket.onclose = (event) => {
      if (disposed) return;
      if (recording) stopCapture();
      if (!terminalReceived) {
        const text = event.code === 1000
          ? '语音服务未返回最终结果，请重试'
          : '语音连接已断开，请重试';
        setStatus(text, true);
      }
      stopping = false;
      button.disabled = Boolean(data.disabled);
    };
  }

  function finishRecording() {
    if (disposed || !recording || stopping) return;
    stopping = true;
    setStatus('正在整理最终识别结果……', false, true);
    if (!flushAudio()) return;
    stopCapture();
    button.disabled = true;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({type: 'finish'}));
    } else {
      stopping = false;
      button.disabled = Boolean(data.disabled);
      setStatus('语音连接已断开，请重试', true);
    }
  }

  button.onclick = () => recording ? finishRecording() : beginRecording();
  button.disabled = Boolean(data.disabled);
  portalObserver = new MutationObserver(() => {
    const duplicateVisible = Array.from(
      document.querySelectorAll('.physics-voice-button, .physics-voice-popover')
    ).some((node) => node !== button && node !== popover && !retirementBin.contains(node));
    if (button.isConnected && popover.isConnected && !duplicateVisible) return;
    schedulePortal();
  });
  portalObserver.observe(document.body, {childList: true, subtree: true});
  ensurePortal();
  if (data.disabled) {
    setStatus('回答生成过程中暂不录音', false);
  } else if (!window.isSecureContext) {
    button.classList.add('unavailable');
    // Keep the input row clean on ordinary HTTP pages.  The actionable
    // explanation is shown only after the user presses the microphone.
    setButtonLabel('需要 HTTPS 才能录音');
  } else {
    const healthPath = runtimeAsrPath().replace(/\/ws$/, '/health');
    fetch(healthPath, {cache: 'no-store'})
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then(() => {
        if (!disposed) setStatus('Paraformer 中文流式识别已就绪', false);
      })
      .catch(() => {
        if (!disposed) setStatus('语音服务尚未就绪，请稍后重试', true);
      });
  }

  return dispose;
}
"""


voice_component = st.components.v2.component(
    "paraformer_voice_input",
    html=VOICE_HTML,
    css=VOICE_CSS,
    js=VOICE_JS,
)


def render_voice_input(*, disabled: bool = False) -> dict | None:
    result = voice_component(
        key="paraformer_voice_recorder",
        data={
            "maxSeconds": 180,
            "disabled": bool(disabled),
        },
        default={"commit": None},
        height=0,
        on_commit_change=lambda: None,
    )
    # Streamlit component values can be materialized as either an attribute
    # object or a plain dict depending on browser/device rerun timing.
    if isinstance(result, dict):
        commit = result.get("commit")
    else:
        commit = getattr(result, "commit", None)
    if isinstance(commit, dict):
        return commit
    if commit is not None:
        commit_id = getattr(commit, "id", None)
        commit_text = getattr(commit, "text", None)
        if commit_id is not None and commit_text is not None:
            return {"id": commit_id, "text": commit_text}
    return None
