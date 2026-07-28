def main(payload):
    """Pure read-only worker example."""
    return {"intent": payload.get("intent", "discover"), "read_only": True}
