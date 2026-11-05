"""Themed vector renderer: the measured layout in Silicon Canvas' own graphic language.

The layout engine decides every position, route and wrap. This module only
decides how those measured shapes are painted: tinted ownership containers,
light cards, a bold heading and dark orthogonal connectors, as in the shipped
showcase artwork. It is a renderer, not a layout.
"""
from __future__ import annotations

import math

FONT_STACK = "'Noto Sans CJK SC','Noto Sans','Source Han Sans SC',sans-serif"
INK = "#1B1B1B"
MUTED_INK = "#4A4A4A"
EDGE = "#262626"

# Ownership tint per semantic role, taken from the showcase figures.
TINTS = {
    "compute": ("#E9F2E5", "#6E9468"),
    "memory": ("#FBF0D9", "#C79A52"),
    "control": ("#EEEEEE", "#9A9A9A"),
    "io": ("#E8EEF6", "#7C93B0"),
    "state": ("#F0EAF7", "#8B74AE"),
    "signal": ("#EEEEEE", "#9A9A9A"),
    "event": ("#EEEEEE", "#9A9A9A"),
    "stage": ("#E9F2E5", "#6E9468"),
    "decision": ("#FBF0D9", "#C79A52"),
}
NODE_FILL = "#FFFFFF"
NODE_BORDER = "#A7ABB0"
EXTERNAL_FILL = "#F4F4F2"


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


class Svg:
    def __init__(self, width, height):
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" font-family="{FONT_STACK}">',
            '<defs>'
            '<filter id="card" x="-20%" y="-20%" width="140%" height="140%">'
            '<feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000000" flood-opacity="0.12"/>'
            '</filter>'
            f'<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{EDGE}"/></marker>'
            f'<marker id="arrow-quiet" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
            f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#7C7C7C"/></marker>'
            '</defs>',
            f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>',
        ]

    def rect(self, box, fill="none", stroke="none", width=1.5, rx=0, shadow=False):
        x0, y0, x1, y1 = box
        extra = ' filter="url(#card)"' if shadow else ""
        self.parts.append(
            f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" '
            f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"{extra}/>')

    def polyline(self, points, width=2.6, dash=None, color=EDGE, marker="arrow"):
        path = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linejoin="miter" marker-end="url(#{marker})"{dash_attr}/>')

    def text(self, x, y, value, size, fill=INK, weight=600, anchor="start", italic=False, max_width=None):
        style = ' font-style="italic"' if italic else ""
        fit = ""
        if max_width and _width(value, size) > max_width:
            # Never let a label run outside its measured box; squeeze only then.
            fit = f' textLength="{max_width:.2f}" lengthAdjust="spacingAndGlyphs"'
        self.parts.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}"{style}{fit} xml:space="preserve">{_esc(value)}</text>')

    def centered(self, lines, box, size, line_height, fill=INK, weight=600):
        x0, y0, x1, y1 = box
        y = (y0 + y1 - len(lines) * line_height) / 2 + size * .92
        for value in lines:
            self.text((x0 + x1) / 2, y, value, size, fill, weight, anchor="middle",
                      max_width=(x1 - x0) - size * .5)
            y += line_height

    def bytes(self):
        return ("\n".join(self.parts) + "\n</svg>\n").encode("utf-8")


def _width(value, size):
    """Measured advance at the shipped font, with a bold-width allowance."""
    from .publication_render import font
    return font(size).getlength(value) * 1.06


def _tint(kind, external=False):
    if external:
        return EXTERNAL_FILL, "#8E8E8E"
    return TINTS.get(kind, ("#F1F2F4", "#9A9A9A"))


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
    width, height = scene["width"], scene["height"]
    typography = plan["typography"]
    body_px = typography["body_px"]
    title = (plan.get("title") or result.get("spec", {}).get("title", "")) if result.get("settings", {}).get("svg_title", True) else ""
    band = round(body_px * 2.3) if title else 0
    svg = Svg(width, height + band)
    if band:
        svg.text(round(body_px * .9), round(body_px * 1.55), title, round(body_px * 1.55), INK, 700)
        svg.parts.append(f'<g transform="translate(0,{band})">')

    def box_of(item):
        x0, y0 = item["x"] * width, item["y"] * height
        return x0, y0, x0 + item["width"] * width, y0 + item["height"] * height

    # Ownership scopes first, so cards and routes sit on top of their fill.
    for container in plan.get("containers", []):
        if container.get("render_boundary") is False:
            continue
        fill, stroke = _tint("control")
        svg.rect(box_of(container["box"]), fill, stroke, 1.6, rx=14)
    for node in plan["macro_nodes"]:
        measured = plan["symbol_metrics"][node["id"]]
        if not measured.get("children"):
            continue
        fill, stroke = _tint(node["kind"], external=node.get("zone") == "external")
        box = box_of(plan["boxes"][node["id"]])
        svg.rect(box, fill, stroke, 1.6, rx=14)

    # Connectors, then their measured labels.
    for route in scene["routes"]:
        points = [(x * width, y * height) for x, y in route["points"]]
        dashed = route.get("stroke_style", "dashed" if route["kind"] in {"control", "feedback", "clock"} else "solid") == "dashed"
        # Long secondary corridors recede so the primary path stays dominant.
        quiet = dashed or max(math.dist(a, b) for a, b in zip(points, points[1:])) > width * .55
        svg.polyline(points, 1.8 if quiet else 2.6, "8 6" if dashed else None,
                     "#7C7C7C" if quiet else EDGE, "arrow-quiet" if quiet else "arrow")
    labels = _label_layout(result, figure) or {}
    for item in labels.get("labels", []):
        box = item["box"]
        svg.text(box["x"] * width, box["y"] * height + labels.get("signal_font_px", body_px) * .95,
                 item["text"], labels.get("signal_font_px", body_px), MUTED_INK, 500)

    # Cards and their measured text.
    pad = round(body_px * .55)
    for node in plan["macro_nodes"]:
        measured = plan["symbol_metrics"][node["id"]]
        box = box_of(plan["boxes"][node["id"]])
        children = measured.get("children", [])
        if children:
            header_y = box[1] + pad + body_px * .92
            for line in measured["lines"]:
                svg.text(box[0] + pad, header_y, line, body_px, INK, 700,
                         max_width=(box[2] - box[0]) - 2 * pad)
                header_y += measured["line_height"]
            for child in children:
                offset = child["box_px"]
                child_box = (box[0] + offset["x"], box[1] + offset["y"],
                             box[0] + offset["x"] + offset["width"], box[1] + offset["y"] + offset["height"])
                svg.rect(child_box, NODE_FILL, NODE_BORDER, 1.5, rx=9, shadow=True)
                svg.centered(child["lines"], child_box, body_px, math.ceil(body_px * 1.22))
        else:
            external = node.get("zone") == "external"
            svg.rect(box, EXTERNAL_FILL if external else NODE_FILL, "#6E6E6E" if external else NODE_BORDER,
                     1.5, rx=10, shadow=True)
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
