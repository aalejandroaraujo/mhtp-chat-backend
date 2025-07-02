import json
import azure.functions as func

from backend.common import nocodb_upsert, verify_signature


async def main(req: func.HttpRequest) -> func.HttpResponse:
    sig = req.headers.get("OpenAI-Signature")
    if not verify_signature(req.get_body(), sig):
        return func.HttpResponse("forbidden", status_code=403)
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse("invalid json", status_code=400)
    session_id = str(payload.get("session_id"))
    summary = str(payload.get("summary", ""))
    try:
        await nocodb_upsert(session_id, summary)
    except Exception:
        return func.HttpResponse("db error", status_code=500)
    body = json.dumps({"status": "ok"})
    return func.HttpResponse(body, mimetype="application/json")
