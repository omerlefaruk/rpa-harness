def main(payload):
    return {"credential": "${secrets.api_token}", "idempotency_key": payload.get("idempotency_key")}
