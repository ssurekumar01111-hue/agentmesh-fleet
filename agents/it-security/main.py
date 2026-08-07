import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import ITSecurityAgent

app = FastAPI(title="AgentMesh IT & Security Agent", version="1.0.0")
agent = ITSecurityAgent()

class AuditRequest(BaseModel):
    repo: str = "ssurekumar01111-hue/Northbridge-Retail-Co."

@app.post("/audit")
def audit_repo(req: AuditRequest):
    try:
        res = agent.audit_repository(req.repo)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "service": "agentmesh-it-security"}
