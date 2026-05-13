"""最小图片 bytes helpers — 不提交真实病历图片。"""

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 128
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
PDF_BYTES = b"%PDF-1.4 not image"
