from dimos.teleop.quest import policy_camera_bridge


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_policy_camera_status_maps_live_wrist_and_missing_act_views(monkeypatch):
    payloads = [
        {"left": {"live": True}, "right": {"live": True}},
        {"live": False, "reason": "ZED camera not detected"},
    ]
    monkeypatch.setattr(policy_camera_bridge, "_json", lambda _path: payloads.pop(0))
    monkeypatch.setattr(policy_camera_bridge, "_CACHE", None)

    status = policy_camera_bridge.status_payload(refresh=True)

    assert status["roles"]["wrist_left"]["live"] is True
    assert status["roles"]["wrist_right"]["live"] is True
    assert status["ready"] is False
    assert status["missing"] == ["top"]
