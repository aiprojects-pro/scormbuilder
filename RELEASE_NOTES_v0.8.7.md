# SCORM Builder v0.8.7 — Release notes

**Fecha**: 7 agosto 2026
**Zip**: `scormbuilder-main-PARCHEADO_v0.8.7.zip`
**SHA-256**: `f5068073ddbad2980499d453a16e0adcc8b886d19bdc17061963805e87f37edd`

Incluye TODO lo de v0.8.6 (optimización costes IA) y v0.8.5 (parser).

---

## Fix aplicado (#81): list items numerados confundidos con headings

### Síntoma

Un docx con listas numeradas Word (elementos "64.", "65.", "66.", "67."...)
producía SCORMs donde esos items aparecían como subapartados propios (h2),
rompiendo la estructura del tema. Por ejemplo, en `Tema 1. Entrevistas 2.docx`:

- El apartado "5. Garantías científicas" contenía una lista con reglas
  numeradas hasta 67.
- Las reglas 64, 65, 66, 67 (con textos <150 chars) matchearon el patrón
  `HEADING2_SIMPLE_PATTERN` introducido en v0.8.5.
- El editor mostraba subapartados "fantasma": `10.20 Si se requiere...`,
  `10.21 Si es pertinente...`.

### Causa raíz

En v0.8.5 añadí un fallback textual para docx sin estilos Heading, que
aceptaba el patrón `N. Título` con guarda de longitud ≤150 caracteres.
Ese umbral era demasiado permisivo: items de listas numeradas <150 chars
también matcheaban.

### Fix

En `libreria/scorm_builder/parser.py`, `_looks_like_heading2()` añade:

- **Longitud ≤ 100** (era 150): los headings reales son cortos.
- **N ≤ 15**: los subapartados de un tema rara vez pasan de 15; las listas
  numeradas de Word pueden llegar a 60, 70...
- **Rechazar citas académicas al final**: `(Autor, año)` o `(Autor, año, p. NN)`.
- **Rechazar `»`**: cierre de cita textual, típico de reglas de manual.
- **Rechazar `Apellido (Año)` en medio**: `Vieira (2005) define...` es
  una oración con cita, no un heading.

### Verificación

Todos los casos del bug ahora rechazan correctamente:

```text
'66. Si se requiere intervención...' (141 chars, N=66)    → NOT heading ✓
'67. Si es pertinente...» (Fernández, 2013)'              → NOT heading ✓
```

Y los subapartados legítimos siguen detectándose:

```text
'1. Introducción y objetivos'         → heading ✓
'7. Referencias bibliográficas.'      → heading ✓
'1.1 Sub-sub'                         → heading ✓
```

E2E con el docx real `Tema 1. Entrevistas 2.docx`: **7 subapartados
correctos**, ningún h2 fantasma.

### Sin regresión

- Docx con estilos Heading reales (plantilla `test_v05.docx`) siguen OK.
- Docx del bug #80 (`Tema 1. Entrevistas.docx`) siguen detectando los 7
  subapartados correctos.
- v0.8.6 (model tiering + caching + Batch API): sin tocar.

---

## Auditoría

**17/17 checks OK**:
- Sintaxis de los 28 .py
- Regresión #80 (docx del Tema 1)
- Fix #81 (docx Tema 1 v2 con listas numeradas)
- Regresión plantilla (docx con Heading estilos reales)
- Imports v0.8.6 (Haiku, batch)
- Casuística exhaustiva de `_looks_like_heading2`
- E2E completo: parse + render + SCORM ZIP con 7 h2 correctos

---

## Cómo desplegar

```bash
unzip scormbuilder-main-PARCHEADO_v0.8.7.zip
cd scormbuilder-main
./deploy/deploy.sh
```

Sin cambios en config, env vars ni manifiestos OpenShift.

---

## Rollback si algo falla

Este fix solo toca la función `_looks_like_heading2()` en `parser.py`.
Para deshacer: revertir al patrón v0.8.5 (solo guarda de longitud ≤150).
El resto del código (v0.8.6 tiering, caching, batch) no depende de este
cambio y puede quedarse intacto.
