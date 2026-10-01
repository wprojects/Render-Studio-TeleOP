// Global error handler
window.onerror = (msg, url, line, col, error) => {
    console.error(`[ERROR] ${msg} at ${url}:${line}:${col}`, error);
    document.getElementById('status').textContent = `Error: ${msg}`;
};

import { geometry_msgs, std_msgs, sensor_msgs } from "https://esm.sh/jsr/@dimos/msgs@0.1.4";
import { matchTeleopVoicePhrase, speechRecognitionCtor, TELEOP_VOICE_HINT } from "./teleop-voice.js?v=20260909-voice1";

// WebSocket and VR state
let ws = null;
let xrSession = null;
let xrRefSpace = null;
let gl = null;
let lastSendTime = 0;
const sendInterval = 1000 / 80; // ~80Hz target
const handSelectActive = new Map();
const GRIPPER_PINCH_DISTANCE_METERS = 0.04;

// Video panel state
const videoEl = document.getElementById('videoFeed');
let videoTex = null;
let quadProgram = null;
let quadVbo = null;
let quadAttribs = null;
let quadUniforms = null;
let videoReady = false;  // true after first frame loads
let videoDirty = false;  // true when a new JPEG has finished decoding
let videoAspect = 1.0;   // cached at load time — see videoEl.onload
let prevBlobUrl = null;  // revoked when the next-next blob arrives
const videoModelMatrix = new Float32Array(16);
const hudModelMatrix = new Float32Array(16);
const hudLocalMatrix = new Float32Array(16);
const headHudModelMatrix = new Float32Array(16);
const headHudLocalMatrix = new Float32Array(16);

const PANEL_POS_X = 0.0;
const PANEL_POS_Y = 1.4;   // ~eye height
const PANEL_POS_Z = -1.5;  // 1.5m in front of starting position
const PANEL_HEIGHT = 0.9;

// Collection HUD state. One copy is world-locked near the start pose; a second
// copy is head-locked every frame so CONNECTED / HOLD X+A stays in view.
let episodeStatus = null;
let episodeStatusReceivedAtMs = 0;
let hudOffline = false;
let hudCanvas = null;
let hudContext = null;
let hudTexture = null;
let hudDirty = false;
let hudElapsedSecond = -1;
let hudPlaced = false;
let lastLeftTrackMs = 0;
let lastRightTrackMs = 0;
let leftPrimaryHeld = false;
let rightPrimaryHeld = false;

const HUD_WIDTH_PX = 2048;
const HUD_HEIGHT_PX = 440;
const HUD_WIDTH_METERS = 1.7;
const HUD_HEIGHT_METERS = HUD_WIDTH_METERS * HUD_HEIGHT_PX / HUD_WIDTH_PX;
const HUD_OFFSET_Y = -0.18;
const HUD_OFFSET_Z = -0.85;
const HEAD_HUD_WIDTH_METERS = 0.92;
const HEAD_HUD_HEIGHT_METERS = HEAD_HUD_WIDTH_METERS * HUD_HEIGHT_PX / HUD_WIDTH_PX;
const HEAD_HUD_OFFSET_Y = -0.08;
const HEAD_HUD_OFFSET_Z = -0.55;

// UI elements
const statusEl = document.getElementById('status');
const connectBtn = document.getElementById('connectBtn');
const disconnectBtn = document.getElementById('disconnectBtn');
const canvas = document.getElementById('canvas');

function setStatus(msg) {
    statusEl.textContent = msg;
}

// WebSocket setup (LCM bridge)
function setupWebSocket() {
    return new Promise((resolve, reject) => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        setStatus('Connecting to server...');
        ws = new WebSocket(wsUrl);
        ws.binaryType = 'blob';

        ws.onopen = () => {
            hudOffline = false;
            hudDirty = true;
            setStatus('Server connected');
            resolve();
        };
        ws.onerror = (error) => {
            setStatus('WebSocket error');
            console.error('WebSocket error:', error);
            reject(error);
        };
        ws.onclose = () => {
            hudOffline = true;
            hudDirty = true;
            setStatus('WebSocket closed');
        };
        // Defer revoking the previous blob URL by one message — revoking
        // immediately after setting src can race with the browser's load
        // on some engines, briefly dropping naturalWidth to 0.
        ws.onmessage = (e) => {
            if (typeof e.data === 'string') {
                handleServerMessage(e.data);
                return;
            }
            if (!(e.data instanceof Blob)) return;
            const newUrl = URL.createObjectURL(e.data);
            if (prevBlobUrl) URL.revokeObjectURL(prevBlobUrl);
            prevBlobUrl = videoEl.src.startsWith('blob:') ? videoEl.src : null;
            videoEl.src = newUrl;
        };
    });
}

// Initialize WebGL
function initGL() {
    gl = canvas.getContext('webgl', {
        xrCompatible: true,
        alpha: true
    });
    if (!gl) {
        throw new Error('WebGL not supported');
    }
    gl.clearColor(0, 0, 0, 0); // Transparent background for passthrough
    initVideoPanel();
    initCollectionHud();
}

// Compile one textured-quad pipeline for the world-locked video and HUD.
function initVideoPanel() {
    const vsSrc = `
        attribute vec2 a_pos;
        attribute vec2 a_uv;
        uniform mat4 u_proj;
        uniform mat4 u_view;
        uniform mat4 u_model;
        varying vec2 v_uv;
        void main() {
            gl_Position = u_proj * u_view * u_model
                        * vec4(a_pos.x, a_pos.y, 0.0, 1.0);
            v_uv = a_uv;
        }`;
    const fsSrc = `
        precision mediump float;
        varying vec2 v_uv;
        uniform sampler2D u_tex;
        void main() {
            gl_FragColor = texture2D(u_tex, v_uv);
        }`;

    const compile = (type, src) => {
        const sh = gl.createShader(type);
        gl.shaderSource(sh, src);
        gl.compileShader(sh);
        if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
            throw new Error('Shader compile failed: ' + gl.getShaderInfoLog(sh));
        }
        return sh;
    };
    const vs = compile(gl.VERTEX_SHADER, vsSrc);
    const fs = compile(gl.FRAGMENT_SHADER, fsSrc);
    quadProgram = gl.createProgram();
    gl.attachShader(quadProgram, vs);
    gl.attachShader(quadProgram, fs);
    gl.linkProgram(quadProgram);
    if (!gl.getProgramParameter(quadProgram, gl.LINK_STATUS)) {
        throw new Error('Program link failed: ' + gl.getProgramInfoLog(quadProgram));
    }

    // Quad as TRIANGLE_STRIP: x, y, u, v. v=0 at top of quad +
    // UNPACK_FLIP_Y_WEBGL=false → image displays upright.
    const verts = new Float32Array([
        -1, -1, 0, 1,
         1, -1, 1, 1,
        -1,  1, 0, 0,
         1,  1, 1, 0,
    ]);
    quadVbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quadVbo);
    gl.bufferData(gl.ARRAY_BUFFER, verts, gl.STATIC_DRAW);

    quadAttribs = {
        pos: gl.getAttribLocation(quadProgram, 'a_pos'),
        uv:  gl.getAttribLocation(quadProgram, 'a_uv'),
    };
    quadUniforms = {
        proj:  gl.getUniformLocation(quadProgram, 'u_proj'),
        view:  gl.getUniformLocation(quadProgram, 'u_view'),
        model: gl.getUniformLocation(quadProgram, 'u_model'),
        tex:   gl.getUniformLocation(quadProgram, 'u_tex'),
    };

    videoTex = createTexture();
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);

    // Cache aspect here — naturalWidth can transiently drop to 0
    // between loads, which would collapse the panel to 1:1.
    videoEl.onload = () => {
        videoReady = true;
        videoDirty = true;
        if (videoEl.naturalHeight) {
            videoAspect = videoEl.naturalWidth / videoEl.naturalHeight;
        }
    };
}

function createTexture() {
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    return texture;
}

function uploadVideoTexture() {
    gl.bindTexture(gl.TEXTURE_2D, videoTex);
    gl.texImage2D(
        gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, videoEl
    );
}

function setModelMatrix(matrix, halfWidth, halfHeight, x, y, z) {
    matrix.fill(0);
    matrix[0] = halfWidth;
    matrix[5] = halfHeight;
    matrix[10] = 1;
    matrix[12] = x;
    matrix[13] = y;
    matrix[14] = z;
    matrix[15] = 1;
}

function multiplyMatrices(out, left, right) {
    for (let column = 0; column < 4; column++) {
        for (let row = 0; row < 4; row++) {
            let value = 0;
            for (let index = 0; index < 4; index++) {
                value += left[index * 4 + row] * right[column * 4 + index];
            }
            out[column * 4 + row] = value;
        }
    }
}

function updateVideoModelMatrix() {
    const halfH = PANEL_HEIGHT * 0.5;
    setModelMatrix(
        videoModelMatrix,
        halfH * videoAspect,
        halfH,
        PANEL_POS_X,
        PANEL_POS_Y,
        PANEL_POS_Z,
    );
}

function renderTexturedQuad(view, viewport, texture, modelMatrix, viewMatrix) {
    gl.viewport(viewport.x, viewport.y, viewport.width, viewport.height);
    gl.useProgram(quadProgram);

    gl.bindBuffer(gl.ARRAY_BUFFER, quadVbo);
    gl.enableVertexAttribArray(quadAttribs.pos);
    gl.vertexAttribPointer(quadAttribs.pos, 2, gl.FLOAT, false, 16, 0);
    gl.enableVertexAttribArray(quadAttribs.uv);
    gl.vertexAttribPointer(quadAttribs.uv,  2, gl.FLOAT, false, 16, 8);

    gl.uniformMatrix4fv(quadUniforms.proj, false, view.projectionMatrix);
    gl.uniformMatrix4fv(quadUniforms.view, false, viewMatrix);
    gl.uniformMatrix4fv(quadUniforms.model, false, modelMatrix);

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.uniform1i(quadUniforms.tex, 0);

    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
}

function renderVideoPanel(view, viewport) {
    renderTexturedQuad(
        view,
        viewport,
        videoTex,
        videoModelMatrix,
        view.transform.inverse.matrix,
    );
}

function handleServerMessage(data) {
    try {
        const message = JSON.parse(data);
        if (message.type !== 'episode_status') return;
        episodeStatus = message;
        episodeStatusReceivedAtMs = performance.now();
        hudOffline = false;
        hudDirty = true;
    } catch (error) {
        console.warn('Ignoring invalid server message', error);
    }
}

function initCollectionHud() {
    hudCanvas = document.createElement('canvas');
    hudCanvas.width = HUD_WIDTH_PX;
    hudCanvas.height = HUD_HEIGHT_PX;
    hudContext = hudCanvas.getContext('2d');

    hudTexture = createTexture();
    setModelMatrix(
        hudLocalMatrix,
        HUD_WIDTH_METERS * 0.5,
        HUD_HEIGHT_METERS * 0.5,
        0,
        HUD_OFFSET_Y,
        HUD_OFFSET_Z,
    );
    setModelMatrix(
        headHudLocalMatrix,
        HEAD_HUD_WIDTH_METERS * 0.5,
        HEAD_HUD_HEIGHT_METERS * 0.5,
        0,
        HEAD_HUD_OFFSET_Y,
        HEAD_HUD_OFFSET_Z,
    );
}

function placeCollectionHud(pose) {
    multiplyMatrices(hudModelMatrix, pose.transform.matrix, hudLocalMatrix);
    hudPlaced = true;
}

function placeHeadLockedHud(pose) {
    multiplyMatrices(headHudModelMatrix, pose.transform.matrix, headHudLocalMatrix);
}

function drawHudSection(
    context,
    x,
    width,
    label,
    value,
    color,
    dotColor = null,
) {
    if (x > 24) {
        context.fillStyle = 'rgba(178, 196, 219, 0.22)';
        context.fillRect(x, 48, 2, HUD_HEIGHT_PX - 96);
    }

    const left = x + 28;
    context.fillStyle = '#c0cfdf';
    context.font = '700 36px sans-serif';
    context.fillText(label, left, 112);

    let valueLeft = left;
    if (dotColor) {
        context.fillStyle = dotColor;
        context.beginPath();
        context.arc(left + 12, 232, 12, 0, Math.PI * 2);
        context.fill();
        valueLeft += 40;
    }
    context.fillStyle = color;
    const font = 'ui-monospace, SFMono-Regular, Menlo, monospace';
    context.font = `700 62px ${font}`;
    const availableWidth = x + width - valueLeft - 24;
    const measuredWidth = context.measureText(value).width;
    const fontSize = Math.min(62, 62 * availableWidth / measuredWidth);
    context.font = `700 ${fontSize}px ${font}`;
    context.fillText(value, valueLeft, 250);
}

function collectionElapsedSeconds() {
    if (!episodeStatus || episodeStatus.state !== 'recording') return 0;
    const sinceUpdate = (performance.now() - episodeStatusReceivedAtMs) / 1000;
    return Math.max(0, Math.floor(episodeStatus.elapsed_s + sinceUpdate));
}

function formatElapsed(seconds) {
    const minutes = Math.floor(seconds / 60).toString().padStart(2, '0');
    const remainder = (seconds % 60).toString().padStart(2, '0');
    return `${minutes}:${remainder}`;
}

function trackingLabel(lastMs, primaryHeld) {
    if (primaryHeld) return 'ENGAGED';
    return lastMs && performance.now() - lastMs < 500 ? 'TRACKING' : '---';
}

function engageLabel() {
    if (leftPrimaryHeld && rightPrimaryHeld) return 'ENGAGED';
    if (leftPrimaryHeld) return 'LEFT X';
    if (rightPrimaryHeld) return 'RIGHT A';
    return 'HOLD X + A';
}

let lastHudLeft = '';
let lastHudRight = '';
let lastHudEngage = '';

function updateHudTexture() {
    if (!hudContext) return;
    const elapsed = collectionElapsedSeconds();
    const left = trackingLabel(lastLeftTrackMs, leftPrimaryHeld);
    const right = trackingLabel(lastRightTrackMs, rightPrimaryHeld);
    const engage = engageLabel();
    if (
        !hudDirty &&
        elapsed === hudElapsedSecond &&
        left === lastHudLeft &&
        right === lastHudRight &&
        engage === lastHudEngage
    ) {
        return;
    }
    hudDirty = false;
    hudElapsedSecond = elapsed;
    lastHudLeft = left;
    lastHudRight = right;
    lastHudEngage = engage;

    const engageColor = (leftPrimaryHeld || rightPrimaryHeld) ? '#7ee8ff' : '#8de2bd';
    const sections = episodeStatus ? [
        [400, 'STATE', hudOffline ? 'OFFLINE' : episodeStatus.state === 'recording' ? 'RECORDING' : 'READY', '#f4f7fb', hudOffline ? '#f6b94d' : episodeStatus.state === 'recording' ? '#ff6b6b' : '#63d6a3'],
        [220, 'TAKE', String(episodeStatus.episodes_saved + episodeStatus.episodes_discarded + 1).padStart(3, '0'), '#f4f7fb'],
        [280, 'ELAPSED', hudOffline ? '--:--' : formatElapsed(elapsed), '#f4f7fb'],
        [260, 'SAVED', String(episodeStatus.episodes_saved).padStart(3, '0'), '#8de2bd'],
        [320, 'DISCARDED', String(episodeStatus.episodes_discarded).padStart(3, '0'), '#f7c66d'],
        [568, 'LAST ACTION', episodeStatus.last_event === 'init' ? 'NONE' : episodeStatus.last_event.toUpperCase(), '#f4f7fb'],
    ] : [
        [340, 'STATE', hudOffline ? 'OFFLINE' : 'CONNECTED', '#f4f7fb', hudOffline ? '#f6b94d' : '#63d6a3'],
        [280, 'LEFT', left, left === 'ENGAGED' ? '#7ee8ff' : '#f4f7fb'],
        [280, 'RIGHT', right, right === 'ENGAGED' ? '#7ee8ff' : '#f4f7fb'],
        [420, 'ENGAGE', engage, engageColor],
        [728, 'ROBOT', 'NONE — RERUN ONLY', '#f7c66d'],
    ];

    hudContext.clearRect(0, 0, HUD_WIDTH_PX, HUD_HEIGHT_PX);
    hudContext.beginPath();
    hudContext.roundRect(8, 8, HUD_WIDTH_PX - 16, HUD_HEIGHT_PX - 16, 40);
    hudContext.fillStyle = 'rgba(4, 12, 28, 0.94)';
    hudContext.fill();
    hudContext.strokeStyle = 'rgba(80, 220, 255, 0.95)';
    hudContext.lineWidth = 8;
    hudContext.stroke();

    let x = 0;
    for (const [width, label, value, color, dotColor] of sections) {
        drawHudSection(hudContext, x, width, label, value, color, dotColor);
        x += width;
    }

    if (!episodeStatus) {
        hudContext.fillStyle = '#7ee8ff';
        hudContext.font = '700 28px sans-serif';
        hudContext.fillText(
            'Tracking + engage only. No robot until you run teleop-quest-xarm7 / piper.',
            36,
            HUD_HEIGHT_PX - 28,
        );
    }

    gl.bindTexture(gl.TEXTURE_2D, hudTexture);
    gl.texImage2D(
        gl.TEXTURE_2D,
        0,
        gl.RGBA,
        gl.RGBA,
        gl.UNSIGNED_BYTE,
        hudCanvas,
    );
}

function renderHudQuad(view, viewport, modelMatrix) {
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    renderTexturedQuad(
        view,
        viewport,
        hudTexture,
        modelMatrix,
        view.transform.inverse.matrix,
    );
    gl.disable(gl.BLEND);
}

function renderCollectionHud(view, viewport) {
    if (!hudPlaced) return;
    renderHudQuad(view, viewport, hudModelMatrix);
}

function renderHeadLockedHud(view, viewport) {
    renderHudQuad(view, viewport, headHudModelMatrix);
}

function sendPose(handedness, pose) {
    const pos = pose.transform.position;
    const rot = pose.transform.orientation;
    const nowMs = Date.now();
    const poseStamped = new geometry_msgs.PoseStamped({
        header: new std_msgs.Header({
            stamp: new std_msgs.Time({ sec: Math.floor(nowMs / 1000), nsec: (nowMs % 1000) * 1_000_000 }),
            frame_id: handedness
        }),
        pose: new geometry_msgs.Pose({
            position: new geometry_msgs.Point({ x: pos.x, y: pos.y, z: pos.z }),
            orientation: new geometry_msgs.Quaternion({ x: rot.x, y: rot.y, z: rot.z, w: rot.w })
        })
    });
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(poseStamped.encode());
    }
}

function sendJoy(handedness, axes, buttons) {
    const nowMs = Date.now();
    const joyMsg = new sensor_msgs.Joy({
        header: new std_msgs.Header({
            stamp: new std_msgs.Time({ sec: Math.floor(nowMs / 1000), nsec: (nowMs % 1000) * 1_000_000 }),
            frame_id: handedness
        }),
        axes_length: axes.length,
        buttons_length: buttons.length,
        axes: axes,
        buttons: buttons
    });
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(joyMsg.encode());
    }
}

function isButtonDown(button) {
    return !!(button && (button.pressed || button.value > 0.5));
}

// DIMOS Joy buttons: [trigger, grip, touchpad, thumbstick, X/A, Y/B, menu].
// Quest Browser does not always put X/A at raw index 4 — copy-by-index
// left Python's primary (buttons[4]) stuck at 0 while X/A was at 2 or 3.
function mapDimosController(gamepad) {
    const raw = gamepad.buttons || [];
    const n = raw.length;
    const xr = gamepad.mapping === 'xr-standard';
    const stickX = (xr ? gamepad.axes[2] : gamepad.axes[0]) ?? 0.0;
    const stickY = (xr ? gamepad.axes[3] : gamepad.axes[1]) ?? 0.0;

    let touchpad = false;
    let thumbstick = false;
    let primary = false;
    let secondary = false;
    let menu = false;

    if (xr && n >= 6) {
        touchpad = isButtonDown(raw[2]);
        thumbstick = isButtonDown(raw[3]);
        primary = isButtonDown(raw[4]);
        secondary = isButtonDown(raw[5]);
        menu = isButtonDown(raw[6]);
    } else if (xr && n === 5) {
        // Touchpad placeholder omitted: stick, X/A, Y/B shift left by one.
        thumbstick = isButtonDown(raw[2]);
        primary = isButtonDown(raw[3]);
        secondary = isButtonDown(raw[4]);
    } else {
        // Oculus/Meta native: 0 trigger, 1 grip, 2 X/A, 3 Y/B, 4 stick, 5 menu.
        primary = isButtonDown(raw[2]);
        secondary = isButtonDown(raw[3]);
        thumbstick = isButtonDown(raw[4]);
        menu = isButtonDown(raw[5]) || isButtonDown(raw[6]);
    }

    if (!primary) {
        primary = isButtonDown(raw[4]) || (!xr && isButtonDown(raw[2]));
    }

    return {
        primary,
        axes: [
            stickX,
            stickY,
            raw[0]?.value ?? 0.0,
            raw[1]?.value ?? 0.0,
        ],
        buttons: [
            isButtonDown(raw[0]) ? 1 : 0,
            isButtonDown(raw[1]) ? 1 : 0,
            touchpad ? 1 : 0,
            thumbstick ? 1 : 0,
            primary ? 1 : 0,
            secondary ? 1 : 0,
            menu ? 1 : 0,
        ],
    };
}

// Send raw controller and wrist tracking data (no processing - done in Python)
function processTracking(frame) {
    const now = performance.now();
    const shouldSend = now - lastSendTime >= sendInterval;
    if (shouldSend) lastSendTime = now;

    let sawLeftPrimary = false;
    let sawRightPrimary = false;

    for (const inputSource of frame.session.inputSources) {
        const handedness = inputSource.handedness;
        if (handedness !== 'left' && handedness !== 'right') continue;

        const gamepad = inputSource.gamepad;
        const looksLikeController = !!(gamepad && gamepad.buttons && gamepad.buttons.length >= 4);
        const hand = inputSource.hand;

        // Prefer controller gamepad over hand skeleton. Quest can attach
        // both; the old path took `hand` first and never read X/A.
        if (hand && !looksLikeController) {
            const wristPose = frame.getJointPose(hand.get('wrist'), xrRefSpace);
            const thumbTipPose = frame.getJointPose(hand.get('thumb-tip'), xrRefSpace);
            const middleTipPose = frame.getJointPose(hand.get('middle-finger-tip'), xrRefSpace);
            if (!wristPose || !thumbTipPose || !middleTipPose) continue;

            const thumb = thumbTipPose.transform.position;
            const middle = middleTipPose.transform.position;
            const gripperPinched = Math.hypot(
                thumb.x - middle.x,
                thumb.y - middle.y,
                thumb.z - middle.z,
            ) < GRIPPER_PINCH_DISTANCE_METERS;

            const primary = !!handSelectActive.get(handedness);
            if (handedness === 'left') {
                lastLeftTrackMs = now;
                sawLeftPrimary = sawLeftPrimary || primary;
            } else {
                lastRightTrackMs = now;
                sawRightPrimary = sawRightPrimary || primary;
            }
            if (shouldSend) {
                sendPose(handedness, wristPose);
                sendJoy(
                    handedness,
                    [0, 0, gripperPinched ? 1 : 0, 0],
                    [0, 0, 0, 0, primary ? 1 : 0, 0, 0],
                );
            }
            continue;
        }

        const trackingSpace = inputSource.gripSpace || inputSource.targetRaySpace;
        if (!trackingSpace) continue;
        const pose = frame.getPose(trackingSpace, xrRefSpace);
        if (!pose) continue;

        if (handedness === 'left') lastLeftTrackMs = now;
        else lastRightTrackMs = now;

        if (gamepad) {
            const mapped = mapDimosController(gamepad);
            if (handedness === 'left') sawLeftPrimary = sawLeftPrimary || mapped.primary;
            else sawRightPrimary = sawRightPrimary || mapped.primary;
            if (shouldSend) {
                sendPose(handedness, pose);
                sendJoy(handedness, mapped.axes, mapped.buttons);
            }
        } else if (shouldSend) {
            sendPose(handedness, pose);
        }
    }

    leftPrimaryHeld = sawLeftPrimary;
    rightPrimaryHeld = sawRightPrimary;
}

// VR render loop
function onXRFrame(_time, frame) {
    if (!xrSession) return;
    xrSession.requestAnimationFrame(onXRFrame);
    // Process and send tracking data
    processTracking(frame);

    const glLayer = xrSession.renderState.baseLayer;
    gl.bindFramebuffer(gl.FRAMEBUFFER, glLayer.framebuffer);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

    // Keep rendering the existing texture between loads to avoid blinking.
    if (videoReady && videoDirty && videoEl.naturalWidth) {
        uploadVideoTexture();
        videoDirty = false;
    }
    if (videoReady) updateVideoModelMatrix();
    updateHudTexture();
    const pose = frame.getViewerPose(xrRefSpace);
    if (pose) {
        if (!hudPlaced) placeCollectionHud(pose);
        placeHeadLockedHud(pose);
        for (const view of pose.views) {
            const viewport = glLayer.getViewport(view);
            if (videoReady) renderVideoPanel(view, viewport);
            renderCollectionHud(view, viewport);
            renderHeadLockedHud(view, viewport);
        }
    }
}

// Start VR session with passthrough
async function startVR() {
    try {
        setStatus('Initializing WebGL...');
        initGL();
        setStatus('Requesting VR session...');

        // Try immersive-ar with a DOM overlay so the HTML panel stays visible
        // in passthrough. Fall back if the headset rejects overlay or AR.
        const overlayRoot = document.getElementById('ui');
        const sessionAttempts = [
            {
                mode: 'immersive-ar',
                init: {
                    requiredFeatures: ['local-floor'],
                    optionalFeatures: ['hand-tracking', 'dom-overlay'],
                    domOverlay: { root: overlayRoot },
                },
            },
            {
                mode: 'immersive-ar',
                init: {
                    requiredFeatures: ['local-floor'],
                    optionalFeatures: ['hand-tracking'],
                },
            },
            {
                mode: 'immersive-vr',
                init: {
                    requiredFeatures: ['local-floor'],
                    optionalFeatures: ['hand-tracking'],
                },
            },
        ];
        let session = null;
        let lastXrError = null;
        for (const attempt of sessionAttempts) {
            try {
                session = await navigator.xr.requestSession(attempt.mode, attempt.init);
                console.log(`Started ${attempt.mode} session`);
                break;
            } catch (xrError) {
                lastXrError = xrError;
            }
        }
        if (!session) {
            throw lastXrError || new Error('WebXR session was not created');
        }

        xrSession = session;
        hudPlaced = false;
        document.body.classList.add('xr-active');

        // Setup WebGL layer
        const glLayer = new XRWebGLLayer(session, gl);
        await session.updateRenderState({
            baseLayer: glLayer
        });

        // Get reference space
        xrRefSpace = await session.requestReferenceSpace('local-floor');

        setStatus('VR active — HUD is locked in front of your eyes');

        // Session event handlers
        session.addEventListener('end', () => {
            document.body.classList.remove('xr-active');
            setStatus('VR session ended');
            handSelectActive.clear();
            hudPlaced = false;
            lastLeftTrackMs = 0;
            lastRightTrackMs = 0;
            leftPrimaryHeld = false;
            rightPrimaryHeld = false;
            xrSession = null;
            window.disconnect();
        });

        session.addEventListener('selectstart', (event) => {
            const { handedness, hand } = event.inputSource;
            if (hand && (handedness === 'left' || handedness === 'right')) {
                handSelectActive.set(handedness, true);
            }
        });
        session.addEventListener('selectend', (event) => {
            const { handedness, hand } = event.inputSource;
            if (hand && (handedness === 'left' || handedness === 'right')) {
                handSelectActive.set(handedness, false);
            }
        });

        // Start render loop
        session.requestAnimationFrame(onXRFrame);

    } catch (error) {
        setStatus('VR failed: ' + error.message);
        console.error('VR session error:', error);
        throw error;
    }
}

// Connect button handler
window.connect = async function() {
    try {
        connectBtn.disabled = true;

        // Check WebXR support
        if (!navigator.xr) {
            throw new Error('WebXR not supported. Use Quest 3 browser.');
        }

        // Setup WebSocket
        await setupWebSocket();

        // Start VR
        await startVR();

        // Update UI
        connectBtn.classList.add('hidden');
        disconnectBtn.classList.remove('hidden');

    } catch (error) {
        setStatus('Connection failed');
        console.error('Connection error:', error);
        connectBtn.disabled = false;
    }
};

// Disconnect button handler
window.disconnect = async function() {
    setStatus('Disconnecting...');

    if (xrSession) {
        await xrSession.end().catch(console.error);
        xrSession = null;
    }

    if (ws) {
        ws.close();
        ws = null;
    }

    // Update UI
    connectBtn.classList.remove('hidden');
    connectBtn.disabled = false;
    disconnectBtn.classList.add('hidden');
    setStatus('Disconnected');
};

// Check WebXR availability on load
window.addEventListener('load', async () => {
    if (!navigator.xr) {
        setStatus('WebXR not available');
        connectBtn.disabled = true;
        return;
    }

    try {
        // Check for AR (passthrough) or VR support
        const arSupported = await navigator.xr.isSessionSupported('immersive-ar').catch(() => false);
        const vrSupported = await navigator.xr.isSessionSupported('immersive-vr').catch(() => false);

        if (!arSupported && !vrSupported) {
            setStatus('VR/AR not supported');
            connectBtn.disabled = true;
        }
    } catch (error) {
        console.error('WebXR check failed:', error);
    }
});

const voiceBtn = document.getElementById('voiceBtn');
const voiceHintEl = document.getElementById('voiceHint');
if (voiceHintEl) voiceHintEl.textContent = TELEOP_VOICE_HINT;

let teleopVoiceRec = null;

function applyTeleopVoiceAction(action) {
    if (action === 'connect') {
        setStatus('Voice: Connect');
        window.connect?.();
        return;
    }
    if (action === 'disconnect') {
        setStatus('Voice: Disconnect');
        window.disconnect?.();
        return;
    }
    if (action === 'engage-hint') {
        setStatus('Engage is hold X + A — voice cannot press Quest face buttons');
    }
}

function stopTeleopVoice() {
    const rec = teleopVoiceRec;
    teleopVoiceRec = null;
    if (rec) {
        try { rec.onresult = null; rec.onerror = null; rec.onend = null; } catch { /* ignore */ }
        try { rec.stop(); } catch { /* ignore */ }
        try { rec.abort(); } catch { /* ignore */ }
    }
    voiceBtn?.setAttribute('aria-pressed', 'false');
    if (voiceBtn) voiceBtn.textContent = 'Listen';
}

function startTeleopVoice() {
    const SpeechRecognition = speechRecognitionCtor();
    if (!SpeechRecognition) {
        setStatus('In-app voice is not supported in this browser');
        return;
    }
    stopTeleopVoice();
    const rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = false;
    try { rec.lang = navigator.language || 'en-US'; } catch { /* ignore */ }
    rec.onresult = (event) => {
        const last = event.results[event.results.length - 1];
        const text = last?.[0]?.transcript || '';
        if (!last?.isFinal) return;
        applyTeleopVoiceAction(matchTeleopVoicePhrase(text));
    };
    rec.onerror = (ev) => {
        setStatus(`Voice: ${ev?.error || 'error'}`);
        stopTeleopVoice();
    };
    rec.onend = () => {
        if (teleopVoiceRec === rec) stopTeleopVoice();
    };
    teleopVoiceRec = rec;
    voiceBtn?.setAttribute('aria-pressed', 'true');
    if (voiceBtn) voiceBtn.textContent = 'Listening…';
    try {
        rec.start();
        setStatus('Listening — say Connect or Disconnect');
    } catch (err) {
        setStatus('Voice failed: ' + (err?.message || err));
        stopTeleopVoice();
    }
}

voiceBtn?.addEventListener('click', () => {
    if (teleopVoiceRec) stopTeleopVoice();
    else startTeleopVoice();
});
