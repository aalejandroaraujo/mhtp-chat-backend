import json
import azure.functions as func

from backend.common import verify_signature


def main(req: func.HttpRequest) -> func.HttpResponse:
    sig = req.headers.get("OpenAI-Signature")
    if not verify_signature(req.get_body(), sig):
        return func.HttpResponse("forbidden", status_code=403)
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse("invalid json", status_code=400)
    new_mode = payload.get("requested_mode") or "default"
    body = json.dumps({"status": "ok", "new_mode": new_mode})
    return func.HttpResponse(body, mimetype="application/json")
