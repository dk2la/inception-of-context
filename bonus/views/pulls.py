"""GET /bonus/pulls, POST /bonus/pulls/{number}/merge and POST /bonus/pulls/{number}/close."""
from fastapi import APIRouter, HTTPException

from bonus.schemas.requests import MergeRequest
from bonus.services.pull_request import pull_request_service


class PullsView:
    def __init__(self, pull_request_service):
        # debug: three routes. A pull request is opened by POST /bonus/patch {"pull_request": true}.
        self.pull_request_service = pull_request_service
        self.router = APIRouter()
        self.router.add_api_route("/bonus/pulls", self.list, methods=["GET"])
        self.router.add_api_route("/bonus/pulls/{number}/merge", self.merge, methods=["POST"])
        self.router.add_api_route("/bonus/pulls/{number}/close", self.close, methods=["POST"])

    def found(self, number, result):
        # debug: result None -> 404 {"detail": "no pull request #99"}
        if result is None:
            raise HTTPException(status_code=404, detail=f"no pull request #{number}")
        return result

    def list(self):
        # debug: GET /bonus/pulls -> [{"number": 2, "state": "open", ...}, {"number": 1, "state": "merged", ...}]
        return self.pull_request_service.list()

    def merge(self, number: int, req: MergeRequest | None = None):
        # debug: POST /bonus/pulls/1/merge {"git_commit": false} -> status "success", pull.state "merged", git None
        git_commit = req.git_commit if req else True
        return self.found(number, self.pull_request_service.merge(number, git_commit))

    def close(self, number: int):
        # debug: POST /bonus/pulls/1/close -> {"number": 1, "state": "closed", ...}
        return self.found(number, self.pull_request_service.close(number))


pulls_view = PullsView(pull_request_service)
