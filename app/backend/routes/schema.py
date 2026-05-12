from flask import Blueprint, current_app
from ..responses import success

schema_bp = Blueprint("schema", __name__)


@schema_bp.route("/api/schema/current")
def get_current_schema():
    service = current_app.config["SCHEMA_SERVICE"]
    schema = service.get_current()
    data = {
        "version": schema["version"],
        "document_type": schema["document_type"],
        "field_groups": [
            {
                "group_key": g["group_key"],
                "group_label": g["group_label"],
                "fields": [
                    {
                        "field_key": f["field_key"],
                        # key 别名用于前端字段匹配，值始终等于 field_key
                        "key": f["field_key"],
                        "label": f["label"],
                        "type": f["type"],
                        "required": f["required"],
                        "hint": f["hint"],
                    }
                    for f in g["fields"]
                ],
            }
            for g in schema["field_groups"]
        ],
    }
    return success(data=data)
