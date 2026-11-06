"""Themed vector renderer following docs/engineering-visual-language.md.

The layout engine decides every position, route and wrap; this module only
paints those measured shapes with the project's own engineering palette:
white canvas, pale ownership boundaries, role-coloured resources, navy ink.
"""
from __future__ import annotations

import math

from .visual_style import boundary_color, palette as style_palette, role_fill, route_color

FONT_STACK = "'Noto Sans CJK SC','Noto Sans','Source Han Sans SC',sans-serif"


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _darken(value, amount):
    """Same-hue border: the role fill pulled toward its own dark tone."""
    channels = [round(int(value[i:i + 2], 16) * (1 - amount)) for i in (1, 3, 5)]
    return "#" + "".join(f"{min(255, channel):02X}" for channel in channels)


def _width(value, size):
    from .publication_render import font
    return font(size).getlength(value) * 1.06


class Svg:
    def __init__(self, width, height, colors):
        self.colors = colors
        ink = colors["ink"]
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" font-family="{FONT_STACK}">',
            '<defs>'
            f'<marker id="arrow" viewBox="0 0 10 10" refX="9.5" refY="5" markerWidth="7" markerHeight="7" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{ink}"/></marker>'
            '</defs>',
            f'<rect width="{width}" height="{height}" fill="{colors["background"]}"/>',
        ]

    def rect(self, box, fill="none", stroke="none", width=1.4, rx=0):
        x0, y0, x1, y1 = box
        self.parts.append(
            f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" '
            f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')

    def polyline(self, points, width=2.4, dash=None, color=None, marker=True):
        path = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        marker_attr = ' marker-end="url(#arrow)"' if marker else ""
        self.parts.append(
            f'<polyline points="{path}" fill="none" stroke="{color or self.colors["ink"]}" '
            f'stroke-width="{width}" stroke-linejoin="miter"{marker_attr}{dash_attr}/>')

    def text(self, x, y, value, size, fill=None, weight=400, anchor="start", max_width=None):
        fit = ""
        if max_width and _width(value, size) > max_width:
            fit = f' textLength="{max_width:.2f}" lengthAdjust="spacingAndGlyphs"'
        self.parts.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill or self.colors["ink"]}" text-anchor="{anchor}"{fit} '
            f'xml:space="preserve">{_esc(value)}</text>')

    def centered(self, lines, box, size, line_height, weight=600):
        x0, y0, x1, y1 = box
        y = (y0 + y1 - len(lines) * line_height) / 2 + size * .92
        for value in lines:
            self.text((x0 + x1) / 2, y, value, size, weight=weight,
                      anchor="middle", max_width=(x1 - x0) - size * .5)
            y += line_height

    def bytes(self):
        return ("\n".join(self.parts) + "\n</svg>\n").encode("utf-8")


def _label_layout(result, figure):
    layout = figure.get("label_layout")
    if isinstance(layout, dict):
        return layout
    from . import publication_render
    try:
        return publication_render.render(result, figure, labels_only=True)
    except (ValueError, KeyError, TypeError):
        return None


def render(result, figure):
    """Styled SVG for a publication layout, or None when there is no geometry."""
    plan = figure.get("structure_layout") or {}
    scene = figure.get("layout_scene") or plan.get("layout_scene")
    if plan.get("type") != "publication" or not scene:
        return None
    if not scene.get("quality", {}).get("routes_complete"):
        return None
    settings = result.get("settings", {})
    colors = style_palette(settings.get("style", "paper"))
    width, height = scene["width"], scene["height"]
    typography = plan["typography"]
    body_px = typography["body_px"]
    title = (plan.get("title") or result.get("spec", {}).get("title", "")) if settings.get("svg_title", False) else ""
    band = round(body_px * 2.1) if title else 0
    svg = Svg(width, height + band, colors)
    if band:
        svg.text(round(body_px * .8), round(body_px * 1.4), title, round(body_px * 1.4), weight=700)
        svg.parts.append(f'<g transform="translate(0,{band})">')

    def box_of(item):
        x0, y0 = item["x"] * width, item["y"] * height
        return x0, y0, x0 + item["width"] * width, y0 + item["height"] * height

    # Ownership scopes: pale boundary, no fill, heading above the box.
    for container in plan.get("containers", []):
        if container.get("render_boundary") is False:
            continue
        box = box_of(container["box"])
        svg.rect(box, stroke=boundary_color(colors), width=1.4)
        svg.text(box[0] + 4, box[1] - body_px * .38, container["label"], body_px, weight=700,
                 max_width=(box[2] - box[0]) - 8)

    # Connectors, then their measured labels.
    for route in scene["routes"]:
        points = [(x * width, y * height) for x, y in route["points"]]
        dashed = route.get("stroke_style", "dashed" if route["kind"] in {"control", "feedback", "clock"} else "solid") == "dashed"
        svg.polyline(points, 1.8 if dashed else 2.4,
                     "8 6" if dashed else None,
                     boundary_color(colors, strong=True) if dashed else route_color(route.get("line_color"), colors))
    labels = _label_layout(result, figure) or {}
    for item in labels.get("labels", []):
        box = item["box"]
        svg.text(box["x"] * width, box["y"] * height + labels.get("signal_font_px", body_px) * .95,
                 item["text"], labels.get("signal_font_px", body_px), weight=400)

    # Resources: role fill with a same-hue border.
    pad = round(body_px * .55)
    for node in plan["macro_nodes"]:
        measured = plan["symbol_metrics"][node["id"]]
        box = box_of(plan["boxes"][node["id"]])
        children = measured.get("children", [])
        if children:
            svg.rect(box, stroke=boundary_color(colors), width=1.4)
            header_y = box[1] + pad + body_px * .92
            for line in measured["lines"]:
                svg.text(box[0] + pad, header_y, line, body_px, weight=700,
                         max_width=(box[2] - box[0]) - 2 * pad)
                header_y += measured["line_height"]
            for child in children:
                offset = child["box_px"]
                child_box = (box[0] + offset["x"], box[1] + offset["y"],
                             box[0] + offset["x"] + offset["width"], box[1] + offset["y"] + offset["height"])
                fill = role_fill(child["kind"], colors)
                svg.rect(child_box, fill, _darken(fill, .45), 1.4)
                svg.centered(child["lines"], child_box, body_px, math.ceil(body_px * 1.22))
        else:
            fill = role_fill(node["kind"], colors)
            svg.rect(box, fill, _darken(fill, .45), 1.4)
            svg.centered(measured["lines"] + measured.get("detail_lines", []), box, body_px,
                         measured["line_height"])

    if band:
        svg.parts.append("</g>")
    data = svg.bytes()
    target_width_mm = typography.get("target_width_mm")
    if target_width_mm:
        from .svg_backend import _physical_size
        data = _physical_size(data, float(target_width_mm))
    return data
