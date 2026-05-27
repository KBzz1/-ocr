manzufei OCR offline Docker bundle

Prerequisites on the target Windows computer:
1. Docker Desktop is installed.
2. WSL2 is enabled.
3. Docker Desktop is running.
4. For GPU OCR/LLM, NVIDIA driver and Docker GPU support are available.

First-time setup:
1. Copy this whole folder from the USB drive to the target computer.
2. Double-click 00_import_image.bat.
3. Double-click 01_start.bat.
4. Open http://127.0.0.1:8081/ if the browser does not open automatically.

Daily use:
1. Start Docker Desktop.
2. Double-click 01_start.bat.
3. Double-click 02_stop.bat when finished.

Logs:
- Double-click 03_logs.bat to watch container logs.
- Runtime logs are also written under the logs folder.
- 00_import_image.bat and 01_start.bat write troubleshooting logs under
  deploy_debug_logs. If startup, Docker, or GPU detection fails, send the whole
  deploy_debug_logs folder for debugging.

Data folders:
- data: uploaded files and processing results.
- exports: exported files.
- logs: local logs.
- models: OCR and LLM model files.

The offline bundle intentionally does not include AGENTS.md, CLAUDE.md, .git,
development docs, tests, frontend source files, node_modules, or cached runtime data.
