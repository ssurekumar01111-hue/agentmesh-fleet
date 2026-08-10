import os
import json
import base64
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel
from google.cloud import pubsub_v1

from agent import ComplianceAgent
from telemetry import init_tracer

app = FastAPI(title="AgentMesh Compliance Agent", version="1.0.0")
tracer = init_tracer("agentmesh-compliance", app=app)
agent = ComplianceAgent()

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
TOPIC_ID = os.getenv("PUB_SUB_TOPIC", "agent-jobs")

# Initialize Pub/Sub Publisher Client
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

class WorkflowReviewRequest(BaseModel):
    workflowId: str = "wf-inv-2026-007"

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "agentmesh-compliance"}

@app.post("/review", status_code=status.HTTP_202_ACCEPTED)
async def review_workflow(req: WorkflowReviewRequest):
    with tracer.start_as_current_span("Review Workflow Compliance (Async Queue)") as span:
        workflow_id = req.workflowId
        span.set_attribute("workflowId", workflow_id)

        try:
            # 1. Write workflow status="queued" to Firestore via Gateway
            queued_at = datetime.now(timezone.utc).isoformat()
            agent.client.update_workflow(
                workflow_id=workflow_id,
                status="queued",
                current_step="queued_compliance_review",
                context={
                    "workflowId": workflow_id,
                    "queuedAt": queued_at
                }
            )
            print(f"[+] [Async /review] Queued workflow '{workflow_id}' in Firestore at {queued_at}")

            # 2. Publish message to Pub/Sub topic "agent-jobs"
            payload = json.dumps({
                "workflowId": workflow_id,
                "agentType": "compliance"
            }).encode("utf-8")

            future = publisher.publish(
                topic_path,
                data=payload,
                agentType="compliance",
                workflowId=workflow_id
            )
            message_id = future.result()
            print(f"[+] [Async /review] Published Pub/Sub message ID: {message_id} to topic '{TOPIC_ID}'")

            # 3. Return 202 Accepted immediately with queued state
            return {
                "status": "queued",
                "workflowId": workflow_id,
                "messageId": message_id,
                "queuedAt": queued_at
            }
        except Exception as e:
            span.record_exception(e)
            print(f"[-] [Async /review] Error queuing compliance review: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/worker/review")
async def worker_review(request: Request):
    with tracer.start_as_current_span("Worker Compliance Review Execution") as span:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")

        print(f"[*] [/worker/review] Received worker payload: {body}")

        workflow_id = None

        # Handle Pub/Sub Push payload format
        if "message" in body:
            msg = body["message"]
            attrs = msg.get("attributes", {})
            workflow_id = attrs.get("workflowId")

            if not workflow_id and "data" in msg:
                try:
                    data_str = base64.b64decode(msg["data"]).decode("utf-8")
                    data_json = json.loads(data_str)
                    workflow_id = data_json.get("workflowId")
                except Exception as e:
                    print(f"[-] Error parsing Pub/Sub message data: {e}")

        # Fallback to direct JSON body payload
        if not workflow_id:
            workflow_id = body.get("workflowId")

        if not workflow_id:
            workflow_id = "wf-inv-2026-007"

        span.set_attribute("workflowId", workflow_id)

        # 4. ATOMIC IDEMPOTENCY GUARD: Claim workflow status in Firestore via Gateway transaction
        claim_res = agent.client.claim_workflow(
            workflow_id=workflow_id,
            expected_status="queued",
            new_status="running",
            current_step="compliance_audit",
            context={
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
                "currentStatus": current_st
            }

        print(f"[+] [/worker/review] Atomically claimed workflow '{workflow_id}' with status='running'. Invoking review_workflow_compliance...")

        # Process compliance review using unchanged agent logic
        try:
            res = await agent.review_workflow_compliance(workflow_id)
            span.set_attribute("assessmentDecision", res.get("assessmentDecision", "unknown"))

            # Update workflow status in Firestore to "completed"
            agent.client.update_workflow(
                workflow_id=workflow_id,
                status="completed",
                current_step="compliance_review_completed",
                context={
                    "workflowId": workflow_id,
                    "complianceResult": res,
                    "completedAt": datetime.now(timezone.utc).isoformat()
                }
            )
            print(f"[+] [/worker/review] Marked workflow '{workflow_id}' as status='completed' with decision '{res.get('assessmentDecision')}'")

            return {"status": "success", "data": res}
        except Exception as e:
            span.record_exception(e)
            print(f"[-] [/worker/review] Execution failed: {e}")
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
