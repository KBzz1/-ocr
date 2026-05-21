import json


class LlmClient:
    def complete_json(self, prompt: str):
        raise NotImplementedError


def parse_json_response(content: str):
    return json.loads(content)
