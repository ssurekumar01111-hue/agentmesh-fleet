import os
import json
import base64
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel
from google.cloud import pubsub_v1

from agent import HRLeaveAgent
from telemetry import init_tracer

app = FastAPI(
    title="AgentMesh HR Leave Assistant Agent",
    version="1.0.0",
    description="Reviews employee leave requests against Northbridge Retail Co. HR policy via Gemini reasoning.",
)
tracer = init_tracer("agentmesh-hr-leave", app=app)
agent = HRLeaveAgent()

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
TOPIC_ID = os.getenv("PUB_SUB_TOPIC", "agent-jobs")

# Initialize Pub/Sub Publisher Client
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

class LeaveReviewRequest(BaseModel):
    requestId: str = "lvr-2026-001"

@app.get("/health")
def health():
    return {"status": "ok", "service": "agentmesh-hr-leave"}

@app.post("/review", status_code=status.HTTP_202_ACCEPTED)
async def review_leave_request(req: LeaveReviewRequest):
    """Submit a leave request for HR policy review (Async Queue)."""
    with tracer.start_as_current_span("Review Leave Request Workflow (Async Queue)") as span:
        request_id = req.requestId
        workflow_id = f"wf-{request_id}"
        span.set_attribute("requestId", request_id)
        span.set_attribute("workflowId", workflow_id)

        try:
            # 1. Write workflow status="queued" to Firestore via Gateway
            queued_at = datetime.now(timezone.utc).isoformat()
            agent.client.update_workflow(
                workflow_id=workflow_id,
                status="queued",
                current_step="queued_leave_review",
                context={
                    "requestId": request_id,
                    "workflowId": workflow_id,
                    "queuedAt": queued_at
                }
            )
            print(f"[+] [Async /review] Queued workflow '{workflow_id}' for leave request '{request_id}' in Firestore at {queued_at}")

            # 2. Publish message to Pub/Sub topic "agent-jobs"
            payload = json.dumps({
                "requestId": request_id,
                "workflowId": workflow_id,
                "agentType": "hr-leave"
            }).encode("utf-8")

            future = publisher.publish(
                topic_path,
                data=payload,
                agentType="hr-leave",
                requestId=request_id,
                workflowId=workflow_id
            )
            message_id = future.result()
            print(f"[+] [Async /review] Published Pub/Sub message ID: {message_id} to topic '{TOPIC_ID}'")

            # 3. Return 202 Accepted immediately with queued state
            return {
                "status": "queued",
                "requestId": request_id,
                "workflowId": workflow_id,
                "messageId": message_id,
                "queuedAt": queued_at
            }
        except Exception as e:
            span.record_exception(e)
            print(f"[-] [Async /review] Error queuing leave review: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/worker/review")
async def worker_review(request: Request):
    with tracer.start_as_current_span("Worker Leave Review Execution") as span:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")

        print(f"[*] [/worker/review] Received worker payload: {body}")

        request_id = None
        workflow_id = None

        # Handle Pub/Sub Push payload format
        if "message" in body:
            msg = body["message"]
            attrs = msg.get("attributes", {})
            request_id = attrs.get("requestId")
            workflow_id = attrs.get("workflowId")

            if (not request_id or not workflow_id) and "data" in msg:
                try:
                    data_str = base64.b64decode(msg["data"]).decode("utf-8")
                    data_json = json.loads(data_str)
                    request_id = request_id or data_json.get("requestId")
                    workflow_id = workflow_id or data_json.get("workflowId")
                except Exception as e:
                    print(f"[-] Error parsing Pub/Sub message data: {e}")

        # Fallback to direct JSON body payload
        if not request_id:
            request_id = body.get("requestId", "lvr-2026-001")
        if not workflow_id:
            workflow_id = body.get("workflowId", f"wf-{request_id}")

        span.set_attribute("requestId", request_id)
        span.set_attribute("workflowId", workflow_id)

        # 4. IDEMPOTENCY GUARD: Check current workflow status in Firestore via Gateway
        try:
            existing_wf = agent.client.call_gateway(
                target_resource="firestore:workflows",
                collection_name="workflows",
                action="read",
                payload={"docId": workflow_id}
            )
            current_status = existing_wf.get("status") if existing_wf else None
        except Exception as e:
            print(f"[-] [Idempotency Guard] Note: Could not read existing workflow ({e})")
            current_status = None

        print(f"[*] [Idempotency Guard] Current status for '{workflow_id}' is '{current_status}'")

        if current_status in ["running", "waiting_approval", "completed", "resumed"]:
            print(f"[!] [Idempotency Guard] Skipping execution for '{workflow_id}' because status is already '{current_status}'.")
            return {
                "status": "skipped",
                "reason": f"Workflow '{workflow_id}' already in status '{current_status}'",
                "workflowId": workflow_id,
                "requestId": request_id,
                "currentStatus": current_status
            }

        # Mark workflow status="running"
        agent.client.update_workflow(
            workflow_id=workflow_id,
            status="running",
            current_step="leave_policy_evaluation",
            context={
                "requestId": request_id,
                "workflowId": workflow_id,
                "startedAt": datetime.now(timezone.utc).isoformat()
            }
        )
        print(f"[+] [/worker/review] Marked workflow '{workflow_id}' as status='running'. Invoking process_leave_request...")

        # Process leave review using unchanged agent logic
        try:
            res = await agent.process_leave_request(request_id)
            span.set_attribute("assessmentStatus", res.get("assessmentStatus", "unknown"))
            span.set_attribute("workflowStatus", res.get("workflowStatus", "unknown"))
            span.set_attribute("riskScore", res.get("riskScore", -1))
            return res
        except Exception as e:
            span.record_exception(e)
            print(f"[-] [/worker/review] Execution failed: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
