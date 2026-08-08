from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
SIZE = 512
FRAME_COUNT = 24
DURATION_MS = 70


def load_subject(name: str, max_size: tuple[int, int]) -> Image.Image:
    image = Image.open(ROOT / name).convert("RGBA")
    alpha = image.getchannel("A")
    box = alpha.getbbox()
    if box is None:
        raise ValueError(f"No visible pixels in {name}")
    image = image.crop(box)
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    return image


def paste_center(canvas: Image.Image, sprite: Image.Image, x: int = 0, y: int = 0) -> None:
    px = (SIZE - sprite.width) // 2 + x
    py = (SIZE - sprite.height) // 2 + y
    canvas.alpha_composite(sprite, (px, py))


def sparkle(draw: ImageDraw.ImageDraw, x: int, y: int, radius: int, alpha: int) -> None:
    color = (255, 246, 130, alpha)
    draw.rectangle((x - radius, y - 2, x + radius, y + 2), fill=color)
    draw.rectangle((x - 2, y - radius, x + 2, y + radius), fill=color)
    draw.rectangle((x - 3, y - 3, x + 3, y + 3), fill=(255, 255, 255, alpha))


def gif_frame(image: Image.Image) -> Image.Image:
    """Quantize an RGBA frame while reserving palette index 0 for transparency."""
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb = Image.new("RGB", rgba.size, (0, 0, 0))
    rgb.paste(rgba, mask=alpha)
    quantized = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    source_indices = quantized.tobytes()
    alpha_bytes = alpha.tobytes()
    shifted = bytes(0 if a < 40 else min(index + 1, 255) for index, a in zip(source_indices, alpha_bytes))
    frame = Image.new("P", rgba.size)
    frame.putdata(shifted)
    palette = quantized.getpalette()[: 255 * 3]
    frame.putpalette([0, 0, 0] + palette + [0] * (768 - 3 - len(palette)))
    frame.info["transparency"] = 0
    frame.info["disposal"] = 2
    return frame


def save_gif(frames: list[Image.Image], filename: str) -> None:
    encoded = [gif_frame(frame) for frame in frames]
    encoded[0].save(
        ROOT / filename,
        save_all=True,
        append_images=encoded[1:],
        duration=DURATION_MS,
        loop=0,
        transparency=0,
        disposal=2,
        optimize=False,
    )


def make_rose() -> None:
    subject = load_subject("rose.png", (292, 330))
    frames: list[Image.Image] = []
    for i in range(FRAME_COUNT):
        phase = 2 * math.pi * i / FRAME_COUNT
        canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        angle = 5.5 * math.sin(phase)
        sprite = subject.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        paste_center(canvas, sprite, y=4 - int(5 * math.cos(phase)))
        draw = ImageDraw.Draw(canvas, "RGBA")
        pulse_a = int(255 * max(0.0, math.sin(phase)))
        pulse_b = int(255 * max(0.0, math.sin(phase + math.pi)))
        sparkle(draw, 143, 150, 15, pulse_a)
        sparkle(draw, 371, 222, 11, pulse_b)
        frames.append(canvas)
    save_gif(frames, "rose-animated.gif")


def make_music() -> None:
    subject = load_subject("music.png", (320, 300))
    frames: list[Image.Image] = []
    for i in range(FRAME_COUNT):
        phase = 2 * math.pi * i / FRAME_COUNT
        canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        bounce = -abs(int(18 * math.sin(phase))) + 8
        scale = 1.0 + 0.045 * math.sin(2 * phase)
        sprite = subject.resize(
            (max(1, int(subject.width * scale)), max(1, int(subject.height / scale))),
            Image.Resampling.LANCZOS,
        )
        angle = 3.5 * math.sin(phase)
        sprite = sprite.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        paste_center(canvas, sprite, y=bounce)
        draw = ImageDraw.Draw(canvas, "RGBA")
        wave = int((i / FRAME_COUNT) * 100)
        for offset, opacity in ((0, 190), (24, 110), (48, 50)):
            radius = 12 + ((wave + offset) % 72)
            draw.arc((256 - radius, 410 - radius // 3, 256 + radius, 410 + radius // 3), 205, 335,
                     fill=(180, 94, 255, opacity), width=5)
        frames.append(canvas)
    save_gif(frames, "tiktok-logo-animated.gif")


def make_ice_cream() -> None:
    subject = load_subject("ice-cream.png", (280, 350))
    frames: list[Image.Image] = []
    for i in range(FRAME_COUNT):
        phase = 2 * math.pi * i / FRAME_COUNT
        canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        squash = 1.0 + 0.035 * math.sin(2 * phase)
        sprite = subject.resize(
            (max(1, int(subject.width / squash)), max(1, int(subject.height * squash))),
            Image.Resampling.LANCZOS,
        )
        angle = 3.0 * math.sin(phase)
        sprite = sprite.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        paste_center(canvas, sprite, y=-6 - int(8 * math.sin(phase)))
        draw = ImageDraw.Draw(canvas, "RGBA")
        a1 = int(255 * max(0.0, math.sin(phase + 0.4)))
        a2 = int(255 * max(0.0, math.sin(phase + math.pi + 0.4)))
        sparkle(draw, 152, 182, 14, a1)
        sparkle(draw, 374, 152, 10, a2)
        frames.append(canvas)
    save_gif(frames, "ice-cream-animated.gif")


if __name__ == "__main__":
    make_rose()
    make_music()
    make_ice_cream()
    print("Created rose-animated.gif, tiktok-logo-animated.gif, ice-cream-animated.gif")
