from flask import jsonify


def success(data=None, status=200):
    resp = jsonify({"success": True, "data": data})
    resp.status_code = status
    return resp


def error_response(app_error):
    resp = jsonify({
        "error": {
            "code": app_error.code,
            "message": app_error.message,
            "details": app_error.details,
        }
    })
    resp.status_code = app_error.http_status
    return resp
