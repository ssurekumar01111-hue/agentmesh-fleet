import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agent import ExpenseApprovalAgent
from telemetry import init_tracer

app = FastAPI(
    title="AgentMesh Expense Approval Agent",
    version="1.0.0",
    description="Reviews employee expense reports against Northbridge Retail Co. policy via Gemini reasoning.",
)
tracer = init_tracer("agentmesh-expense-approval", app=app)
agent = ExpenseApprovalAgent()


class ExpenseReviewRequest(BaseModel):
    expenseId: str


@app.post("/review")
async def review_expense(req: ExpenseReviewRequest):
    """Submit an expense report for policy review.

    The agent fetches the expense from Firestore via Gateway, runs ADK Runner,
    writes Memory, and escalates to 'waiting_approval' if FLAGGED or ESCALATED.
    """
    with tracer.start_as_current_span("Review Expense Workflow") as span:
        span.set_attribute("expenseId", req.expenseId)
        try:
            res = await agent.process_expense(req.expenseId)
            span.set_attribute("assessmentStatus", res.get("assessmentStatus", "unknown"))
            span.set_attribute("workflowStatus", res.get("workflowStatus", "unknown"))
            span.set_attribute("riskScore", res.get("riskScore", -1))
            return res
        except Exception as e:
            span.record_exception(e)
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok", "service": "agentmesh-expense-approval"}
