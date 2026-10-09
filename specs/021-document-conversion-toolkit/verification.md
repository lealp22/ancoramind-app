# Verification: 021 — Document Conversion Toolkit

> **Status:** 🔶 Fase 1 implementada localmente (T1-T9, 2026-10-03); pendiente
> validación E2E con un PDF real de usuario vía Telegram (bloqueado por
> restricciones de infraestructura actuales)

## Incremento T1 — 2026-09-30

`has_extractable_text` clasifica bytes de PDF en memoria con PyMuPDF, sin
persistencia ni cliente LLM. Las pruebas crean PDFs con texto, página en blanco,
imagen sin texto, texto en página posterior, PDF vacío/corrupto y PDF cifrado.
Los documentos inválidos o cifrados devuelven error tipado. **La función aún no
se llama desde `analyze_document`: no modifica ingesta, costes ni ruta visual.**
No se instaló `pymupdf4llm` ni se declara completada Fase 1; siguen pendientes
T2–T9 y la coordinación de seguridad con BL-39 antes de activar el nuevo flujo.

Validación local: `python -m pytest tests/unit/ -q` → **551 passed**;
`python -m pytest tests/integration/ -q` → **71 skipped** (sin PostgreSQL);
`python -m ruff check src/ tests/ scripts/ migrations/` → limpio;
`python -m mypy src/` → limpio (107 módulos); `git diff --check` → limpio.

## Incremento T2-T9 — 2026-10-03

`extract_pdf_text_markdown` (PyMuPDF + `pymupdf4llm.to_markdown`, sin
`write_images`, sin I/O de disco) se cablea en `analyze_document`:
`has_extractable_text` decide la ruta antes de tocar el extraction port, y un
PDF con texto nunca pasa por `prepare_visual_pages`/visión. `DocumentService`
trata el texto extraído igual que el `text_preview` ya existente de `text/*`
(mismo `MAX_TEXT_PREVIEW_BYTES`, misma serialización JSON escapada de
BL-39/specs/022 — no es un control de autorización nuevo, solo reutiliza el
existente). Señal metadata-only `ancora.document.extraction_route` añadida al
allowlist de telemetría y emitida en cada extracción.

Decisiones documentadas en `tasks.md` T2/T5: el límite de páginas es el mismo
`document_vision_max_pdf_pages` que ya acotaba la ruta visual (sin tope
independiente); páginas sin texto en un PDF mixto simplemente no aportan
contenido (no hay política todo-o-nada, `has_extractable_text` ya decidió con
"cualquier página" que la ruta es aplicable).

Validación local:

```text
python -m pytest tests/unit/test_document_vision.py tests/unit/test_document_tools.py tests/unit/test_document_extraction_port.py -q
→ 43 passed

python -m pytest tests/unit/ -q
→ 693 passed

python -m ruff check src/ tests/ scripts/ migrations/
→ All checks passed

python -m mypy src/
→ Success: no issues found in 114 source files
```

`pytest tests/integration/` no se ejecutó (sin PostgreSQL/Docker disponible en
este incremento); el pipeline de persistencia de documentos no cambió de
forma, solo el contenido textual que llega a `_build_extraction_prompt`.
Pendiente confirmar cuando haya infraestructura disponible, junto con el
ensayo E2E real de un PDF con texto enviado por Telegram.

## Local verification required (al implementar Fase 1)

```powershell
.venv\Scripts\Activate.ps1
python -m pytest tests/unit/test_document_vision.py -q
python -m pytest tests/unit/test_document_tools.py -q
python -m pytest tests/unit/ -q
python -m pytest tests/integration/ -q
ruff check src/ tests/ scripts/ migrations/
mypy src/
```

## Pending acceptance evidence

- [x] Antes de activar la ruta PDF textual, BL-39/specs/022 valida filename y
      contenido PDF adversarial (`</document_data>`) con la representación JSON;
      el adjunto original entregado al Agent principal se incluye en ensayos de
      seguridad. El JSON no es un control de autorización. **La ruta PDF
      textual reutiliza la misma `_build_extraction_prompt`/serialización ya
      cubierta por los tests adversariales de `test_document_extraction_port.py`
      (closing-tag falso, unicode, truncado) — no introduce una función de
      escape nueva.**

- [x] Un PDF con capa de texto extraíble se procesa sin invocar el extraction
      port de visión (verificado por mock/spy en unit test), y la extracción
      persistida en `ai_extractions` es equivalente en forma a la ruta visual
      existente.
- [x] Un PDF escaneado (sin texto) sigue exactamente el comportamiento actual
      (ruta `ancoramind-vision`), sin cambios de resultado ni de coste.
- [x] Un PDF con páginas mixtas (algunas con texto, algunas sin) se comporta
      según la política documentada en `tasks.md` T2, con test que la cubre.
- [x] `pymupdf4llm` está declarado en `pyproject.toml` con licencia confirmada
      y rango de versión compatible con `PyMuPDF`.
- [x] `pytest tests/unit/`, `ruff check` y `mypy src/` en verde.
      `pytest tests/integration/` pendiente de infraestructura (no requerido
      por este incremento: no cambia el pipeline de persistencia).
- [x] `BACKLOG.md` (BL-38, BL-6) actualizado referenciando este spec al cerrar
      la Fase 1.
- [ ] Ensayo E2E real: un PDF con capa de texto enviado por un usuario real vía
      Telegram usa la ruta determinista (sin llamada de visión) y la extracción
      llega correctamente. Bloqueado por las restricciones de infraestructura
      actuales — pendiente de validación por el propietario.

## Incremento — Límite de páginas desacoplado (2026-10-10)

El cierre de T2/T5 (incremento T2-T9) había dejado deliberadamente
`extract_pdf_text_markdown` acotado al mismo `document_vision_max_pdf_pages`
que la ruta visual, para no introducir un tope independiente sin necesidad.
BL-6 seguía anotando como pendiente definir una política de páginas propia
para la ruta de texto. Se resuelve ahora: nuevo
`document_text_max_pdf_pages` (default 20, `ge=1, le=50`) en `src/config.py`,
independiente de `document_vision_max_pdf_pages` (default 3, sin cambios) —
justificado porque `extract_pdf_text_markdown` no invoca ningún LLM, así que
no comparte la razón de ser conservador que sí aplica a la ruta visual
(coste de inferencia por página). `analyze_document`
(`src/agent/tools/documents.py`) pasa ahora `document_text_max_pdf_pages` a
la rama determinista; la rama visual sigue usando
`document_vision_max_pdf_pages` sin cambios.

Validación local:

```text
python -m pytest tests/unit/test_document_tools.py tests/unit/test_config.py tests/unit/test_document_vision.py -q
→ 62 passed

python -m pytest tests/unit/ -q
→ 1114 passed

python -m ruff check src/ tests/ scripts/ migrations/
→ All checks passed

python -m mypy src/
→ Success: no issues found in 159 source files
```

4 tests nuevos: 3 en `test_config.py` (default independiente, override por
env var, rechazo fuera de rango) y 1 en `test_document_tools.py` (un PDF de
4 páginas con capa de texto se lee entero con el límite de visión fijado a 2,
confirmando que cada ruta usa su propio presupuesto).



- Fase 2 (DOCX determinista) y Fase 3 (Markdown → PDF export) no se verifican
  aquí: dependen de BL-35 y BL-29/decisión de diseño respectivamente, y tienen
  sus propios criterios de cierre en `tasks.md`.
