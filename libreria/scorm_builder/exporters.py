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


# ============================================================
# IMS CONTENT PACKAGE (v0.5 Fase 2)
# Para Moodle como "Contenido IMS" — sin tracking SCORM, pero estructura
# multi-tema reconocida por el LMS.
# ============================================================

IMS_CP_MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{identifier}" version="1.1"
  xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
  xmlns:imsmd="http://www.imsglobal.org/xsd/imsmd_v1p2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsglobal.org/xsd/imscp_v1p1 imscp_v1p1.xsd
                      http://www.imsglobal.org/xsd/imsmd_v1p2 imsmd_v1p2p4.xsd">

  <metadata>
    <schema>IMS Content</schema>
    <schemaversion>1.1.4</schemaversion>
    <imsmd:lom>
      <imsmd:general>
        <imsmd:identifier>{identifier}</imsmd:identifier>
        <imsmd:title>
          <imsmd:langstring xml:lang="es">{title}</imsmd:langstring>
        </imsmd:title>
        <imsmd:description>
          <imsmd:langstring xml:lang="es">{description}</imsmd:langstring>
        </imsmd:description>
        <imsmd:language>es</imsmd:language>
{keywords}      </imsmd:general>
    </imsmd:lom>
  </metadata>

  <organizations default="ORG-{identifier}">
    <organization identifier="ORG-{identifier}">
      <title>{title}</title>
{items}    </organization>
  </organizations>

  <resources>
{resources}  </resources>
</manifest>
"""


def export_ims_cp(course, htmls: Dict[int, str], output_zip: Path,
                  recursos_dir: Optional[Path] = None) -> Path:
    """Empaqueta el curso completo como un IMS Content Package (1.1.4).

    Estructura del paquete:
    - imsmanifest.xml: organizations con un item por tema, resources con
      cada HTML como webcontent
    - tema_01_<slug>.html, tema_02_<slug>.html, ...
    - recursos/: carpeta común con imágenes, PDFs, etc.

    Diferencias con SCORM:
    - No usa namespace adlcp
    - No es scormtype="sco"
    - Moodle lo carga como recurso "Contenido IMS"
    - No hay tracking de completion ni nota (es navegación libre)
    """
    output_zip = Path(output_zip)
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    work = output_zip.parent / f"_{output_zip.stem}_imscp_build"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    md = course.metadata
    course_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", md.title.lower())[:40] or "curso"
    identifier = course_slug.upper()[:60]

    # Recoger todas las etiquetas a nivel curso (unión de tags por tema)
    all_tags = []
    seen = set()
    for t in course.topics:
        for tag in getattr(t, "tags", []) or []:
            if tag not in seen:
                all_tags.append(tag)
                seen.add(tag)

    # 1. Escribir cada HTML del tema, quitando llamadas SCORM
    item_lines: List[str] = []
    resource_lines: List[str] = []
    html_files: List[str] = []
    for topic in course.topics:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", topic.title.lower())[:40] or f"tema_{topic.number}"
        filename = f"tema_{topic.number:02d}_{slug}.html"
        html = htmls.get(topic.number, "")
        html_clean = _strip_scorm_calls(html)
        (work / filename).write_text(html_clean, encoding="utf-8")
        html_files.append(filename)

        item_id = f"ITEM-T{topic.number:02d}"
        res_id = f"RES-T{topic.number:02d}"
        item_lines.append(
            f'      <item identifier="{item_id}" identifierref="{res_id}" isvisible="true">\n'
            f'        <title>{_xml_escape_2004(topic.title)}</title>\n'
            f'      </item>'
        )
        resource_lines.append(
            f'    <resource identifier="{res_id}" type="webcontent" href="{filename}">\n'
            f'      <file href="{filename}"/>\n'
            f'    </resource>'
        )

    # 2. Copiar recursos (imágenes, PDFs, etc.) y declararlos como ficheros
    if recursos_dir and Path(recursos_dir).exists():
        target = work / "recursos"
        target.mkdir(exist_ok=True)
        files_extra: List[str] = []
        for f in Path(recursos_dir).iterdir():
            if f.is_file():
                shutil.copy2(f, target / f.name)
                files_extra.append(f"recursos/{f.name}")
        # Recurso "shared" con todos los archivos comunes
        if files_extra:
            shared_files = "\n".join(
                f'      <file href="{_xml_escape_2004(p)}"/>' for p in files_extra
            )
            resource_lines.append(
                f'    <resource identifier="RES-SHARED" type="webcontent" href="recursos/">\n'
                f'{shared_files}\n    </resource>'
            )

    # 3. Construir keywords
    keywords_xml = ""
    if all_tags:
        kw_lines = []
        for tag in all_tags:
            kw_lines.append("        <imsmd:keyword>")
            kw_lines.append(
                f'          <imsmd:langstring xml:lang="es">{_xml_escape_2004(tag)}</imsmd:langstring>'
            )
            kw_lines.append("        </imsmd:keyword>")
        keywords_xml = "\n".join(kw_lines) + "\n"

    manifest = IMS_CP_MANIFEST.format(
        identifier=identifier,
        title=_xml_escape_2004(md.title),
        description=_xml_escape_2004(md.subtitle or f"Curso: {md.title}"),
        keywords=keywords_xml,
        items="\n".join(item_lines) + ("\n" if item_lines else ""),
        resources="\n".join(resource_lines) + ("\n" if resource_lines else ""),
    )
    (work / "imsmanifest.xml").write_text(manifest, encoding="utf-8")

    # 4. Empaquetar
    if output_zip.exists():
        output_zip.unlink()
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in work.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(work)))
    shutil.rmtree(work)
    return output_zip


# ============================================================
# cmi5 (xAPI) — alternativa moderna a SCORM
# (v0.5 Fase 5)
# ============================================================
# cmi5 es un perfil xAPI estándar (ADL) que muchos LMS modernos prefieren a
# SCORM 1.2/2004. La estructura del paquete es similar a SCORM pero el manifest
# es `cmi5.xml` y el tracking se hace mediante Statements enviados a un LRS
# (Learning Record Store) configurado por el LMS en runtime.

CMI5_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<courseStructure xmlns="https://w3id.org/xapi/profiles/cmi5/v1/CourseStructure.xsd"
                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <course id="{course_id}">
    <title>
      <langstring lang="es">{title}</langstring>
    </title>
    <description>
      <langstring lang="es">{description}</langstring>
    </description>
  </course>
{au_blocks}</courseStructure>
"""

CMI5_AU_TEMPLATE = """  <au id="{au_id}" launchMethod="OwnWindow"
      moveOn="{move_on}" masteryScore="{mastery}">
    <title>
      <langstring lang="es">{title}</langstring>
    </title>
    <description>
      <langstring lang="es">{description}</langstring>
    </description>
    <url>{url}</url>
  </au>
"""

# JS de tracking xAPI para inyectar en cada HTML cmi5
CMI5_TRACKING_JS = r"""
<script>
// cmi5 launch parameters — el LMS los pasa por query string al lanzar el AU.
// La página, al cargar, envía un Statement "initialized" y al completar uno
// "completed"/"passed"/"failed". Esto es lo mínimo para que cualquier LMS
// cmi5-compliant registre el progreso.
(function() {
  var q = new URLSearchParams(window.location.search);
  var endpoint = q.get("endpoint");           // URL del LRS
  var fetchUrl = q.get("fetch");              // URL para obtener auth token
  var actorJSON = q.get("actor");             // JSON del actor
  var registration = q.get("registration");   // UUID de la sesión
  var activityId = q.get("activityId");       // ID del AU

  if (!endpoint || !activityId) { return; }   // no estamos en un LMS cmi5
  var actor = null;
  try { actor = JSON.parse(decodeURIComponent(actorJSON || "")); } catch(e) {}

  // Obtener token de autenticación
  var authToken = null;
  function getAuth(cb) {
    if (!fetchUrl) return cb(null);
    fetch(fetchUrl, { method: "POST" })
      .then(function(r) { return r.json(); })
      .then(function(d) { authToken = d["auth-token"]; cb(authToken); })
      .catch(function() { cb(null); });
  }

  function sendStatement(verbId, verbDisplay, extra) {
    if (!authToken || !actor) return;
    var stmt = {
      actor: actor,
      verb: { id: verbId, display: { "es": verbDisplay } },
      object: {
        id: activityId,
        definition: {
          type: "https://w3id.org/xapi/cmi5/activitytype/au",
          name: { "es": document.title }
        }
      },
      context: {
        registration: registration,
        contextActivities: {
          category: [{ id: "https://w3id.org/xapi/cmi5/context/categories/cmi5" }]
        }
      }
    };
    if (extra) { Object.assign(stmt, extra); }
    fetch(endpoint + "statements", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Experience-API-Version": "1.0.3",
        "Authorization": "Basic " + authToken
      },
      body: JSON.stringify(stmt)
    });
  }

  // CMI5 exige que cuando se inicia un AU se envíe un "initialized" antes
  // que cualquier otro statement.
  getAuth(function() {
    sendStatement(
      "http://adlnet.gov/expapi/verbs/initialized",
      "iniciado"
    );
  });

  // Exponer función para reportar completion desde el resto del JS
  window.cmi5Complete = function(score, passed) {
    sendStatement(
      "http://adlnet.gov/expapi/verbs/completed",
      "completado",
      score != null ? {
        result: {
          score: { scaled: Math.max(0, Math.min(1, score / 100)) },
          completion: true,
          success: !!passed
        }
      } : { result: { completion: true } }
    );
    if (score != null) {
      sendStatement(
        passed ? "http://adlnet.gov/expapi/verbs/passed" : "http://adlnet.gov/expapi/verbs/failed",
        passed ? "aprobado" : "suspendido",
        { result: { score: { scaled: score / 100 }, success: !!passed } }
      );
    }
  };

  // Antes de cerrar la pestaña, terminamos la sesión cmi5
  window.addEventListener("beforeunload", function() {
    if (authToken) {
      sendStatement(
        "http://adlnet.gov/expapi/verbs/terminated",
        "terminado"
      );
    }
  });
})();
</script>
"""


def _xml_escape_cmi5(text: str) -> str:
    return _xml_escape_2004(text)


def _adapt_html_for_cmi5(html: str, mastery: int) -> str:
    """Adapta el HTML del SCORM para cmi5: neutraliza llamadas SCORM y
    añade el JS de tracking xAPI. Cuando el alumno termina, llama a
    cmi5Complete(score, passed) en lugar de a SCORM.LMSCommit."""
    # Neutralizar llamadas SCORM (como en HTML standalone)
    cleaned = _strip_scorm_calls(html)
    # Inyectar JS cmi5 antes de </body>
    if "</body>" in cleaned:
        cleaned = cleaned.replace("</body>", CMI5_TRACKING_JS + "\n</body>", 1)
    else:
        cleaned += CMI5_TRACKING_JS
    # Reemplazar la función "finalizarTema" para que llame a cmi5Complete.
    # En el JS existente hay `if (typeof SCORM !== 'undefined')...` que ya
    # se ha neutralizado por _strip_scorm_calls. Añadimos un override.
    override = """
<script>
// Override v0.5 Fase 5: cuando se completa el tema desde la UI,
// también informar a cmi5 si el JS de tracking está activo.
(function() {
  var origFinalizar = window.finalizarTema;
  window.finalizarTema = function() {
    if (typeof origFinalizar === "function") origFinalizar();
    if (typeof window.cmi5Complete === "function" && typeof ProgresoVista !== "undefined") {
      try {
        var f = ProgresoVista.finalScore();
        var passed = ProgresoVista.passed();
        window.cmi5Complete(f, passed);
      } catch(e) { window.cmi5Complete(null, false); }
    }
  };
})();
</script>
"""
    if "</body>" in cleaned:
        cleaned = cleaned.replace("</body>", override + "\n</body>", 1)
    else:
        cleaned += override
    return cleaned


def export_cmi5(course, htmls: Dict[int, str], output_zip: Path,
                recursos_dir: Optional[Path] = None) -> Path:
    """Empaqueta el curso completo como un paquete cmi5 (xAPI).

    Estructura:
    - cmi5.xml: courseStructure con un AU por tema
    - tema_NN_<slug>.html: HTML adaptado con JS xAPI
    - recursos/: recursos compartidos

    El paquete se sube a un LMS cmi5-compliant (Moodle 4+ tiene plugin,
    SCORM Cloud, Watershed, Learning Locker, etc.). El LMS lanza cada AU
    con los parámetros estándar (endpoint, fetch, actor, registration,
    activityId) y la página los lee del query string para reportar.
    """
    output_zip = Path(output_zip)
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    work = output_zip.parent / f"_{output_zip.stem}_cmi5_build"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    md = course.metadata
    course_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", md.title.lower())[:40] or "curso"
    # cmi5 exige IDs como URIs absolutos (publisher-controlled).
    # Usamos un esquema "urn:cmi5:" para que sean únicos sin requerir un dominio.
    course_id = f"urn:cmi5:course:{course_slug}"

    # 1) HTMLs adaptados + AUs
    au_blocks: List[str] = []
    for topic in course.topics:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", topic.title.lower())[:40] or f"tema_{topic.number}"
        filename = f"tema_{topic.number:02d}_{slug}.html"
        adapted = _adapt_html_for_cmi5(htmls.get(topic.number, ""), md.mastery)
        (work / filename).write_text(adapted, encoding="utf-8")

        au_id = f"urn:cmi5:au:{course_slug}:t{topic.number:02d}"
        # moveOn=Passed si hay quiz (debe pasar), CompletedOrPassed si no
        move_on = "Passed" if topic.quiz else "Completed"
        au_blocks.append(CMI5_AU_TEMPLATE.format(
            au_id=au_id,
            move_on=move_on,
            mastery=f"{max(0, min(100, md.mastery)) / 100:.2f}",
            title=_xml_escape_cmi5(topic.title),
            description=_xml_escape_cmi5(
                f"Tema {topic.number} del curso '{md.title}'."
            ),
            url=filename,
        ))

    # 2) cmi5.xml
    cmi5_xml = CMI5_XML_TEMPLATE.format(
        course_id=course_id,
        title=_xml_escape_cmi5(md.title),
        description=_xml_escape_cmi5(md.subtitle or f"Curso: {md.title}"),
        au_blocks="".join(au_blocks),
    )
    (work / "cmi5.xml").write_text(cmi5_xml, encoding="utf-8")

    # 3) Recursos
    if recursos_dir and Path(recursos_dir).exists():
        target = work / "recursos"
        target.mkdir(exist_ok=True)
        for f in Path(recursos_dir).iterdir():
            if f.is_file():
                shutil.copy2(f, target / f.name)

    # 4) Empaquetar
    if output_zip.exists():
        output_zip.unlink()
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in work.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(work)))
    shutil.rmtree(work)
    return output_zip
