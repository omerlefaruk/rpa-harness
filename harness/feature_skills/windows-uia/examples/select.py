def main(payload):
    return {"selector": payload.get("selector", "automation_id"), "interactive_windows_required": True}
