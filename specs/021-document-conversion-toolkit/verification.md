# Verification: 021 — Document Conversion Toolkit

> **Status:** 🔶 Fase 1 parcial — solo detección local T1 (2026-09-30)

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

- [ ] Antes de activar la ruta PDF textual, BL-39/specs/022 valida filename y
      contenido PDF adversarial (`</document_data>`) con la representación JSON;
      el adjunto original entregado al Agent principal se incluye en ensayos de
      seguridad. El JSON no es un control de autorización.

- [ ] Un PDF con capa de texto extraíble se procesa sin invocar el extraction
      port de visión (verificado por mock/spy en unit test), y la extracción
      persistida en `ai_extractions` es equivalente en forma a la ruta visual
      existente.
- [ ] Un PDF escaneado (sin texto) sigue exactamente el comportamiento actual
      (ruta `ancoramind-vision`), sin cambios de resultado ni de coste.
- [ ] Un PDF con páginas mixtas (algunas con texto, algunas sin) se comporta
      según la política documentada en `tasks.md` T2, con test que la cubre.
- [ ] `pymupdf4llm` está declarado en `pyproject.toml` con licencia confirmada
      y rango de versión compatible con `PyMuPDF`.
- [ ] `pytest tests/unit/`, `pytest tests/integration/` (si aplica), `ruff
      check` y `mypy src/` en verde.
- [ ] `BACKLOG.md` (BL-38, BL-6) actualizado referenciando este spec al cerrar
      la Fase 1.

## Fuera de alcance de esta verificación

- Fase 2 (DOCX determinista) y Fase 3 (Markdown → PDF export) no se verifican
  aquí: dependen de BL-35 y BL-29/decisión de diseño respectivamente, y tienen
  sus propios criterios de cierre en `tasks.md`.
