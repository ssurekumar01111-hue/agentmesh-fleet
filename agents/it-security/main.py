import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import ITSecurityAgent
from telemetry import init_tracer

app = FastAPI(title="AgentMesh IT & Security Agent", version="1.0.0")
tracer = init_tracer("agentmesh-it-security", app=app)
agent = ITSecurityAgent()

class AuditRequest(BaseModel):
    repo: str = "ssurekumar01111-hue/Northbridge-Retail-Co."

@app.post("/audit")
async def audit_repo(req: AuditRequest):
    with tracer.start_as_current_span("Audit Repository Security") as span:
        span.set_attribute("repo", req.repo)
        try:
            res = await agent.audit_repository(req.repo)
            span.set_attribute("riskScore", res.get("riskScore", 0.0))
            return res
        except Exception as e:
            span.record_exception(e)
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "service": "agentmesh-it-security"}
