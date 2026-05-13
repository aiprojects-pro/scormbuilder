# SCORM Builder

> Convierte documentos Word en cursos SCORM con tu marca, en minutos.

Este repositorio contiene el **motor** que genera paquetes SCORM 1.2 a partir de archivos `.docx` que siguen una convención sencilla. Es el núcleo de la plataforma SaaS en construcción y también funciona como herramienta de línea de comandos para uso personal.

> **Versión 0.5** (Fases 1 → 5, completa) — **Fase 1**: extracción automática de imágenes, hipervínculos preservados, YouTube embebido, PDF descargable, WCAG 2.1 AA. **Fase 2**: IA centralizada, tags por tema, quizzes mixtos (test / V-F / huecos), exporter IMS CP, banco Aiken extendido por IA. **Fase 3**: UI completa en editor para endpoints IA. **Fase 4**: alt-text IA por imagen, modal WCAG, vista previa en iframe. **Fase 5**: enriquecer Word desordenado con callouts IA, plantilla Word moderna descargable, exporter cmi5/xAPI, comparador antes/después por snapshots, detección de copyright en imágenes. Ver [`MEJORAS_v0.5.md`](MEJORAS_v0.5.md), [`MEJORAS_v0.5_fase2.md`](MEJORAS_v0.5_fase2.md), [`MEJORAS_v0.5_fase3.md`](MEJORAS_v0.5_fase3.md), [`MEJORAS_v0.5_fase4.md`](MEJORAS_v0.5_fase4.md) y [`MEJORAS_v0.5_fase5.md`](MEJORAS_v0.5_fase5.md).
>
> **Versión 0.4** — Asistente IA en el editor (reescritura, objetivos, resumen, glosario, ilustraciones), validador WCAG 2.1 AA, subtítulos automáticos para vídeos (Whisper), narración TTS, modo constructor visual completo, exports HTML standalone y SCORM 2004. Ver [`MEJORAS_v0.4.md`](MEJORAS_v0.4.md).
>
> **Versión 0.3** — Sistema de puntuación ponderada (visualización + quiz), edición desde la app sin volver al Word, vista previa antes de empaquetar y generación de quiz por IA. Ver [`MEJORAS_v0.3.md`](MEJORAS_v0.3.md).
>
> **Versión 0.2** — Recursos multimedia completos (imágenes, vídeo, audio, YouTube, descargables), sistema de cuentas multi-usuario y biblioteca personal de cursos. Ver [`MEJORAS_v0.2.md`](MEJORAS_v0.2.md).

## Estructura del proyecto

```
scorm_builder_proyecto/
├── docs/                          # Documentación de visión y convenciones
│   ├── 01_vision_producto.md      # Documento de visión del producto SaaS
│   ├── 02_convencion_docx.md      # Reglas de cómo se interpreta un DOCX
│   └── 03_guia_instalacion.md     # Cómo instalarlo en tu ordenador
├── libreria/                      # El motor Python
│   ├── scorm_builder/             # Código fuente de la librería
│   │   ├── __init__.py
│   │   ├── parser.py              # DOCX → estructura intermedia (JSON)
│   │   ├── renderer.py            # Estructura → HTML
│   │   ├── packager.py            # HTML → SCORM válido (ZIP)
│   │   ├── pdf_builder.py         # Estructura → PDF descargable
│   │   ├── aiken_builder.py       # Estructura → banco Aiken (.txt)
│   │   ├── themes.py              # Paletas y configuración visual
│   │   └── cli.py                 # Línea de comandos
│   ├── tests/                     # Tests automáticos
│   ├── pyproject.toml             # Configuración del paquete Python
│   └── README.md
├── plantilla/                     # Plantilla DOCX para clientes
│   ├── Plantilla_Curso_SCORM.docx
│   └── generar_plantilla.py
└── landing/                       # Landing de validación de mercado
    └── README.md
```

## Inicio rápido

### Si tienes Python 3.10+ instalado:

```bash
cd libreria
pip install -e .
scorm-builder generar mi_curso.docx --output mi_curso.zip
```

### Si NO tienes Python:

Lee `docs/03_guia_instalacion.md` para una guía paso a paso según tu sistema operativo.

## Roadmap

Consulta `docs/01_vision_producto.md` para el plan completo del producto.

## Licencia

Propietaria. Todos los derechos reservados.
