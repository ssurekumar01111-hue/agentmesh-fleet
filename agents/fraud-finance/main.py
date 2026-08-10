import os
import json
import base64
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel
from google.cloud import pubsub_v1

from agent import FraudFinanceAgent
from telemetry import init_tracer

app = FastAPI(title="AgentMesh Fraud & Finance Agent", version="1.0.0")
tracer = init_tracer("agentmesh-fraud-finance", app=app)
agent = FraudFinanceAgent()

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
TOPIC_ID = os.getenv("PUB_SUB_TOPIC", "agent-jobs")

# Initialize Pub/Sub Publisher Client
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

class InvestigationRequest(BaseModel):
    invoiceId: str

class ResumeRequest(BaseModel):
    workflowId: str

@app.post("/investigate", status_code=status.HTTP_202_ACCEPTED)
async def investigate_invoice(req: InvestigationRequest):
    with tracer.start_as_current_span("Investigate Invoice Workflow (Async Queue)") as span:
        invoice_id = req.invoiceId
        workflow_id = f"wf-{invoice_id}"
        span.set_attribute("invoiceId", invoice_id)
        span.set_attribute("workflowId", workflow_id)
        
        try:
            # 1. Write workflow status="queued" to Firestore via Gateway
            queued_at = datetime.now(timezone.utc).isoformat()
            agent.client.update_workflow(
                workflow_id=workflow_id,
                status="queued",
                current_step="queued",
                context={
                    "invoiceId": invoice_id,
                    "queuedAt": queued_at
                }
            )
            print(f"[+] [Async /investigate] Queued workflow '{workflow_id}' in Firestore at {queued_at}")

            # 2. Publish message to Pub/Sub topic "agent-jobs"
            payload = json.dumps({
                "invoiceId": invoice_id,
                "workflowId": workflow_id,
                "agentType": "fraud-finance"
            }).encode("utf-8")

            future = publisher.publish(
                topic_path,
                data=payload,
                agentType="fraud-finance",
                invoiceId=invoice_id,
                workflowId=workflow_id
            )
            message_id = future.result()
            print(f"[+] [Async /investigate] Published Pub/Sub message ID: {message_id} to topic '{TOPIC_ID}'")

            # 3. Return 202 Accepted immediately with queued state
            return {
                "status": "queued",
                "workflowId": workflow_id,
                "invoiceId": invoice_id,
                "messageId": message_id,
                "queuedAt": queued_at
            }
        except Exception as e:
            span.record_exception(e)
            print(f"[-] [Async /investigate] Error queuing investigation: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/worker/investigate")
async def worker_investigate(request: Request):
    with tracer.start_as_current_span("Worker Investigate Execution") as span:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")

        print(f"[*] [/worker/investigate] Received worker payload: {body}")

        invoice_id = None
        workflow_id = None

        # Handle Pub/Sub Push payload format
        if "message" in body:
            msg = body["message"]
            attrs = msg.get("attributes", {})
            invoice_id = attrs.get("invoiceId")
            workflow_id = attrs.get("workflowId")

            if not invoice_id and "data" in msg:
                try:
                    data_str = base64.b64decode(msg["data"]).decode("utf-8")
                    data_json = json.loads(data_str)
                    invoice_id = data_json.get("invoiceId")
                    workflow_id = data_json.get("workflowId")
                except Exception as e:
                    print(f"[-] Error parsing Pub/Sub message data: {e}")

        # Fallback to direct JSON body payload
        if not invoice_id:
            invoice_id = body.get("invoiceId")
            workflow_id = body.get("workflowId")

        if not invoice_id:
            raise HTTPException(status_code=400, detail="Missing invoiceId in request")

        if not workflow_id:
            workflow_id = f"wf-{invoice_id}"

        span.set_attribute("invoiceId", invoice_id)
        span.set_attribute("workflowId", workflow_id)

        # 4. ATOMIC IDEMPOTENCY GUARD: Claim workflow status in Firestore via Gateway transaction
        claim_res = agent.client.claim_workflow(
            workflow_id=workflow_id,
            expected_status="queued",
            new_status="running",
            current_step="investigating",
            context={
                "invoiceId": invoice_id,
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
                "invoiceId": invoice_id,
                "currentStatus": current_st
            }

        print(f"[+] [/worker/investigate] Atomically claimed workflow '{workflow_id}' with status='running'. Invoking process_invoice...")

        # Process invoice using unchanged agent logic
        try:
            res = await agent.process_invoice(invoice_id)
            span.set_attribute("workflowStatus", res.get("workflowStatus", "unknown"))
            return res
        except Exception as e:
            span.record_exception(e)
            print(f"[-] [/worker/investigate] Execution failed: {e}")
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
