import json
import azure.functions as func

from backend.common import verify_signature


def score(data: dict) -> dict:
    categories = ["symptoms", "duration", "severity", "triggers", "meds"]
    score = sum(1 for k in categories if data.get(k))
    return {"enough_data": score >= 3, "score": score}


def main(req: func.HttpRequest) -> func.HttpResponse:
    sig = req.headers.get("OpenAI-Signature")
    if not verify_signature(req.get_body(), sig):
        return func.HttpResponse("forbidden", status_code=403)
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse("invalid json", status_code=400)
    result = score(payload)
    result["status"] = "ok"
    return func.HttpResponse(
        json.dumps(result),
        mimetype="application/json"
    )
