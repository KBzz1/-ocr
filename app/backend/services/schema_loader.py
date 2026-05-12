import os
import yaml
from ..errors import AppError, ErrorCode

ALLOWED_FIELD_TYPES = {"string", "number", "date", "boolean"}


def load_schema(path: str) -> dict:
    """加载并校验 YAML schema 文件。成功返回规范化 dict；失败抛 AppError。"""

    if not os.path.isfile(path):
        raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                       message="Schema 文件不存在",
                       details={"reason": "文件不存在"})

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError:
        raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                       message="Schema YAML 语法错误",
                       details={"reason": "YAML 语法错误"})

    if not isinstance(raw, dict):
        raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                       message="Schema 必须为 YAML mapping",
                       details={"reason": "不是 YAML mapping"})

    # version
    version = raw.get("version")
    if not isinstance(version, str) or not version.strip():
        raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                       message="Schema 缺少 version 字段",
                       details={"reason": "缺少 version 字段"})

    # document_type
    document_type = raw.get("document_type")
    if not isinstance(document_type, str) or not document_type.strip():
        raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                       message="Schema 缺少 document_type 字段",
                       details={"reason": "缺少 document_type 字段"})

    # field_groups
    field_groups = raw.get("field_groups")
    if not isinstance(field_groups, list) or len(field_groups) == 0:
        raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                       message="Schema field_groups 必须为非空列表",
                       details={"reason": "field_groups 不能为空"})

    seen_group_keys = set()
    seen_field_keys = set()
    normalized_groups = []

    for group in field_groups:
        if not isinstance(group, dict):
            raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                           message="field_group 必须为 dict",
                           details={"reason": "field_group 格式非法"})

        group_key = group.get("group_key")
        if not isinstance(group_key, str) or not group_key.strip():
            raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                           message="field_group 缺少 group_key",
                           details={"reason": "缺少 group_key"})

        group_label = group.get("group_label")
        if not isinstance(group_label, str) or not group_label.strip():
            raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                           message="field_group 缺少 group_label",
                           details={"reason": "缺少 group_label",
                                    "group_key": group_key})

        if group_key in seen_group_keys:
            raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                           message="field_group group_key 重复",
                           details={"reason": "group_key 重复",
                                    "group_key": group_key})
        seen_group_keys.add(group_key)

        fields = group.get("fields")
        if not isinstance(fields, list) or len(fields) == 0:
            raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                           message="field_group 的 fields 必须为非空列表",
                           details={"reason": "fields 不能为空",
                                    "group_key": group_key})

        normalized_fields = []
        for field in fields:
            if not isinstance(field, dict):
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field 必须为 dict",
                               details={"reason": "field 格式非法",
                                        "group_key": group_key})

            field_key = field.get("field_key")
            if not isinstance(field_key, str) or not field_key.strip():
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field 缺少 field_key",
                               details={"reason": "缺少 field_key",
                                        "group_key": group_key})

            label = field.get("label")
            if not isinstance(label, str) or not label.strip():
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field 缺少 label",
                               details={"reason": "缺少 label",
                                        "field_key": field_key})

            if field_key in seen_field_keys:
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field_key 重复",
                               details={"reason": "field_key 重复",
                                        "field_key": field_key})
            seen_field_keys.add(field_key)

            field_type = field.get("type", "string")
            if field_type not in ALLOWED_FIELD_TYPES:
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field type 非法",
                               details={"reason": "type 非法",
                                        "field_key": field_key,
                                        "type": field_type})

            required = field.get("required", False)
            if not isinstance(required, bool):
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field required 必须为 boolean",
                               details={"reason": "required 非法",
                                        "field_key": field_key})

            hint = field.get("hint", "")
            if not isinstance(hint, str):
                raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                               message="field hint 必须为 string",
                               details={"reason": "hint 非法",
                                        "field_key": field_key})

            normalized_fields.append({
                "field_key": field_key,
                "label": label,
                "type": field_type,
                "required": required,
                "hint": hint,
            })

        normalized_groups.append({
            "group_key": group_key,
            "group_label": group_label,
            "fields": normalized_fields,
        })

    return {
        "version": version,
        "document_type": document_type,
        "field_groups": normalized_groups,
    }
