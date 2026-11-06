"""Vector output: the SVG carries the same measured geometry as the guide."""
import io
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from PIL import Image

from silicon_canvas import bundle, engine, layout_guide, svg_backend
from silicon_canvas.artifact_store import ArtifactStore

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
SVG = "{http://www.w3.org/2000/svg}"


def compile_spec(spec, **settings):
    return engine.compile_manual({"spec": spec, "settings": {"scene": "auto", **settings}, "description": ""})


def selected(result):
    return next(figure for figure in result["figures"] if figure["id"] == result["selected_figure_id"])


def small_spec():
    return {"title": "Buffered Compute Path", "summary": "输入经缓冲后计算", "category": "dataflow",
            "nodes": [{"id": "input", "label": "Input", "kind": "io"},
                      {"id": "buffer", "label": "Buffer", "kind": "memory"},
                      {"id": "compute", "label": "Compute", "kind": "compute"},
                      {"id": "out", "label": "Output", "kind": "io"}],
            "edges": [{"source": "input", "target": "buffer", "kind": "data"},
                      {"source": "buffer", "target": "compute", "kind": "data"},
                      {"source": "compute", "target": "out", "kind": "data"}]}


class SvgBackendTests(unittest.TestCase):
    def test_svg_reuses_the_guide_geometry(self):
        result = compile_spec(small_spec(), target_width_mm=85, body_pt=8, svg_title=False)
        figure = selected(result)
        png = layout_guide.render(result, figure)
        svg = layout_guide.render_svg(result, figure)
        self.assertIsNotNone(png)
        self.assertIsNotNone(svg)
        scene = figure["layout_scene"]
        root = ET.fromstring(svg)
        self.assertEqual(root.get("viewBox"), f'0 0 {scene["width"]} {scene["height"]}')
        self.assertEqual(Image.open(io.BytesIO(png)).size, (scene["width"], scene["height"]))
        self.assertEqual(root.get("width"), "85mm")
        # Every source label is real text; nothing is baked into a raster layer.
        text = " ".join("".join(element.itertext()) for element in root.iter(SVG + "text"))
        self.assertEqual(list(root.iter(SVG + "image")), [])
        for node in figure["structure_layout"]["macro_nodes"]:
            self.assertIn(" ".join(node["label"].split()), " ".join(text.split()))

    def test_themed_render_adds_a_heading_band(self):
        result = compile_spec(small_spec(), target_width_mm=85, body_pt=8, svg_title=True)
        figure = selected(result)
        svg = layout_guide.render_svg(result, figure)
        root = ET.fromstring(svg)
        scene = figure["layout_scene"]
        self.assertEqual(root.get("width"), "85mm")
        self.assertGreater(float(root.get("viewBox").split()[3]), scene["height"])
        text = " ".join("".join(element.itertext()) for element in root.iter(SVG + "text"))
        self.assertIn("Buffered Compute Path", text)

    def test_physical_width_follows_the_typography_contract(self):
        result = compile_spec(small_spec(), target_width_mm=85, body_pt=8)
        typography = selected(result)["structure_layout"]["typography"]
        self.assertEqual(typography["target_width_mm"], 85.0)
        self.assertEqual(typography["body_pt"], 8.0)
        self.assertEqual(typography["signal_pt"], 7.5)
        # 8 pt at 1800 px over 85 mm.
        self.assertEqual(typography["body_px"], 60)

    def test_explicit_width_overrides_the_scene_minimum(self):
        spec = small_spec()
        result = compile_spec(spec, scene="concept", target_width_mm=85, body_pt=8)
        self.assertEqual(selected(result)["design_contract"]["target_width_mm"], 85.0)
        result = compile_spec(spec, scene="concept")
        self.assertEqual(selected(result)["design_contract"]["target_width_mm"], 240.0)

    def test_prompt_only_views_have_no_vector_figure(self):
        payload = json.loads((EXAMPLES / "attention-dataflow.json").read_text(encoding="utf-8"))
        result = engine.compile_manual({**payload, "settings": {"scene": "auto"}, "description": ""})
        figure = next(f for f in result["figures"] if f.get("algorithm_flow_plan"))
        self.assertIsNone(layout_guide.render_svg(result, figure))

    def test_invalid_document_width_is_rejected(self):
        for value in (20, 500, "85", True):
            with self.assertRaises(ValueError):
                engine.normalize_settings({"target_width_mm": value})
        for value in (5, 20, "8"):
            with self.assertRaises(ValueError):
                engine.normalize_settings({"body_pt": value})

    def test_product_render_keeps_its_framing_reference(self):
        payload = json.loads((EXAMPLES / "soc.json").read_text(encoding="utf-8"))
        result = engine.compile_manual({**payload, "settings": {"scene": "auto", "representation": "product_render"},
                                        "description": "芯片产品渲染"})
        figure = selected(result)
        self.assertEqual(figure["representation"], "product_render")
        self.assertIsNone(layout_guide.render_svg(result, figure))

    def test_cli_writes_a_document_sized_svg(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            spec_path = Path(temporary) / "spec.json"
            spec_path.write_text(json.dumps({"spec": small_spec()}), encoding="utf-8")
            out = Path(temporary) / "figure.svg"
            svg_backend.main([str(spec_path), str(out), "--width-mm", "85", "--body-pt", "8"])
            self.assertIn('width="85mm"', out.read_text(encoding="utf-8"))

    def test_artifact_names_and_bundle_include_the_svg(self):
        self.assertEqual(ArtifactStore.figure_name("main", "figure.svg"), "main.figure.svg")
        result = compile_spec(small_spec(), target_width_mm=85, body_pt=8)
        data = bundle.build(result)
        import zipfile
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertIn("figures/" + result["selected_figure_id"] + "/figure.svg", archive.namelist())


if __name__ == "__main__":
    unittest.main()
