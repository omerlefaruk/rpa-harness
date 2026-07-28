def main(payload):
    return {"revision": payload.get("revision"), "mutable_source": False, "secret_values": False}
