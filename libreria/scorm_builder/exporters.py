"""Exportadores adicionales: SCORM 2004, HTML standalone.

El motor por defecto genera SCORM 1.2 (el más compatible con LMS legacy).
Estos exportadores son alternativas para distintos casos de uso:

- export_html_standalone: empaqueta los HTML del curso como sitio estático,
  sin dependencias SCORM. Útil para subir a un blog/web propia.
- export_scorm_2004: genera SCORM 2004 4ª edición (lo que piden los LMS modernos).
- export_xapi (próxima versión): empaqueta como cmi5/xAPI.
"""
from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Optional


# ---------- HTML STANDALONE -----------

INDEX_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: #F8FAFC; color: #0F172A; line-height: 1.6;
  min-height: 100vh; padding: 2rem 1.5rem;
}}
.container {{ max-width: 900px; margin: 0 auto; }}
header.cover {{
  background: linear-gradient(135deg, #0A2540, #1D4ED8);
  color: white; padding: 3rem 2rem; border-radius: 16px;
  margin-bottom: 2rem; box-shadow: 0 4px 20px rgba(10,37,64,0.15);
}}
header.cover h1 {{ font-size: 2.2rem; margin-bottom: 0.5rem; }}
header.cover p {{ color: rgba(255,255,255,0.85); font-size: 1.05rem; }}
.toc {{ background: white; padding: 2rem; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.05); }}
.toc h2 {{ margin-bottom: 1.2rem; color: #0A2540; }}
.toc ol {{ list-style: none; counter-reset: tema; }}
.toc li {{
  counter-increment: tema; margin-bottom: 0.7rem;
  padding-left: 3.5rem; position: relative;
  padding-top: 0.7rem; padding-bottom: 0.7rem;
}}
.toc li::before {{
  content: counter(tema, decimal-leading-zero);
  position: absolute; left: 0; top: 50%; transform: translateY(-50%);
  width: 48px; height: 48px; background: #2563EB; color: white;
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-weight: 700;
}}
.toc a {{
  display: block; padding: 0.5rem 1rem; background: #F1F5F9;
  border-radius: 8px; color: #0F172A; text-decoration: none;
  font-weight: 600; transition: all 0.2s;
}}
.toc a:hover {{ background: #DBEAFE; color: #1D4ED8; transform: translateX(4px); }}
.toc small {{ display: block; color: #64748B; font-weight: 400; font-size: 0.85rem; margin-top: 0.2rem; }}
footer {{ text-align: center; color: #94A3B8; margin-top: 3rem; font-size: 0.85rem; }}
</style>
</head>
<body>
<div class="container">
  <header class="cover">
    <h1>{title}</h1>
    {subtitle_html}
    <p style="margin-top:1rem; font-size:0.9rem;">{author_html}</p>
  </header>
  <div class="toc">
    <h2>Contenidos del curso</h2>
    <ol>
{toc_items}
    </ol>
  </div>
  <footer>Generado con SCORM Builder · {n_topics} temas</footer>
</div>
</body>
</html>
"""


def _strip_scorm_calls(html: str) -> str:
    """Elimina las llamadas a la API SCORM del HTML para que funcione standalone."""
    # Inhabilitamos solo las llamadas (mantenemos el resto del JS de quiz/progreso)
    return re.sub(
        r"if\s*\(\s*typeof\s+SCORM\s*!==\s*'undefined'.+?\}\s*",
        "if (false) { }",
        html,
        flags=re.DOTALL,
    )


def export_html_standalone(course, htmls: Dict[int, str], output_zip: Path) -> Path:
    """Empaqueta el curso como sitio HTML standalone.

    Args:
        course: CourseStructure
        htmls: dict {topic_number: html_string}
        output_zip: ruta del ZIP a generar
    """
    output_zip = Path(output_zip)
    work = output_zip.parent / f"_{output_zip.stem}_html_build"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    # index.html con TOC
    md = course.metadata
    toc_items = []
    for topic in course.topics:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", topic.title.lower())[:40] or f"tema_{topic.number}"
        filename = f"tema_{topic.number:02d}_{slug}.html"
        n_subs = len(topic.subsections)
        n_quiz = len(topic.quiz)
        toc_items.append(
            f'      <li><a href="{filename}">{topic.title}'
            f'<small>{n_subs} subapartados · {n_quiz} preguntas de quiz</small></a></li>'
        )

    subtitle_html = f'<p style="font-size:1.15rem;">{md.subtitle}</p>' if md.subtitle else ""
    author_html = md.author or "Curso e-learning"

    index_html = INDEX_HTML_TEMPLATE.format(
        title=md.title,
        subtitle_html=subtitle_html,
        author_html=author_html,
        toc_items="\n".join(toc_items),
        n_topics=len(course.topics),
    )
    (work / "index.html").write_text(index_html, encoding="utf-8")

    # Un HTML por tema (con SCORM API neutralizada)
    for topic in course.topics:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", topic.title.lower())[:40] or f"tema_{topic.number}"
        filename = f"tema_{topic.number:02d}_{slug}.html"
        html = htmls.get(topic.number, "")
        # Quitar llamadas SCORM
        html_clean = _strip_scorm_calls(html)
        # Inyectar enlace de vuelta al índice
        nav_back = (
            '<div style="position:fixed;top:1rem;right:1rem;z-index:1000;">'
            '<a href="index.html" style="background:white;padding:0.5rem 1rem;'
            'border-radius:6px;text-decoration:none;color:#0A2540;font-weight:600;'
            'box-shadow:0 2px 8px rgba(0,0,0,0.15);">← Índice</a></div>'
        )
        html_clean = html_clean.replace("<body>", "<body>" + nav_back, 1)
        (work / filename).write_text(html_clean, encoding="utf-8")

    # Empaquetar ZIP
    if output_zip.exists():
        output_zip.unlink()
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in work.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(work)))
    shutil.rmtree(work)
    return output_zip


# ---------- SCORM 2004 -----------

SCORM_2004_MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{identifier}" version="1.0"
  xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3"
  xmlns:adlseq="http://www.adlnet.org/xsd/adlseq_v1p3"
  xmlns:adlnav="http://www.adlnet.org/xsd/adlnav_v1p3"
  xmlns:imsss="http://www.imsglobal.org/xsd/imsss"
  xmlns:lom="http://ltsc.ieee.org/xsd/LOM"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsglobal.org/xsd/imscp_v1p1 imscp_v1p1.xsd
                      http://www.adlnet.org/xsd/adlcp_v1p3 adlcp_v1p3.xsd
                      http://www.adlnet.org/xsd/adlseq_v1p3 adlseq_v1p3.xsd
                      http://www.adlnet.org/xsd/adlnav_v1p3 adlnav_v1p3.xsd
                      http://www.imsglobal.org/xsd/imsss imsss_v1p0.xsd">

  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>2004 4th Edition</schemaversion>
    <lom:lom>
      <lom:general>
        <lom:identifier>
          <lom:catalog>SCORM</lom:catalog>
          <lom:entry>{identifier}</lom:entry>
        </lom:identifier>
        <lom:title><lom:string language="es">{title}</lom:string></lom:title>
        <lom:description><lom:string language="es">{description}</lom:string></lom:description>
        <lom:language>es</lom:language>
      </lom:general>
    </lom:lom>
  </metadata>

  <organizations default="ORG-{identifier}">
    <organization identifier="ORG-{identifier}" adlseq:objectivesGlobalToSystem="false">
      <title>{title}</title>
      <item identifier="ITEM-{identifier}" identifierref="RES-{identifier}">
        <title>{title}</title>
        <adlcp:completionThreshold minProgressMeasure="0.8"/>
        <imsss:sequencing>
          <imsss:controlMode choice="true" flow="true"/>
          <imsss:objectives>
            <imsss:primaryObjective satisfiedByMeasure="true" objectiveID="PRIMARYOBJ">
              <imsss:minNormalizedMeasure>{mastery_norm}</imsss:minNormalizedMeasure>
            </imsss:primaryObjective>
          </imsss:objectives>
          <imsss:deliveryControls completionSetByContent="true" objectiveSetByContent="true"/>
        </imsss:sequencing>
      </item>
    </organization>
  </organizations>

  <resources>
    <resource identifier="RES-{identifier}" type="webcontent" adlcp:scormType="sco" href="index.html">
      <file href="index.html"/>
{extra_files}
    </resource>
  </resources>
</manifest>
"""


def _xml_escape_2004(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def export_scorm_2004(
    topic, html_content: str, course_title: str,
    output_path: Path, recursos_dir: Optional[Path] = None,
    mastery: int = 70,
) -> Path:
    """Empaqueta un tema como SCORM 2004 4ª edición.

    El HTML interno usa el wrapper SCORM universal definido en renderer.py,
    que detecta automáticamente la versión del LMS (API_1484_11 vs API)
    y traduce las llamadas. Por eso el mismo HTML sirve tanto para 1.2 como
    para 2004 — sólo cambia el manifest.

    Características de este export 2004:
      - Manifest con namespaces 2004 4th Edition correctos.
      - completionThreshold + primaryObjective satisfiedByMeasure (0–1).
      - deliveryControls: el SCO marca completion y objective por contenido.
      - LOM metadata embebido.
      - El contenido reporta cmi.score.scaled, cmi.completion_status,
        cmi.success_status, cmi.progress_measure, cmi.interactions.*
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    identifier = re.sub(r"[^a-zA-Z0-9_]+", "_", f"T{topic.number}_{topic.title}")[:60].upper() or "SCORM"

    work = output_path.parent / f"_{output_path.stem}_2004_build"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / "index.html").write_text(html_content, encoding="utf-8")

    extra_files = []
    if recursos_dir and Path(recursos_dir).exists():
        target = work / "recursos"
        target.mkdir(exist_ok=True)
        for f in Path(recursos_dir).iterdir():
            if f.is_file():
                shutil.copy2(f, target / f.name)
                extra_files.append(f'      <file href="recursos/{f.name}"/>')

    manifest = SCORM_2004_MANIFEST.format(
        identifier=identifier,
        title=_xml_escape_2004(topic.title),
        description=_xml_escape_2004(f"Tema {topic.number} del curso '{course_title}'."),
        mastery_norm=f"{max(0, min(100, mastery)) / 100:.2f}",
        extra_files="\n".join(extra_files),
    )
    (work / "imsmanifest.xml").write_text(manifest, encoding="utf-8")

    if output_path.exists():
        output_path.unlink()
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in work.rglob("*"):
            if fp.is_file():
                zf.write(fp, arcname=str(fp.relative_to(work)))
    shutil.rmtree(work)
    return output_path


def export_all_topics_2004(course, htmls: dict, output_dir: Path,
                            recursos_dir: Optional[Path] = None) -> List[Path]:
    """Empaqueta todos los temas como SCORM 2004."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    zips = []
    for topic in course.topics:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", topic.title.lower())[:40]
        zip_name = f"T{topic.number:02d}_{slug}_scorm2004.zip"
        zip_path = output_dir / zip_name
        html = htmls.get(topic.number)
        if not html:
            continue
        export_scorm_2004(topic, html, course.metadata.title, zip_path,
                          recursos_dir=recursos_dir, mastery=course.metadata.mastery)
        zips.append(zip_path)
    return zips
