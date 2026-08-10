import os
import json
import base64
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel
from google.cloud import pubsub_v1

from agent import ExpenseApprovalAgent
from telemetry import init_tracer

app = FastAPI(
    title="AgentMesh Expense Approval Agent",
    version="1.0.0",
    description="Reviews employee expense reports against Northbridge Retail Co. policy via Gemini reasoning.",
)
tracer = init_tracer("agentmesh-expense-approval", app=app)
agent = ExpenseApprovalAgent()

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
TOPIC_ID = os.getenv("PUB_SUB_TOPIC", "agent-jobs")

# Initialize Pub/Sub Publisher Client
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

class ExpenseReviewRequest(BaseModel):
    expenseId: str = "exp-2026-001"

@app.get("/health")
def health():
    return {"status": "ok", "service": "agentmesh-expense-approval"}

@app.post("/review", status_code=status.HTTP_202_ACCEPTED)
async def review_expense(req: ExpenseReviewRequest):
    """Submit an expense report for policy review (Async Queue)."""
    with tracer.start_as_current_span("Review Expense Workflow (Async Queue)") as span:
        expense_id = req.expenseId
        workflow_id = f"wf-{expense_id}"
        span.set_attribute("expenseId", expense_id)
        span.set_attribute("workflowId", workflow_id)

        try:
            # 1. Write workflow status="queued" to Firestore via Gateway
            queued_at = datetime.now(timezone.utc).isoformat()
            agent.client.update_workflow(
                workflow_id=workflow_id,
                status="queued",
                current_step="queued_expense_review",
                context={
                    "expenseId": expense_id,
                    "workflowId": workflow_id,
                    "queuedAt": queued_at
                }
            )
            print(f"[+] [Async /review] Queued workflow '{workflow_id}' for expense '{expense_id}' in Firestore at {queued_at}")

            # 2. Publish message to Pub/Sub topic "agent-jobs"
            payload = json.dumps({
                "expenseId": expense_id,
                "workflowId": workflow_id,
                "agentType": "expense-approval"
            }).encode("utf-8")

            future = publisher.publish(
                topic_path,
                data=payload,
                agentType="expense-approval",
                expenseId=expense_id,
                workflowId=workflow_id
            )
            message_id = future.result()
            print(f"[+] [Async /review] Published Pub/Sub message ID: {message_id} to topic '{TOPIC_ID}'")

            # 3. Return 202 Accepted immediately with queued state
            return {
                "status": "queued",
                "expenseId": expense_id,
                "workflowId": workflow_id,
                "messageId": message_id,
                "queuedAt": queued_at
            }
        except Exception as e:
            span.record_exception(e)
            print(f"[-] [Async /review] Error queuing expense review: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/worker/review")
async def worker_review(request: Request):
    with tracer.start_as_current_span("Worker Expense Review Execution") as span:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")

        print(f"[*] [/worker/review] Received worker payload: {body}")

        expense_id = None
        workflow_id = None

        # Handle Pub/Sub Push payload format
        if "message" in body:
            msg = body["message"]
            attrs = msg.get("attributes", {})
            expense_id = attrs.get("expenseId")
            workflow_id = attrs.get("workflowId")

            if (not expense_id or not workflow_id) and "data" in msg:
                try:
                    data_str = base64.b64decode(msg["data"]).decode("utf-8")
                    data_json = json.loads(data_str)
                    expense_id = expense_id or data_json.get("expenseId")
                    workflow_id = workflow_id or data_json.get("workflowId")
                except Exception as e:
                    print(f"[-] Error parsing Pub/Sub message data: {e}")

        # Fallback to direct JSON body payload
        if not expense_id:
            expense_id = body.get("expenseId", "exp-2026-001")
        if not workflow_id:
            workflow_id = body.get("workflowId", f"wf-{expense_id}")

        span.set_attribute("expenseId", expense_id)
        span.set_attribute("workflowId", workflow_id)

        # 4. ATOMIC IDEMPOTENCY GUARD: Claim workflow status in Firestore via Gateway transaction
        claim_res = agent.client.claim_workflow(
            workflow_id=workflow_id,
            expected_status="queued",
            new_status="running",
            current_step="expense_policy_evaluation",
            context={
                "expenseId": expense_id,
                "workflowId": workflow_id,
                "startedAt": datetime.now(timezone.utc).isoformat()
            }
        )

        if not claim_res.get("claimed", False):
            current_st = claim_res.get("currentStatus", "unknown")
            print(f"[!] [Idempotency Guard] Atomic claim failed for '{workflow_id}'. Current status is '{current_st}'. Skipping execution.")
            return {
                "status": "skipped",
                "reason": f"Atomic claim failed: Workflow '{workflow_id}' already claimed by concurrent delivery (status: '{current_st}')",
                "workflowId": workflow_id,
                "expenseId": expense_id,
                "currentStatus": current_st
            }

        print(f"[+] [/worker/review] Atomically claimed workflow '{workflow_id}' with status='running'. Invoking process_expense...")

        # Process expense review using unchanged agent logic
        try:
            res = await agent.process_expense(expense_id)
            span.set_attribute("assessmentStatus", res.get("assessmentStatus", "unknown"))
            span.set_attribute("workflowStatus", res.get("workflowStatus", "unknown"))
            span.set_attribute("riskScore", res.get("riskScore", -1))
            return res
        except Exception as e:
            span.record_exception(e)
            print(f"[-] [/worker/review] Execution failed: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
