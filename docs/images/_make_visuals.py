#!/usr/bin/env python3
"""Generate compact instructional diagrams for the TeleOP README."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
BG = (10, 16, 32)
CARD = (18, 28, 52)
CARD2 = (24, 40, 72)
CYAN = (62, 200, 232)
WHITE = (244, 247, 251)
MUTED = (154, 168, 184)
ORANGE = (232, 122, 62)
GREEN = (72, 201, 138)
YELLOW = (247, 198, 109)
RED = (232, 90, 90)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def rounded(draw: ImageDraw.ImageDraw, box, fill, radius=18):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def center_text(draw, xy, text, fnt, fill=WHITE):
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=fnt)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x - w / 2, y - h / 2), text, font=fnt, fill=fill)


def wrap_center(draw, xy, text, fnt, fill=WHITE, width=220):
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=fnt) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    x, y = xy
    line_h = fnt.size + 4
    total = len(lines) * line_h
    start = y - total / 2
    for i, line in enumerate(lines):
        center_text(draw, (x, start + i * line_h + line_h / 2), line, fnt, fill)


def arrow(draw, start, end, fill=CYAN):
    draw.line([start, end], fill=fill, width=4)
    x1, y1 = start
    x2, y2 = end
    if abs(x2 - x1) >= abs(y2 - y1):
        direction = 1 if x2 > x1 else -1
        draw.polygon(
            [(x2, y2), (x2 - 12 * direction, y2 - 8), (x2 - 12 * direction, y2 + 8)],
            fill=fill,
        )
    else:
        direction = 1 if y2 > y1 else -1
        draw.polygon(
            [(x2, y2), (x2 - 8, y2 - 12 * direction), (x2 + 8, y2 - 12 * direction)],
            fill=fill,
        )


def make_architecture() -> Image.Image:
    img = Image.new("RGB", (1280, 720), BG)
    d = ImageDraw.Draw(img)
    title = font(32, True)
    body = font(18)
    small = font(15)
    d.text((48, 28), "Render Studio TeleOP  ·  how the pieces connect", font=title, fill=WHITE)
    d.text(
        (48, 72),
        "Quest talks HTTPS to the Pi. Render Studio uses the same LAN IP. Arms speak CAN-FD.",
        font=small,
        fill=MUTED,
    )

    boxes = [
        (48, 180, 280, 430, "Meta Quest 3", "Quest Browser\nhttps://PI_IP:8443/teleop\naccept cert once\nthen Connect"),
        (360, 140, 760, 470, "Raspberry Pi + DimOS", "HTTPS :8443  Quest teleop\nHTTP  :8450  Connect API /trust\nHTTP  :8095  Viser 3D\nsystemd: dimos-teleop-quest-openarm"),
        (860, 120, 1232, 300, "OpenArm (Peak CAN-FD)", "can1 = LEFT arm\ncan0 = RIGHT arm\nCAN-FD 1M / 5M\nnever classic 1M setup"),
        (860, 340, 1232, 500, "Render Studio VR", "Add the Pi LAN IP in\nrobotics configuration\nview + control the robot"),
        (360, 500, 760, 660, "Laptop (optional)", "http://PI_IP:8095\nViser 3D viewer"),
    ]
    for x1, y1, x2, y2, heading, extra in boxes:
        rounded(d, (x1, y1, x2, y2), CARD)
        d.text((x1 + 22, y1 + 18), heading, font=font(20, True), fill=CYAN)
        for i, line in enumerate(extra.split("\n")):
            d.text((x1 + 22, y1 + 62 + i * 28), line, font=body, fill=WHITE)

    arrow(d, (280, 300), (360, 300))
    arrow(d, (760, 220), (860, 220))
    arrow(d, (760, 400), (860, 400))
    arrow(d, (560, 470), (560, 500))
    return img


def make_setup_flow() -> Image.Image:
    img = Image.new("RGB", (1280, 520), BG)
    d = ImageDraw.Draw(img)
    d.text((48, 24), "Link a robot to Render Studio VR", font=font(30, True), fill=WHITE)
    d.text(
        (48, 68),
        "Six steps. Official Render IP steps: https://render3d.app/getting-started.html#robotics-configuration",
        font=font(16),
        fill=MUTED,
    )
    steps = [
        "1. Clone this repo",
        "2. Copy .env.example\nto .env",
        "3. Start DimOS\nteleop-quest-openarm",
        "4. Find Pi LAN IP\nhostname -I",
        "5. Add IP on Render\nrobotics config",
        "6. Quest Browser\n:8443/teleop",
    ]
    gap = 20
    w = 180
    y1, y2 = 130, 430
    for i, text in enumerate(steps):
        x1 = 40 + i * (w + gap)
        x2 = x1 + w
        rounded(d, (x1, y1, x2, y2), CARD)
        circle = (x1 + w / 2, y1 + 46)
        d.ellipse((circle[0] - 22, circle[1] - 22, circle[0] + 22, circle[1] + 22), fill=CYAN)
        center_text(d, circle, str(i + 1), font(20, True), BG)
        wrap_center(d, (x1 + w / 2, 300), text.split(". ", 1)[1], font(17, True), WHITE, width=150)
        if i < len(steps) - 1:
            arrow(d, (x2 + 2, 280), (x2 + gap - 4, 280))
    return img


def make_controls() -> Image.Image:
    img = Image.new("RGB", (1280, 640), BG)
    d = ImageDraw.Draw(img)
    d.text((48, 24), "Quest gamepad  ·  OpenArm teleop", font=font(30, True), fill=WHITE)
    d.text(
        (48, 68),
        "Y tap = follow or pause-hold. Hold Y ~1s = home + teleop off. Triggers pinch from rest 0.5.",
        font=font(16),
        fill=MUTED,
    )

    def controller(x, title, buttons):
        rounded(d, (x, 130, x + 560, 580), CARD)
        d.text((x + 28, 150), title, font=font(22, True), fill=CYAN)
        d.rounded_rectangle((x + 80, 210, x + 480, 430), radius=90, fill=CARD2)
        d.ellipse((x + 200, 270, x + 360, 390), outline=CYAN, width=3)
        for label, desc, by in buttons:
            d.ellipse((x + 40, by, x + 72, by + 32), fill=ORANGE)
            d.text((x + 86, by + 4), f"{label}  {desc}", font=font(18), fill=WHITE)

    controller(
        48,
        "LEFT controller",
        [
            ("Y", "tap: arm follow / pause-hold", 460),
            ("Y", "hold ~1s: slow-home, teleop OFF", 500),
            ("X", "emote picker", 540),
        ],
    )
    controller(
        672,
        "RIGHT controller",
        [
            ("A", "record / save a take", 460),
            ("B", "discard while recording", 500),
            ("LT/RT", "pinch grippers (rest = 0.5)", 540),
        ],
    )
    return img


def make_ip() -> Image.Image:
    img = Image.new("RGB", (1280, 560), BG)
    d = ImageDraw.Draw(img)
    d.text((48, 24), "Find the Pi LAN IP, then add it on Render", font=font(30, True), fill=WHITE)
    d.text(
        (48, 68),
        "Example IP only. Use YOUR address. Source of truth: render3d.app/getting-started.html#robotics-configuration",
        font=font(16),
        fill=MUTED,
    )
    rounded(d, (48, 130, 620, 500), CARD)
    d.text((72, 154), "On the Raspberry Pi", font=font(22, True), fill=CYAN)
    d.rounded_rectangle((72, 210, 596, 430), radius=12, fill=(8, 12, 22))
    d.text((92, 230), "$ hostname -I | awk '{print $1}'", font=font(20), fill=GREEN)
    d.text((92, 270), "192.168.1.100", font=font(28, True), fill=WHITE)
    d.text((92, 320), "# also:  hostname -I", font=font(16), fill=MUTED)
    d.text((92, 350), "# also:  ip -4 addr", font=font(16), fill=MUTED)
    d.text((92, 390), "Labeled EXAMPLE — not a secret, not your IP.", font=font(15), fill=YELLOW)

    rounded(d, (660, 130, 1232, 500), CARD)
    d.text((684, 154), "On Render Studio (generic)", font=font(22, True), fill=CYAN)
    d.text((684, 210), "Robotics configuration", font=font(18, True), fill=WHITE)
    d.text((684, 250), "Paste the Pi LAN IP so VR Studio can", font=font(17), fill=WHITE)
    d.text((684, 278), "view and control the robot.", font=font(17), fill=WHITE)
    d.rounded_rectangle((684, 330, 1208, 390), radius=10, fill=(8, 12, 22))
    d.text((704, 348), "Pi / robot IP   192.168.1.100   [example]", font=font(18), fill=WHITE)
    d.rounded_rectangle((684, 414, 980, 470), radius=10, fill=CYAN)
    center_text(d, (832, 442), "Save on Render", font(18, True), BG)
    d.text((684, 478), "Not a screenshot of a logged-in account.", font=font(14), fill=MUTED)
    arrow(d, (620, 300), (660, 300))
    return img


def make_hud() -> Image.Image:
    img = Image.new("RGB", (1280, 280), BG)
    d = ImageDraw.Draw(img)
    d.text((48, 18), "In-visor HUD (Quest)  ·  grip the panel to move it", font=font(24, True), fill=WHITE)
    rounded(d, (40, 70, 1240, 250), (16, 24, 40))
    chips = [
        ("TELEOP", "OFF", RED),
        ("STATE", "READY", GREEN),
        ("TAKE", "001", WHITE),
        ("ELAPSED", "00:00", WHITE),
        ("SAVED", "000", CYAN),
        ("DISCARDED", "000", YELLOW),
        ("LAST ACTION", "NONE", WHITE),
    ]
    x = 60
    for label, value, color in chips:
        rounded(d, (x, 92, x + 160, 188), CARD2, radius=12)
        d.text((x + 14, 104), label, font=font(12, True), fill=MUTED)
        d.text((x + 14, 136), value, font=font(22, True), fill=color)
        x += 170
    d.text(
        (60, 206),
        "tap Y pause   ·   hold Y home   ·   A record   ·   B discard   ·   X emotes   ·   pinch triggers close",
        font=font(16),
        fill=MUTED,
    )
    return img


def make_gif(frames: list[Image.Image]) -> None:
    resized = [im.resize((960, 390), Image.Resampling.LANCZOS) for im in frames]
    resized[0].save(
        OUT / "setup-flow.gif",
        save_all=True,
        append_images=resized[1:],
        duration=1400,
        loop=0,
        optimize=True,
    )


def main() -> None:
    arch = make_architecture()
    flow = make_setup_flow()
    controls = make_controls()
    ip = make_ip()
    hud = make_hud()
    arch.save(OUT / "architecture.png", optimize=True)
    flow.save(OUT / "setup-flow.png", optimize=True)
    controls.save(OUT / "quest-controls.png", optimize=True)
    ip.save(OUT / "find-lan-ip.png", optimize=True)
    hud.save(OUT / "hud.png", optimize=True)
    make_gif([flow, ip, controls])
    print("wrote", list(OUT.glob("*.png")) + list(OUT.glob("*.gif")))


if __name__ == "__main__":
    main()
