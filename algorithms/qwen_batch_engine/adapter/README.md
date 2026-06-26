# Qwen Batch Engine Adapter

This adapter is the only stable interface between the workstation backend and the synced upstream batch pipeline.

Allowed responsibilities:

- validate `manifest.json`
- prepare job directories
- call the configured upstream runner
- normalize `merged_ocr.txt`, `merged_structured.json`, `anchors.json`, and `summary.json`
- write `result.json` or `error.json`

Forbidden responsibilities:

- infer medical field values from OCR text
- remap Qwen Chinese nested fields back to the legacy 61-field schema as the default path
- swallow upstream errors and return empty success
- log OCR full text, image base64, prompt full text, patient names, or full model output in ordinary logs
