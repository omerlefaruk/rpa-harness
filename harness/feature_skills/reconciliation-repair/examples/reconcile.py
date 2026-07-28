def main(payload):
    return {"conclusion": payload.get("conclusion", "still_unknown"), "automatic_retry": False}
