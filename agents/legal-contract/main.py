import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import LegalContractAgent
from telemetry import init_tracer

app = FastAPI(
    title="AgentMesh Legal Contract & NDA Reviewer Agent",
    version="1.0.0",
    description="Reviews vendor agreements, NDAs, and MSAs against Northbridge Retail Co. legal policy via Gemini reasoning.",
)
tracer = init_tracer("agentmesh-legal-contract", app=app)
agent = LegalContractAgent()


class ContractReviewRequest(BaseModel):
    contractId: str


@app.post("/review")
async def review_contract(req: ContractReviewRequest):
    """Submit a contract for legal policy review.

    The agent fetches the contract from Firestore via Gateway, runs ADK Runner
    on raw clause text and fields, writes Memory, and escalates to 'waiting_approval' if
    FLAGGED or ESCALATED.
    """
    with tracer.start_as_current_span("Review Contract Workflow") as span:
        span.set_attribute("contractId", req.contractId)
        try:
            res = await agent.process_contract(req.contractId)
            span.set_attribute("assessmentStatus", res.get("assessmentStatus", "unknown"))
            span.set_attribute("workflowStatus", res.get("workflowStatus", "unknown"))
            span.set_attribute("riskScore", res.get("riskScore", -1))
            return res
        except Exception as e:
            span.record_exception(e)
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok", "service": "agentmesh-legal-contract"}
