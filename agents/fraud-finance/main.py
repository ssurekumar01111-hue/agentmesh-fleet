import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import FraudFinanceAgent
from telemetry import init_tracer

app = FastAPI(title="AgentMesh Fraud & Finance Agent", version="1.0.0")
tracer = init_tracer("agentmesh-fraud-finance", app=app)
agent = FraudFinanceAgent()

class InvestigationRequest(BaseModel):
    invoiceId: str

class ResumeRequest(BaseModel):
    workflowId: str

@app.post("/investigate")
async def investigate_invoice(req: InvestigationRequest):
    with tracer.start_as_current_span("Investigate Invoice Workflow") as span:
        span.set_attribute("invoiceId", req.invoiceId)
        try:
            res = await agent.process_invoice(req.invoiceId)
            span.set_attribute("workflowStatus", res.get("workflowStatus", "unknown"))
            return res
        except Exception as e:
            span.record_exception(e)
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/resume")
def resume_workflow(req: ResumeRequest):
    with tracer.start_as_current_span("Resume Workflow Transition") as span:
        span.set_attribute("workflowId", req.workflowId)
        try:
            res = agent.resume_workflow(req.workflowId)
            span.set_attribute("workflowStatus", res.get("status", "unknown"))
            return res
        except Exception as e:
            span.record_exception(e)
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "service": "agentmesh-fraud-finance"}
