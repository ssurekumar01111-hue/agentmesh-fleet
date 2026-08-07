import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import FraudFinanceAgent

app = FastAPI(title="AgentMesh Fraud & Finance Agent", version="1.0.0")
agent = FraudFinanceAgent()

class InvestigationRequest(BaseModel):
    invoiceId: str

@app.post("/investigate")
def investigate_invoice(req: InvestigationRequest):
    try:
        res = agent.process_invoice(req.invoiceId)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "service": "agentmesh-fraud-finance"}
