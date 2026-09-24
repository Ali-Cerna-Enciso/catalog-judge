"""Las imágenes del README existen y son SVG válidos."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path


def test_readme_images_exist_and_parse(repo_root: Path) -> None:
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    refs = sorted(set(re.findall(r"!\[[^\]]*\]\((docs/img/[^)]+)\)", readme)))
    assert refs, "el README no referencia imágenes en docs/img"
    for ref in refs:
        path = repo_root / ref
        assert path.is_file(), f"falta el asset {ref}"
        ET.fromstring(path.read_bytes())
