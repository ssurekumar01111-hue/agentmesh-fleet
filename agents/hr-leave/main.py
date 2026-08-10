import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import HRLeaveAgent
from telemetry import init_tracer

app = FastAPI(
    title="AgentMesh HR Leave Assistant Agent",
    version="1.0.0",
    description="Reviews employee leave requests against Northbridge Retail Co. HR policy via Gemini reasoning.",
)
tracer = init_tracer("agentmesh-hr-leave", app=app)
agent = HRLeaveAgent()


class LeaveReviewRequest(BaseModel):
    requestId: str


@app.post("/review")
async def review_leave_request(req: LeaveReviewRequest):
    """Submit a leave request for HR policy review.

    The agent fetches the leave request from Firestore via Gateway, runs ADK Runner,
    writes Memory, and escalates to 'waiting_approval' if FLAGGED or ESCALATED.
    """
    with tracer.start_as_current_span("Review Leave Request Workflow") as span:
        span.set_attribute("requestId", req.requestId)
        try:
            res = await agent.process_leave_request(req.requestId)
            span.set_attribute("assessmentStatus", res.get("assessmentStatus", "unknown"))
            span.set_attribute("workflowStatus", res.get("workflowStatus", "unknown"))
            span.set_attribute("riskScore", res.get("riskScore", -1))
            return res
        except Exception as e:
            span.record_exception(e)
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok", "service": "agentmesh-hr-leave"}
