import os
import json
import base64
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel
from google.cloud import pubsub_v1

from agent import LegalContractAgent
from telemetry import init_tracer

app = FastAPI(
    title="AgentMesh Legal Contract & NDA Reviewer Agent",
    version="1.0.0",
    description="Reviews vendor agreements, NDAs, and MSAs against Northbridge Retail Co. legal policy via Gemini reasoning.",
)
tracer = init_tracer("agentmesh-legal-contract", app=app)
agent = LegalContractAgent()

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
TOPIC_ID = os.getenv("PUB_SUB_TOPIC", "agent-jobs")

# Initialize Pub/Sub Publisher Client
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

class ContractReviewRequest(BaseModel):
    contractId: str = "ctr-2026-001"

@app.get("/")
def root():
    return {
        "service": "agentmesh-legal-contract",
        "status": "ok",
        "description": "AgentMesh Legal Contract & NDA Reviewer Agent — Reviews vendor agreements, NDAs, and MSAs against Northbridge Retail Co. legal policy via Gemini reasoning.",
        "note": "This is a backend API service, not a browsable UI. Try /health for a status check, or visit the AgentMesh Dashboard for the live control plane: https://agentmesh-dashboard-138003672216.asia-south1.run.app"
    }

@app.get("/health")
def health():
    return {"status": "ok", "service": "agentmesh-legal-contract"}

@app.post("/review", status_code=status.HTTP_202_ACCEPTED)
async def review_contract(req: ContractReviewRequest):
    """Submit a contract for legal policy review (Async Queue)."""
    with tracer.start_as_current_span("Review Contract Workflow (Async Queue)") as span:
        contract_id = req.contractId
        workflow_id = f"wf-{contract_id}"
        span.set_attribute("contractId", contract_id)
        span.set_attribute("workflowId", workflow_id)

        try:
            # 1. Write workflow status="queued" to Firestore via Gateway
            queued_at = datetime.now(timezone.utc).isoformat()
            agent.client.update_workflow(
                workflow_id=workflow_id,
                status="queued",
                current_step="queued_contract_review",
                context={
                    "contractId": contract_id,
                    "workflowId": workflow_id,
                    "queuedAt": queued_at
                }
            )
            print(f"[+] [Async /review] Queued workflow '{workflow_id}' for contract '{contract_id}' in Firestore at {queued_at}")

            # 2. Publish message to Pub/Sub topic "agent-jobs"
            payload = json.dumps({
                "contractId": contract_id,
                "workflowId": workflow_id,
                "agentType": "legal-contract"
            }).encode("utf-8")

            future = publisher.publish(
                topic_path,
                data=payload,
                agentType="legal-contract",
                contractId=contract_id,
                workflowId=workflow_id
            )
            message_id = future.result()
            print(f"[+] [Async /review] Published Pub/Sub message ID: {message_id} to topic '{TOPIC_ID}'")

            # 3. Return 202 Accepted immediately with queued state
            return {
                "status": "queued",
                "contractId": contract_id,
                "workflowId": workflow_id,
                "messageId": message_id,
                "queuedAt": queued_at
            }
        except Exception as e:
            span.record_exception(e)
            print(f"[-] [Async /review] Error queuing contract review: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@app.post("/worker/review")
async def worker_review(request: Request):
    with tracer.start_as_current_span("Worker Contract Review Execution") as span:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")

        print(f"[*] [/worker/review] Received worker payload: {body}")

        contract_id = None
        workflow_id = None

        # Handle Pub/Sub Push payload format
        if "message" in body:
            msg = body["message"]
            attrs = msg.get("attributes", {})
            contract_id = attrs.get("contractId")
            workflow_id = attrs.get("workflowId")

            if (not contract_id or not workflow_id) and "data" in msg:
                try:
                    data_str = base64.b64decode(msg["data"]).decode("utf-8")
                    data_json = json.loads(data_str)
                    contract_id = contract_id or data_json.get("contractId")
                    workflow_id = workflow_id or data_json.get("workflowId")
                except Exception as e:
                    print(f"[-] Error parsing Pub/Sub message data: {e}")

        # Fallback to direct JSON body payload
        if not contract_id:
            contract_id = body.get("contractId", "ctr-2026-001")
        if not workflow_id:
            workflow_id = body.get("workflowId", f"wf-{contract_id}")

        span.set_attribute("contractId", contract_id)
        span.set_attribute("workflowId", workflow_id)

        # 4. ATOMIC IDEMPOTENCY GUARD: Claim workflow status in Firestore via Gateway transaction
        claim_res = agent.client.claim_workflow(
            workflow_id=workflow_id,
            expected_status="queued",
            new_status="running",
            current_step="contract_policy_evaluation",
            context={
                "contractId": contract_id,
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
                "contractId": contract_id,
                "currentStatus": current_st
            }

        print(f"[+] [/worker/review] Atomically claimed workflow '{workflow_id}' with status='running'. Invoking process_contract...")

        # Process contract review using unchanged agent logic
        try:
            res = await agent.process_contract(contract_id)
            span.set_attribute("assessmentStatus", res.get("assessmentStatus", "unknown"))
            span.set_attribute("workflowStatus", res.get("workflowStatus", "unknown"))
            span.set_attribute("riskScore", res.get("riskScore", -1))
            return res
        except Exception as e:
            span.record_exception(e)
            print(f"[-] [/worker/review] Execution failed: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

class ResumeRequest(BaseModel):
    workflowId: str

@app.post("/resume")
def resume_workflow(req: ResumeRequest):
    """Resume a workflow that was paused at human_approval_gate."""
    with tracer.start_as_current_span("Resume Workflow Transition") as span:
        span.set_attribute("workflowId", req.workflowId)
        try:
            wf = agent.client.call_gateway(
                target_resource="firestore:workflows",
                collection_name="workflows",
                action="read",
                payload={"docId": req.workflowId}
            )
            if not wf:
                raise HTTPException(status_code=404, detail=f"Workflow '{req.workflowId}' not found.")

            current_status = wf.get("status")
            if current_status != "resumed":
                raise HTTPException(
                    status_code=409,
                    detail=f"Workflow '{req.workflowId}' status is '{current_status}' (expected 'resumed')."
                )

            context = wf.get("context", {})
            context["resumedAt"] = datetime.now(timezone.utc).isoformat()
            context["finalResolution"] = "Human approval granted; contract review authorized."
            agent.client.update_workflow(
                workflow_id=req.workflowId,
                status="completed",
                current_step="review_complete",
                context=context
            )
            span.set_attribute("workflowStatus", "completed")
            return {"workflowId": req.workflowId, "status": "completed", "currentStep": "review_complete"}
        except HTTPException:
            raise
        except Exception as e:
            span.record_exception(e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
