"""字段级复核器：对抽取结果做 LLM 二次审查，输出 verdict 意见。

- 复核范围：status=found 且 value 非空 的字段（not_found / 空值由审核页兜底）。
- 失败语义：LLM 失败 / 输出非 JSON / verdict 契约非法 → 静默降级为空意见，
  绝不抛出、绝不导致任务失败、绝不修改抽取结果的值。
- 输出映射（apply_verdicts）：suspicious/fail → quality_flags(verifier_suspicious)
  + verification_status=suspicious + attention_required + 规则化 message。
"""
import json
import logging

logger = logging.getLogger(__name__)

_ALLOWED_VERDICTS = {"pass", "suspicious", "fail"}


class FieldVerifier:
    def __init__(self, llm_client, append_reminder: bool = False):
        self._llm_client = llm_client
        self._append_reminder = append_reminder

    def verify(self, candidates: list[dict], document_text: str = "") -> list[dict]:
        """对 found + value 非空的字段执行复核，返回其意见列表；失败降级为空列表。

        返回的 verdict 只保留复核范围内字段（status=found 且 value 非空）；
        LLM 对范围外字段的输出按静默降级过滤。
        """
        targets = [
            c for c in candidates
            if isinstance(c, dict)
            and c.get("status") == "found"
            and (c.get("value") or "").strip()
        ]
        if not targets:
            return []
        try:
            from .prompts import build_verification_messages

            evidence_units = _collect_evidence(targets, document_text)
            fields = [
                {
                    "field_key": c.get("field_key", ""),
                    "value": c.get("value", ""),
                    "evidence_ids": c.get("evidence_ids") or [],
                }
                for c in targets
            ]
            system, user = build_verification_messages(
                evidence_units, fields, append_reminder=self._append_reminder
            )
            payload = self._llm_client.complete_json(user, system_prompt=system)
        except Exception:  # noqa: BLE001 — 复核器失败必须静默降级
            logger.warning("复核器调用失败，已降级为空意见", exc_info=True)
            return []
        target_keys = {c.get("field_key") for c in targets}
        return [v for v in _parse_verdicts(payload) if v.get("field_key") in target_keys]


def _collect_evidence(candidates: list[dict], document_text: str) -> list[dict]:
    """聚合候选字段的 evidence（去重保序），超长时以 document_text 兜底。"""
    seen: set[str] = set()
    units: list[dict] = []
    for c in candidates:
        for ev in c.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            key = ev.get("id") or ev.get("text") or ""
            if key and key not in seen:
                seen.add(key)
                units.append({"id": ev.get("id") or f"e{len(units) + 1:03d}", "text": ev.get("text", "")})
    if not units and document_text:
        # evidence 缺失时用原文全文兜底，保证复核器仍有事实可依
        units.append({"id": "doc", "text": document_text[:8000]})
    return units


def _clip_comment(comment) -> str:
    """comment 限制 40 字符；截断时保持引号成对、不切出半句残片。

    LLM 输出的 comment 可能超长（契约要求 ≤40 汉字），直接切片会切在
    引号中间（如"应为'…"），导致人工读不懂。截断后若引号不成对，
    回退到最后一个成对引号之后，再补省略号。
    """
    text = str(comment or "")
    if len(text) <= 40:
        return text
    clipped = text[:40]
    if clipped.count("'") % 2 == 1:
        last_pair = clipped.rfind("'")
        if last_pair > 0:
            clipped = clipped[:last_pair]
    return clipped + "…"


def _parse_verdicts(payload) -> list[dict]:
    """容错解析 LLM 输出；任何异常/非法项跳过，不抛出。"""
    if not isinstance(payload, dict):
        try:
            payload = json.loads(payload) if isinstance(payload, str) else None
        except (json.JSONDecodeError, TypeError):
            logger.warning("复核器输出非 JSON，已降级为空意见")
            return []
    verifications = payload.get("verifications") if isinstance(payload, dict) else None
    if not isinstance(verifications, list):
        return []
    verdicts = []
    for item in verifications:
        if not isinstance(item, dict):
            continue
        verdict = item.get("verdict")
        if verdict not in _ALLOWED_VERDICTS:
            continue
        verdicts.append({
            "field_key": item.get("field_key", ""),
            "verdict": verdict,
            "reason_code": item.get("reason_code") or "none",
            "checks": item.get("checks") or {},
            "comment": _clip_comment(item.get("comment")),
        })
    return verdicts


def apply_verdicts(candidates: list[dict], verdicts: list[dict]) -> list[dict]:
    """把复核意见合并进候选字段：suspicious/fail → 标记 + verification_status 升为 suspicious。

    不修改字段值；verification_status 已是 failed 的字段不降级。
    """
    by_key = {c.get("field_key"): c for c in candidates if isinstance(c, dict)}
    for v in verdicts:
        field = by_key.get(v.get("field_key"))
        if field is None:
            continue
        if v.get("verdict") not in ("suspicious", "fail"):
            continue
        flags = field.setdefault("quality_flags", [])
        if not any(f.get("flag") == "verifier_suspicious" for f in flags if isinstance(f, dict)):
            flags.append({
                "flag": "verifier_suspicious",
                "severity": "warning",
                "message": v.get("comment") or "复核器标记，请核对原文",
            })
        if field.get("verification_status") != "failed":
            field["verification_status"] = "suspicious"
        field["attention_required"] = True
        field["attention_message"] = "复核器标记，请核对原文"
    return candidates
