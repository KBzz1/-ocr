"""Shared judgement normal/abnormal inference rules.

Used by both the backend review service and the Qwen batch engine adapter to
keep normal/negative judgement text patterns consistent across code paths.
"""

import re

# 正常/阴性判定文本 — 来自 Qwen J 字段的医学表述惯例。
# 新增模式时需同时更新 tests，避免简单子串误判。
NORMAL_JUDGEMENT_PATTERNS: tuple[str, ...] = (
    "正常",
    "无异常",
    "未见异常",
    "无压痛",
    "无肿大",
    "无充血",
    "无水肿",
    "无黄染",
    "无分泌物",
    "未闻及病理性杂音",
    "未触及包块",
    "未扪及包块",
    "未触及明显",
    "未扪及肿大",
    "心律规则",
    "心音正常",
    "未闻及杂音",
    "阴性",
)

# 短模式（≤2 字符）：必须由标点/空白/字符串边界界定，防止子串误判。
# 例如 "正常" 不得在 "肺动脉压正常范围上限" 中命中。
_SHORT_PATTERNS: frozenset[str] = frozenset({"正常", "阴性"})

# 中文/英文标点和空白字符，用作模式边界
_BOUNDARY_CHARS = "，。；;、,：:！？!?（）()\n\r\t "


def matches_normal_judgement(text: str) -> bool:
    """Check whether *text* contains a medical normal/negative judgement indicator.

    Short patterns (≤2 chars, e.g. ``"正常"``, ``"阴性"``) are matched with
    punctuation/whitespace boundaries to prevent false positives like
    ``"肺动脉压正常范围上限"``.

    Longer patterns (3+ chars, e.g. ``"无压痛"``, ``"心律规则"``) use
    substring matching because they are specific enough to be unambiguous.
    """
    if not text or not text.strip():
        return False
    normalized = text.replace(" ", "")
    for pattern in NORMAL_JUDGEMENT_PATTERNS:
        if len(pattern) <= 2 and pattern in _SHORT_PATTERNS:
            escaped = re.escape(pattern)
            if re.search(
                rf"(?:^|[{re.escape(_BOUNDARY_CHARS)}]){escaped}(?:$|[{re.escape(_BOUNDARY_CHARS)}])",
                normalized,
            ):
                return True
        else:
            if pattern in normalized:
                return True
    return False
