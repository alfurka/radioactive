#!/usr/bin/env python3
"""Build GNOME/KDE scalable (SVG) cursors from the original Xcursor artwork.

The static cursors are vectorised from the largest bitmap in each Xcursor file
(96px): the image is upscaled with smooth interpolation, split into its flat
colours, and each colour is traced with potrace. The result is a faithful,
resolution-independent copy of the original pixel art. Xcursor files remain the
source of truth for names, hotspots and timing.

Animated cursors (``progress``, ``wait``) are traced frame by frame, so the
SVGs animate exactly like the originals.

GNOME shows ``wait`` (not ``progress``) while an application is starting, so in
the SVG set ``wait`` is an alias of ``progress``: the arrow stays and a small
radioactive symbol spins beside it. Set WAIT_USES_PROGRESS = False to keep the
original big spinning disc for ``wait``.

Requires: Pillow, numpy and the ``potrace`` command line tool.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


IMAGE_CHUNK_TYPE = 0xFFFD0002
TRACE_SIZE = 96  # Xcursor image size that gets traced
UPSCALE = 8  # smooth upscaling factor before tracing
ALPHA_THRESHOLD = 120  # alpha (0-255) of the visible edge; below it is drop shadow
NOMINAL_SIZE = 24  # hotspots in the metadata are given at this size
CANVAS = TRACE_SIZE  # SVG user units; 96 units == NOMINAL_SIZE pixels


WAIT_USES_PROGRESS = True
DEFAULT_DELAY = 60  # ms, used when an animated Xcursor frame has no delay

SHADOW = (
    '<filter id="shadow" x="-20%" y="-20%" width="150%" height="150%" '
    'color-interpolation-filters="sRGB">'
    '<feDropShadow dx="2" dy="3" stdDeviation="3" flood-color="#000" flood-opacity="0.35"/>'
    "</filter>"
)


# --------------------------------------------------------------------------
# Xcursor reading
# --------------------------------------------------------------------------


def read_xcursor_images(path: Path) -> list[dict]:
    data = path.read_bytes()
    if len(data) < 16 or data[:4] != b"Xcur":
        raise ValueError(f"not an Xcursor file: {path}")

    header_size, _version, toc_count = struct.unpack_from("<III", data, 4)
    if header_size < 16 or header_size + toc_count * 12 > len(data):
        raise ValueError(f"invalid Xcursor table of contents: {path}")

    images: list[dict] = []
    for index in range(toc_count):
        toc_offset = header_size + index * 12
        chunk_type, _subtype, chunk_offset = struct.unpack_from("<III", data, toc_offset)
        if chunk_type != IMAGE_CHUNK_TYPE:
            continue
        if chunk_offset + 36 > len(data):
            raise ValueError(f"truncated Xcursor image header: {path}")

        (
            chunk_header_size,
            actual_type,
            nominal_size,
            _chunk_version,
            width,
            height,
            hotspot_x,
            hotspot_y,
            delay,
        ) = struct.unpack_from("<9I", data, chunk_offset)
        if chunk_header_size < 36 or actual_type != IMAGE_CHUNK_TYPE:
            raise ValueError(f"invalid Xcursor image chunk: {path}")
        if width == 0 or height == 0 or hotspot_x >= width or hotspot_y >= height:
            raise ValueError(f"invalid Xcursor image dimensions or hotspot: {path}")
        start = chunk_offset + chunk_header_size
        pixels = data[start : start + width * height * 4]
        if len(pixels) != width * height * 4:
            raise ValueError(f"truncated Xcursor pixel data: {path}")
        images.append(
            {
                "size": nominal_size,
                "width": width,
                "height": height,
                "hotspot_x": hotspot_x,
                "hotspot_y": hotspot_y,
                "delay": delay,
                "pixels": pixels,
            }
        )

    if not images:
        raise ValueError(f"no image chunks found: {path}")
    return images


def image_array(image: dict) -> np.ndarray:
    pic = Image.frombuffer(
        "RGBA", (image["width"], image["height"]), image["pixels"], "raw", "BGRA", 0, 1
    )
    return np.array(pic)


# --------------------------------------------------------------------------
# Tracing
# --------------------------------------------------------------------------


def hex_color(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(int(v) for v in rgb))


def flat_palette(rgba: np.ndarray) -> np.ndarray:
    """Dominant flat colours of the artwork, darkest first."""
    opaque = rgba[rgba[..., 3] == 255][:, :3].astype(np.int32)
    colors, counts = np.unique(opaque, axis=0, return_counts=True)
    palette: list[np.ndarray] = [np.zeros(3, dtype=np.int32)]  # ink is always present
    for index in np.argsort(-counts):
        if counts[index] < 40:
            break
        color = colors[index]
        if all(np.linalg.norm(color - known) >= 60 for known in palette):
            palette.append(color)
    palette.sort(key=lambda c: int(c.sum()))
    return np.array(palette)


def upscale(channel: np.ndarray) -> np.ndarray:
    height, width = channel.shape
    image = Image.fromarray(channel.astype(np.float32), mode="F")
    return np.array(image.resize((width * UPSCALE, height * UPSCALE), Image.BICUBIC))


def potrace_path(mask: np.ndarray) -> str:
    """Trace a boolean mask and return SVG path data in CANVAS units."""
    if not mask.any():
        return ""
    height, width = mask.shape
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "mask.pbm"
        target = Path(tmp) / "mask.svg"
        source.write_bytes(
            f"P4\n{width} {height}\n".encode() + np.packbits(mask, axis=1).tobytes()
        )
        subprocess.run(
            ["potrace", "-b", "svg", "-t", "10", "-a", "1.0", "-O", "0.6", "-u", "10",
             "-o", str(target), str(source)],
            check=True,
        )
        svg = target.read_text()

    scale_match = re.search(r"scale\(([-\d.]+),([-\d.]+)\)", svg)
    sx, sy = float(scale_match.group(1)), float(scale_match.group(2))
    view_height = float(re.search(r'viewBox="[\d.]+ [\d.]+ [\d.]+ ([\d.]+)"', svg).group(1))
    path_data = " ".join(re.findall(r'<path d="([^"]*)"', svg))
    factor = CANVAS / (width)  # traced pixels -> canvas units

    def tx(x: float) -> float:
        return x * sx * factor

    def ty(y: float) -> float:
        return (view_height + y * sy) * factor

    def fmt(value: float) -> str:
        return f"{value:.2f}".rstrip("0").rstrip(".")

    tokens = re.findall(r"[MmLlCcZz]|-?\d+(?:\.\d+)?", path_data)
    out: list[str] = []
    cx = cy = start_x = start_y = 0.0
    command = ""
    i = 0
    while i < len(tokens):
        if re.fullmatch(r"[MmLlCcZz]", tokens[i]):
            command = tokens[i]
            i += 1
            if command in "Zz":
                out.append("Z")
                cx, cy = start_x, start_y
                continue
        if command in "Mm":
            x, y = float(tokens[i]), float(tokens[i + 1])
            i += 2
            if command == "m":
                x, y = cx + x, cy + y
            cx, cy = start_x, start_y = x, y
            out.append(f"M{fmt(tx(x))} {fmt(ty(y))}")
            command = "L" if command == "M" else "l"
        elif command in "Ll":
            x, y = float(tokens[i]), float(tokens[i + 1])
            i += 2
            if command == "l":
                x, y = cx + x, cy + y
            cx, cy = x, y
            out.append(f"L{fmt(tx(x))} {fmt(ty(y))}")
        elif command in "Cc":
            values = [float(v) for v in tokens[i : i + 6]]
            i += 6
            if command == "c":
                values = [
                    values[0] + cx, values[1] + cy, values[2] + cx,
                    values[3] + cy, values[4] + cx, values[5] + cy,
                ]
            cx, cy = values[4], values[5]
            out.append(
                "C" + " ".join(
                    f"{fmt(tx(values[n]))} {fmt(ty(values[n + 1]))}" for n in (0, 2, 4)
                )
            )
        else:
            raise ValueError(f"unexpected potrace path command {command!r}")
    return "".join(out)


def trace_layers(rgba: np.ndarray) -> list[tuple[str, str]]:
    """Vectorise one cursor bitmap into [(fill colour, path data)] bottom to top."""
    palette = flat_palette(rgba)
    channels = [upscale(rgba[..., index]) for index in range(4)]
    visible = channels[3] >= ALPHA_THRESHOLD
    rgb = np.stack(channels[:3], axis=-1)
    distance = np.linalg.norm(rgb[..., None, :] - palette[None, None, :, :], axis=-1)
    nearest = distance.argmin(axis=-1)

    layers = [(hex_color(palette[0]), potrace_path(visible))]
    masks = []
    for index in range(1, len(palette)):
        mask = visible & (nearest == index)
        # Grow by one traced pixel so neighbouring colours overlap and leave no seam.
        grown = mask.copy()
        grown[1:] |= mask[:-1]
        grown[:-1] |= mask[1:]
        grown[:, 1:] |= mask[:, :-1]
        grown[:, :-1] |= mask[:, 1:]
        masks.append((int(mask.sum()), index, grown & visible))
    for _area, index, mask in sorted(masks, key=lambda item: -item[0]):
        path = potrace_path(mask)
        if path:
            layers.append((hex_color(palette[index]), path))
    return layers


# --------------------------------------------------------------------------
# SVG output
# --------------------------------------------------------------------------


def paths_markup(layers: list[tuple[str, str]]) -> str:
    return "".join(f'<path fill="{color}" d="{path}"/>' for color, path in layers if path)


def svg_document(content: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{NOMINAL_SIZE}" '
        f'height="{NOMINAL_SIZE}" viewBox="0 0 {CANVAS} {CANVAS}">\n'
        f"<defs>{SHADOW}</defs>\n"
        f'<g filter="url(#shadow)">{content}</g>\n'
        "</svg>\n"
    )


# --------------------------------------------------------------------------
# Theme build
# --------------------------------------------------------------------------


def hotspot(image: dict) -> tuple[int, int]:
    return (
        min(image["hotspot_x"], NOMINAL_SIZE - 1),
        min(image["hotspot_y"], NOMINAL_SIZE - 1),
    )


def write_cursor(
    output_dir: Path, name: str, frames: list[str], hot: tuple[int, int], delays: list[int]
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for previous in output_dir.iterdir():
        if previous.is_file() and (previous.suffix == ".svg" or previous.name == "metadata.json"):
            previous.unlink()

    metadata: list[dict[str, int | str]] = []
    for index, content in enumerate(frames):
        filename = f"{name}.svg" if len(frames) == 1 else f"{name}-{index + 1:02}.svg"
        (output_dir / filename).write_text(svg_document(content), encoding="utf-8")
        entry: dict[str, int | str] = {
            "filename": filename,
            "hotspot_x": hot[0],
            "hotspot_y": hot[1],
            "nominal_size": NOMINAL_SIZE,
        }
        if len(frames) > 1:
            entry["delay"] = delays[index] or DEFAULT_DELAY
        metadata.append(entry)
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def small_image(images: list[dict]) -> dict:
    return min(images, key=lambda image: image["size"])


def trace_cursor(cursor_path: Path) -> tuple[list[str], list[int]]:
    """Trace every frame of the 96px image set; returns (SVG contents, delays)."""
    images = read_xcursor_images(cursor_path)
    large = [image for image in images if image["size"] == TRACE_SIZE]
    if not large:
        raise ValueError(f"{cursor_path} has no {TRACE_SIZE}px image to trace")
    frames = [paths_markup(trace_layers(image_array(image))) for image in large]
    return frames, [image["delay"] for image in large]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--theme-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "Radioactive",
        help="theme directory containing cursors/",
    )
    args = parser.parse_args()

    theme_dir = args.theme_dir.resolve()
    source_cursors = theme_dir / "cursors"
    output_root = theme_dir / "cursors_scalable"
    if not source_cursors.is_dir():
        parser.error(f"expected {source_cursors}")
    output_root.mkdir(parents=True, exist_ok=True)

    canonical = sorted(
        path for path in source_cursors.iterdir() if path.is_file() and not path.is_symlink()
    )
    for cursor_path in canonical:
        name = cursor_path.name
        if name == "wait" and WAIT_USES_PROGRESS:
            continue
        hot = hotspot(small_image(read_xcursor_images(cursor_path)))
        frames, delays = trace_cursor(cursor_path)
        write_cursor(output_root / name, name, frames, hot, delays)

    if WAIT_USES_PROGRESS:
        wait_path = output_root / "wait"
        if wait_path.is_symlink():
            wait_path.unlink()
        elif wait_path.is_dir():
            shutil.rmtree(wait_path)
        os.symlink("progress", wait_path)

    for cursor_path in sorted(source_cursors.iterdir()):
        if not cursor_path.is_symlink():
            continue
        alias_path = output_root / cursor_path.name
        target = os.readlink(cursor_path)
        if alias_path.is_symlink():
            if os.readlink(alias_path) != target:
                alias_path.unlink()
                os.symlink(target, alias_path)
            continue
        if alias_path.exists():
            raise ValueError(f"scalable alias path already exists: {alias_path}")
        os.symlink(target, alias_path)

    all_resize = output_root / "all-resize"
    if not all_resize.exists() and not all_resize.is_symlink():
        os.symlink("all-scroll", all_resize)
    print(f"Built native SVG cursor artwork in {output_root}")


if __name__ == "__main__":
    main()
