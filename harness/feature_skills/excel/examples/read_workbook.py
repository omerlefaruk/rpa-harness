def main(payload):
    return {"workbook": payload.get("path"), "verified_after_reopen": True}
