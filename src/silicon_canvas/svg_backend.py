"""Vector backend: emit the measured layout as SVG instead of a PNG plate.

The publication, structure and behavior renderers draw only through the
Pillow ImageDraw API. Swapping Image/ImageDraw for one render therefore turns
the same geometry into SVG without duplicating any layout, routing or
typography decision. The result is the figure itself, not a reference plate
for an image generator.
"""
from __future__ import annotations

import contextlib
import json
import re
import sys

FONT_STACK = "'Noto Sans CJK SC','Noto Sans','Source Han Sans SC',sans-serif"
_PHYSICAL = re.compile(r'width="(\d+)" height="(\d+)"')


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


class Canvas:
    def __init__(self, size, background):
        self.width, self.height = size
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}" font-family="{FONT_STACK}">',
            f'<rect width="{self.width}" height="{self.height}" fill="{background}"/>',
        ]

    def save(self, buffer, format=None):
        buffer.write(("\n".join(self.parts) + "\n</svg>\n").encode("utf-8"))


class Draw:
    """The subset of ImageDraw the shipped renderers actually call."""

    def __init__(self, canvas):
        self.canvas = canvas

    def rectangle(self, box, fill=None, outline=None, width=1):
        x0, y0, x1, y1 = box
        self.canvas.parts.append(
            f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" '
            f'fill="{fill or "none"}" stroke="{outline or "none"}" stroke-width="{width}"/>')

    def rounded_rectangle(self, box, radius=0, fill=None, outline=None, width=1):
        x0, y0, x1, y1 = box
        self.canvas.parts.append(
            f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" '
            f'rx="{radius}" fill="{fill or "none"}" stroke="{outline or "none"}" stroke-width="{width}"/>')

    def line(self, points, fill=None, width=1):
        points = [tuple(point) for point in points]
        if len(points) == 2:
            (x0, y0), (x1, y1) = points
            self.canvas.parts.append(
                f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" '
                f'stroke="{fill}" stroke-width="{width}"/>')
            return
        path = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        self.canvas.parts.append(
            f'<polyline points="{path}" fill="none" stroke="{fill}" stroke-width="{width}"/>')

    def polygon(self, points, fill=None):
        path = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        self.canvas.parts.append(f'<polygon points="{path}" fill="{fill}"/>')

    def ellipse(self, box, fill=None, outline=None, width=1):
        x0, y0, x1, y1 = box
        self.canvas.parts.append(
            f'<ellipse cx="{(x0 + x1) / 2:.2f}" cy="{(y0 + y1) / 2:.2f}" '
            f'rx="{(x1 - x0) / 2:.2f}" ry="{(y1 - y0) / 2:.2f}" '
            f'fill="{fill or "none"}" stroke="{outline or "none"}" stroke-width="{width}"/>')

    def text(self, xy, text, font=None, fill=None, anchor=None):
        px, ascent = font.size, font.getmetrics()[0]
        x, y = xy
        self.canvas.parts.append(
            f'<text x="{x:.2f}" y="{y + ascent:.2f}" font-size="{px}" fill="{fill}" '
            f'xml:space="preserve">{_esc(text)}</text>')

    def multiline_text(self, xy, text, font=None, fill=None, spacing=4):
        px, ascent = font.size, font.getmetrics()[0]
        x, y = xy
        for offset, line in enumerate(str(text).splitlines()):
            self.canvas.parts.append(
                f'<text x="{x:.2f}" y="{y + ascent + offset * (px + spacing):.2f}" '
                f'font-size="{px}" fill="{fill}" xml:space="preserve">{_esc(line)}</text>')

    def textlength(self, text, font=None):
        return font.getlength(text)


class ImageModule:
    @staticmethod
    def new(mode, size, color=None):
        return Canvas(size, color)


class DrawModule:
    @staticmethod
    def Draw(canvas):
        return Draw(canvas)


@contextlib.contextmanager
def pillow_as_svg():
    """Route Pillow draw calls into the SVG emitter for one render."""
    import PIL
    import PIL.Image  # noqa: F401  populate the package attributes before swapping
    import PIL.ImageDraw  # noqa: F401
    saved = (PIL.Image, PIL.ImageDraw,
             sys.modules.get("PIL.Image"), sys.modules.get("PIL.ImageDraw"))
    PIL.Image, PIL.ImageDraw = ImageModule, DrawModule
    sys.modules["PIL.Image"], sys.modules["PIL.ImageDraw"] = ImageModule, DrawModule
    try:
        yield
    finally:
        (PIL.Image, PIL.ImageDraw,
         sys.modules["PIL.Image"], sys.modules["PIL.ImageDraw"]) = saved


def _physical_size(data, target_width_mm):
    """Give the pixel canvas a document width; the viewBox keeps exact units."""
    match = _PHYSICAL.search(data.decode("utf-8"))
    if not match:
        return data
    width, height = int(match.group(1)), int(match.group(2))
    height_mm = target_width_mm * height / width
    return data.replace(
        match.group(0).encode(),
        f'width="{target_width_mm:g}mm" height="{height_mm:.3f}mm"'.encode(), 1)


def render(result, figure):
    """SVG bytes for a figure, or None when the figure has no measured geometry.

    Mirrors layout_guide.render: a prompt-only view (algorithm dependency plan)
    has nothing to draw, and this backend never invents a layout for it.
    """
    from . import layout_guide
    if figure.get("representation") in {"product_render", "system_illustration"}:
        # Those views carry a framing reference, not measured engineering geometry.
        return None
    with pillow_as_svg():
        data = layout_guide.render(result, figure)
    if not data:
        return None
    typography = (figure.get("structure_layout") or {}).get("typography") or {}
    target_width_mm = typography.get("target_width_mm")
    if target_width_mm:
        data = _physical_size(data, float(target_width_mm))
    return data


def main(argv=None):
    import argparse
    from . import engine
    parser = argparse.ArgumentParser(prog="python -m silicon_canvas.svg_backend",
                                     description="Compile a semantic spec and write the figure as SVG.")
    parser.add_argument("spec", help="JSON file with spec/settings, as accepted by silicon_compile")
    parser.add_argument("out", help="output .svg path")
    parser.add_argument("--width-mm", type=float, help="document column width; overrides the scene default")
    parser.add_argument("--body-pt", type=float, help="body type size; overrides the scene default")
    parser.add_argument("--scene", default="auto")
    parser.add_argument("--style", default="paper")
    options = parser.parse_args(argv)
    payload = json.load(open(options.spec, encoding="utf-8"))
    settings = {"scene": options.scene, "style": options.style, **(payload.get("settings") or {})}
    if options.width_mm is not None:
        settings["target_width_mm"] = options.width_mm
    if options.body_pt is not None:
        settings["body_pt"] = options.body_pt
    result = engine.compile_manual({**payload, "settings": settings,
                                    "description": payload.get("description", "")})
    figure = next(f for f in result["figures"] if f["id"] == result["selected_figure_id"])
    data = render(result, figure)
    if not data:
        for warning in result["warnings"]:
            print(warning, file=sys.stderr)
        raise SystemExit(f"figure {figure['id']} has no measured geometry: the content does not fit "
                         f"{figure['design_contract'].get('target_width_mm')} mm at "
                         f"{figure['design_contract'].get('body_pt')} pt. Reduce the scope or widen the figure.")
    open(options.out, "wb").write(data)
    print(options.out, "written from", figure["id"], len(data), "bytes")


if __name__ == "__main__":
    main()
