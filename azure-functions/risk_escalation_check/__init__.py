import json
import azure.functions as func

from backend.common import get_openai_client, verify_signature


async def check(message: str) -> str | None:
    client = get_openai_client()
    resp = await client.moderations.create(input=message)
    cats = resp.results[0].categories
    if cats.self_harm:
        return "self-harm"
    if cats.violence:
        return "violence"
    return None


async def main(req: func.HttpRequest) -> func.HttpResponse:
    sig = req.headers.get("OpenAI-Signature")
    if not verify_signature(req.get_body(), sig):
        return func.HttpResponse("forbidden", status_code=403)
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse("invalid json", status_code=400)
    flag = await check(str(payload.get("message", "")))
    body = json.dumps({"status": "ok", "flag": flag})
    return func.HttpResponse(body, mimetype="application/json")
