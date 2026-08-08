import os
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from agent import ComplianceAgent
from telemetry import init_tracer

app = FastAPI(title="AgentMesh Compliance Agent", version="1.0.0")
tracer = init_tracer("agentmesh-compliance", app=app)
agent = ComplianceAgent()

class WorkflowReviewRequest(BaseModel):
    workflowId: str = "wf-inv-2026-007"

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "agentmesh-compliance"}

@app.post("/review")
def review_workflow(req: WorkflowReviewRequest):
    with tracer.start_as_current_span("Review Workflow Compliance") as span:
        span.set_attribute("workflowId", req.workflowId)
        try:
            res = agent.review_workflow_compliance(req.workflowId)
            span.set_attribute("assessmentDecision", res.get("assessmentDecision", "unknown"))
            return {"status": "success", "data": res}
        except Exception as e:
            span.record_exception(e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/test-denied")
def test_denied_access():
    with tracer.start_as_current_span("Test Denied Access Check") as span:
        try:
            res = agent.test_hr_data_access()
            span.set_attribute("policyDecision", "denied" if res.get("status_code") in (403, 401) or not res.get("success") else "allowed")
            return {"status": "completed", "gatewayResponse": res}
        except Exception as e:
            span.record_exception(e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
