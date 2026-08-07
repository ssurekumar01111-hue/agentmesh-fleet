#!/usr/bin/env python3
"""
AgentMesh Gateway Service — FastAPI App.
Enforces 6-stage pipeline:
Authentication -> Identity Check -> Policy Check -> Model Armor -> Tool Access / Forward -> Audit Logging.
"""

import os
import sys
import time
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Request, HTTPException, Header, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.cloud import firestore
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from armor import ModelArmor

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE", "(default)")
ALLOW_LOCAL_AUTH_EMULATION = os.getenv("ALLOW_LOCAL_AUTH_EMULATION", "false").lower() == "true"

app = FastAPI(title="AgentMesh Gateway", version="1.0.0")

# Initialize clients
db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)
armor = ModelArmor(project_id=PROJECT_ID)

class GatewayRequest(BaseModel):
    callerServiceAccount: str
    targetResource: str       # e.g., "firestore:sandbox_invoices" or "firestore:sandbox_employees"
    collectionName: str       # e.g., "sandbox_invoices"
    action: str               # e.g., "read", "write", "query"
    payload: Optional[Dict[str, Any]] = None

def write_audit_log(
    agent_id: str,
    workflow_id: Optional[str],
    action: str,
    request_summary: str,
    response_summary: str,
    policy_decision: str,
    policy_reason: Optional[str],
    armor_flags: List[str],
    latency_ms: float
):
    """Writes an immutable, redacted audit log entry directly to Firestore."""
    try:
        log_doc = {
            "agentId": agent_id,
            "workflowId": workflow_id,
            "action": action,
            "requestSummary": request_summary[:500],
            "responseSummary": response_summary[:500],
            "policyDecision": policy_decision,
            "policyReason": policy_reason,
            "armorFlags": armor_flags,
            "latencyMs": round(latency_ms, 2),
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        db.collection("audit_log").add(log_doc)
    except Exception as e:
        print(f"[AuditLog] Error writing audit log: {e}")

def verify_token(authorization: Optional[str] = Header(None), x_emulated_sa: Optional[str] = Header(None)) -> str:
    """
    Stage 1: Authentication.
    Verifies Cloud Run OIDC ID token, or uses local auth emulation header if explicitly enabled.
    Returns caller service account email.
    """
    if ALLOW_LOCAL_AUTH_EMULATION and x_emulated_sa:
        print(f"[Auth] Local Auth Emulation active for caller: {x_emulated_sa}")
        return x_emulated_sa

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header with Bearer token."
        )

    token = authorization.split("Bearer ")[1]
    try:
        # Verify Cloud Run / OIDC Token
        claim = id_token.verify_oauth2_token(token, google_requests.Request())
        email = claim.get("email")
        if not email:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing email claim.")
        return email
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid OIDC token: {str(e)}"
        )

@app.post("/v1/execute")
async def execute_request(req: GatewayRequest, request: Request, caller_email: str = Depends(verify_token)):
    start_time = time.time()
    agent_id = "unknown"
    armor_flags = []
    
    # Override caller email from verified token
    sa_email = caller_email

    # Stage 2: Identity Check
    print(f"[Gateway] Stage 2: Identity Check for SA '{sa_email}'...")
    registry_query = db.collection("agent_registry").where("serviceAccountEmail", "==", sa_email).limit(1).stream()
    registry_docs = list(registry_query)
    
    if not registry_docs:
        latency = (time.time() - start_time) * 1000
        reason = f"Caller identity '{sa_email}' is not found in agent_registry."
        write_audit_log("unknown", None, req.action, str(req.dict()), "DENIED", "denied", reason, [], latency)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    agent_doc = registry_docs[0]
    agent_manifest = agent_doc.to_dict()
    agent_id = agent_doc.id
    department = agent_manifest.get("department", "")
    agent_status = agent_manifest.get("status", "")
    allowed_collections = agent_manifest.get("allowedCollections", [])

    if agent_status != "active":
        latency = (time.time() - start_time) * 1000
        reason = f"Agent '{agent_id}' status is '{agent_status}' (must be 'active')."
        write_audit_log(agent_id, None, req.action, str(req.dict()), "DENIED", "denied", reason, [], latency)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "status": "denied",
                "agentId": agent_id,
                "policyDecision": "denied",
                "policyReason": reason
            }
        )

    # Stage 3: Policy Check
    print(f"[Gateway] Stage 3: Policy Check for Dept '{department}' on Resource '{req.targetResource}'...")
    
    # Check 3a: Registry Allowed Collections check
    if req.collectionName and req.collectionName not in allowed_collections:
        latency = (time.time() - start_time) * 1000
        reason = f"Collection '{req.collectionName}' not listed in allowedCollections for agent '{agent_id}'."
        write_audit_log(agent_id, None, req.action, str(req.dict()), "DENIED", "denied", reason, [], latency)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "status": "denied",
                "agentId": agent_id,
                "policyDecision": "denied",
                "policyReason": reason
            }
        )

    # Check 3b: Real Firestore Policies query
    policies_query = db.collection("policies")\
        .where("subjectDepartment", "==", department)\
        .where("resource", "==", req.targetResource)\
        .where("effect", "==", "deny").stream()
    
    deny_policies = list(policies_query)
    if deny_policies:
        pol_data = deny_policies[0].to_dict()
        reason = pol_data.get("reason") or pol_data.get("description") or f"Denied by policy {deny_policies[0].id}"
        latency = (time.time() - start_time) * 1000
        write_audit_log(agent_id, None, req.action, str(req.dict()), "DENIED", "denied", reason, [], latency)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "status": "denied",
                "agentId": agent_id,
                "policyDecision": "denied",
                "policyReason": reason
            }
        )

    # Stage 4: Model Armor (Inbound Prompt / Payload Scan)
    print(f"[Gateway] Stage 4: Model Armor Inbound Scan...")
    req_str = str(req.payload or "")
    is_blocked, flags, clean_payload = armor.scan_content(req_str)
    armor_flags.extend(flags)

    if is_blocked:
        latency = (time.time() - start_time) * 1000
        reason = f"Model Armor inbound block flags triggered: {flags}"
        write_audit_log(agent_id, None, req.action, req_str, "BLOCKED_BY_ARMOR", "denied", reason, armor_flags, latency)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    # Stage 5 & 6: Tool Access & Forwarding to Target
    print(f"[Gateway] Stage 5/6: Forwarding request to Firestore collection '{req.collectionName}'...")
    try:
        if req.action == "read":
            if req.payload and "docId" in req.payload:
                doc_ref = db.collection(req.collectionName).document(req.payload["docId"]).get()
                result = doc_ref.to_dict() if doc_ref.exists else None
            else:
                docs = db.collection(req.collectionName).limit(20).stream()
                result = [d.to_dict() for d in docs]
        elif req.action == "write":
            doc_id = req.payload.get("docId")
            data = req.payload.get("data", {})
            if doc_id:
                db.collection(req.collectionName).document(doc_id).set(data)
            else:
                db.collection(req.collectionName).add(data)
            result = {"status": "written"}
        else:
            result = {"status": "forwarded", "collection": req.collectionName}

        # Model Armor Outbound Scan
        res_str = str(result)
        out_blocked, out_flags, clean_result = armor.scan_content(res_str)
        armor_flags.extend(out_flags)

        latency = (time.time() - start_time) * 1000
        write_audit_log(agent_id, None, req.action, req_str, str(clean_result), "allowed", None, armor_flags, latency)

        return {
            "status": "allowed",
            "agentId": agent_id,
            "policyDecision": "allowed",
            "data": result
        }

    except Exception as e:
        latency = (time.time() - start_time) * 1000
        err_msg = f"Execution error in collection '{req.collectionName}': {str(e)}"
        write_audit_log(agent_id, None, req.action, req_str, err_msg, "error", err_msg, armor_flags, latency)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=err_msg)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "agentmesh-gateway", "project": PROJECT_ID}
