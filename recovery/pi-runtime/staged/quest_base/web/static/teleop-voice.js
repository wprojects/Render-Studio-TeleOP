/**
 * In-app voice for Quest teleop. Quest OS “Hey Meta” cannot target
 * arbitrary web buttons on this page or in Studio WebXR.
 */

export function speechRecognitionCtor(win = typeof window !== "undefined" ? window : globalThis) {
  return win.SpeechRecognition || win.webkitSpeechRecognition || null;
}

export function matchTeleopVoicePhrase(text) {
  const t = String(text || "")
    .toLowerCase()
    .replace(/[^\w\s+]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!t) return null;
  if (/\b(disconnect|stop vr|end session|exit vr)\b/.test(t)) return "disconnect";
  if (/\b(connect|enter vr|start vr|start teleop)\b/.test(t)) return "connect";
  if (/\b(disengage|release engage)\b/.test(t)) return "engage-hint";
  if (/\b(engage|hold x|hold a)\b/.test(t)) return "engage-hint";
  return null;
}

export const TELEOP_VOICE_HINT =
  'Quest “Hey Meta” cannot click these buttons. In-app voice: say “Connect” or “Disconnect”. Engage is still hold X + A.';
