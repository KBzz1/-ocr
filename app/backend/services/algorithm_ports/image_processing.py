class ImageProcessingPort:
    def process(self, input: dict) -> dict:
        raise NotImplementedError


class OriginalImagePassthroughPort(ImageProcessingPort):
    """Use uploaded originals directly when OCR module owns image handling."""

    def process(self, input: dict) -> dict:
        return {"processed_path": input["original_path"]}
