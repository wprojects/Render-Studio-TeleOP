import { test } from "node:test";
import assert from "node:assert/strict";
import { matchTeleopVoicePhrase, TELEOP_VOICE_HINT } from "./teleop-voice.js";

test("teleop in-app voice maps connect/disconnect, not Hey Meta", () => {
  assert.equal(matchTeleopVoicePhrase("hey connect please"), "connect");
  assert.equal(matchTeleopVoicePhrase("Disconnect"), "disconnect");
  assert.equal(matchTeleopVoicePhrase("engage now"), "engage-hint");
  assert.equal(matchTeleopVoicePhrase("open youtube"), null);
  assert.match(TELEOP_VOICE_HINT, /Hey Meta/);
  assert.match(TELEOP_VOICE_HINT, /Connect/);
});
