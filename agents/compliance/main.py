import os
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from agent import ComplianceAgent

app = FastAPI(title="AgentMesh Compliance Agent", version="1.0.0")
agent = ComplianceAgent()

class WorkflowReviewRequest(BaseModel):
    workflowId: str = "wf-inv-2026-007"

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "agentmesh-compliance"}

@app.post("/review")
def review_workflow(req: WorkflowReviewRequest):
    try:
        res = agent.review_workflow_compliance(req.workflowId)
        return {"status": "success", "data": res}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/test-denied")
def test_denied_access():
    try:
        res = agent.test_hr_data_access()
        return {"status": "completed", "gatewayResponse": res}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
