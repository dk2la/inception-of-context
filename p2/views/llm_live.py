"""GET /llm/live: what the local model is writing right now, as Server-Sent Events."""
import json
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from p1.core.llm import llm_client


class LLMLiveView:
    def __init__(self, llm_client):
        # debug: registers GET /llm/live. The 3D View opens it with new EventSource("/llm/live").
        self.llm_client = llm_client
        self.router = APIRouter()
        self.router.add_api_route("/llm/live", self.live, methods=["GET"])

    def updates(self, sent):
        """The messages this connection has not had yet. sent is {model: (id, characters sent, done sent)}."""
        # debug: sent == {} and the coder has written '{"summary": "a' so far:
        #   return == [{"model": "qwen2.5-coder:3b", "id": 3, "reset": True, "delta": '{"summary": "a',
        #               "done": False, "error": None}]
        # next call, 5 more characters: reset False, delta is those 5. Nothing new: return == [].
        # a new call of the same model has a new id: reset True and the whole text again.
        messages = []
        for state in self.llm_client.live_snapshot():
            last_id, length, done = sent.get(state["model"], (None, 0, False))
            reset = state["id"] != last_id
            if reset:
                length, done = 0, False
            delta = state["text"][length:]
            if reset or delta or state["done"] != done:
                messages.append({"model": state["model"], "id": state["id"], "reset": reset, "delta": delta,
                                 "done": state["done"], "error": state["error"]})
                sent[state["model"]] = (state["id"], len(state["text"]), state["done"])
        return messages

    def stream(self):
        """Send what changed five times a second. The comment line lets the server notice a closed tab."""
        sent = {}
        while True:
            for message in self.updates(sent):
                yield "data: " + json.dumps(message) + "\n\n"
            yield ": waiting\n\n"
            time.sleep(0.2)

    def live(self):
        # debug: return is a StreamingResponse, media_type == "text/event-stream". It stays open.
        return StreamingResponse(self.stream(), media_type="text/event-stream")


llm_live_view = LLMLiveView(llm_client)
