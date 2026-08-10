import os
import json
import base64
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel
from google.cloud import pubsub_v1

from agent import ITSecurityAgent
from telemetry import init_tracer

app = FastAPI(title="AgentMesh IT & Security Agent", version="1.0.0")
tracer = init_tracer("agentmesh-it-security", app=app)
agent = ITSecurityAgent()

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
TOPIC_ID = os.getenv("PUB_SUB_TOPIC", "agent-jobs")

# Initialize Pub/Sub Publisher Client
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

class AuditRequest(BaseModel):
    repo: str = "ssurekumar01111-hue/Northbridge-Retail-Co."

@app.post("/audit", status_code=status.HTTP_202_ACCEPTED)
async def audit_repo(req: AuditRequest):
    with tracer.start_as_current_span("Audit Repository Security (Async Queue)") as span:
        repo = req.repo
        repo_slug = repo.replace('/', '-')
        workflow_id = f"sec-wf-{repo_slug}"
        span.set_attribute("repo", repo)
        span.set_attribute("workflowId", workflow_id)

        try:
            # 1. Write workflow status="queued" to Firestore via Gateway
            queued_at = datetime.now(timezone.utc).isoformat()
            agent.client.update_workflow(
                workflow_id=workflow_id,
                status="queued",
                current_step="queued",
                context={
                    "repo": repo,
                    "queuedAt": queued_at
                }
            )
            print(f"[+] [Async /audit] Queued workflow '{workflow_id}' in Firestore at {queued_at}")

            # 2. Publish message to Pub/Sub topic "agent-jobs"
            payload = json.dumps({
                "repo": repo,
                "workflowId": workflow_id,
                "agentType": "it-security"
            }).encode("utf-8")

            future = publisher.publish(
                topic_path,
                data=payload,
                agentType="it-security",
                repo=repo,
                workflowId=workflow_id
            )
            message_id = future.result()
            print(f"[+] [Async /audit] Published Pub/Sub message ID: {message_id} to topic '{TOPIC_ID}'")

            # 3. Return 202 Accepted immediately with queued state
            return {
                "status": "queued",
                "workflowId": workflow_id,
                "repo": repo,
                "messageId": message_id,
                "queuedAt": queued_at
            }
        except Exception as e:
            span.record_exception(e)
            print(f"[-] [Async /audit] Error queuing audit: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/worker/audit")
async def worker_audit(request: Request):
    with tracer.start_as_current_span("Worker Audit Execution") as span:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")

        print(f"[*] [/worker/audit] Received worker payload: {body}")

        repo = None
        workflow_id = None

        # Handle Pub/Sub Push payload format
        if "message" in body:
            msg = body["message"]
            attrs = msg.get("attributes", {})
            repo = attrs.get("repo")
            workflow_id = attrs.get("workflowId")

            if not repo and "data" in msg:
                try:
                    data_str = base64.b64decode(msg["data"]).decode("utf-8")
                    data_json = json.loads(data_str)
                    repo = data_json.get("repo")
                    workflow_id = data_json.get("workflowId")
                except Exception as e:
                    print(f"[-] Error parsing Pub/Sub message data: {e}")

        # Fallback to direct JSON body payload
        if not repo:
            repo = body.get("repo")
            workflow_id = body.get("workflowId")

        if not repo:
            repo = "ssurekumar01111-hue/Northbridge-Retail-Co."

        if not workflow_id:
            repo_slug = repo.replace('/', '-')
            workflow_id = f"sec-wf-{repo_slug}"

        span.set_attribute("repo", repo)
        span.set_attribute("workflowId", workflow_id)

        # 4. ATOMIC IDEMPOTENCY GUARD: Claim workflow status in Firestore via Gateway transaction
        claim_res = agent.client.claim_workflow(
            workflow_id=workflow_id,
            expected_status="queued",
            new_status="running",
            current_step="scanning",
            context={
                "repo": repo,
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
                "repo": repo,
                "currentStatus": current_st
            }

        print(f"[+] [/worker/audit] Atomically claimed workflow '{workflow_id}' with status='running'. Invoking audit_repository...")

        # Process audit using unchanged agent logic
        try:
            res = await agent.audit_repository(repo)
            span.set_attribute("riskScore", res.get("riskScore", 0.0))
            return res
        except Exception as e:
            span.record_exception(e)
            print(f"[-] [/worker/audit] Execution failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "service": "agentmesh-it-security"}
