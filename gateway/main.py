#!/usr/bin/env python3
"""
AgentMesh Gateway Service — FastAPI App with OpenTelemetry Instrumentation.
Enforces 6-stage pipeline:
Authentication -> Identity Check -> Policy Check -> Guard Pipeline -> Tool Access / Forward -> Audit Logging.
Also exposes a dedicated, authenticated Policy Simulation endpoint for zero-trust evaluation without tool execution.
"""

import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Request, HTTPException, Header, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.cloud import firestore
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from opentelemetry import trace

from armor import GuardPipeline
from telemetry import init_tracer

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE", "(default)")
ALLOW_LOCAL_AUTH_EMULATION = os.getenv("ALLOW_LOCAL_AUTH_EMULATION", "false").lower() == "true"

app = FastAPI(title="AgentMesh Gateway", version="1.0.0")
tracer = init_tracer("agentmesh-gateway", app=app)

# Initialize clients
db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)
armor = GuardPipeline(project_id=PROJECT_ID)

class GatewayRequest(BaseModel):
    callerServiceAccount: str
    targetResource: str       # e.g., "firestore:sandbox_invoices" or "firestore:sandbox_employees"
    collectionName: str       # e.g., "sandbox_invoices"
    action: str               # e.g., "read", "write", "query"
    payload: Optional[Dict[str, Any]] = None

class PolicyCheckRequest(BaseModel):
    targetAgentSa: str        # The identity to evaluate policy for e.g. agentmesh-compliance@...
    targetResource: str       # e.g. "firestore:sandbox_employees"
    collectionName: str       # e.g. "sandbox_employees"
    action: str = "read"

class ScanSimulationRequest(BaseModel):
    content: str

def write_audit_log(
    agent_id: str,
    workflow_id: Optional[str],
    action: str,
    request_summary: str,
    response_summary: str,
    policy_decision: str,
    policy_reason: Optional[str],
    armor_flags: List[str],
    latency_ms: float,
    simulated: bool = False
) -> Optional[str]:
    """Writes an immutable, redacted audit log entry directly to Firestore and returns the document ID."""
    with tracer.start_as_current_span("Audit Log write") as span:
        span.set_attribute("agentId", agent_id)
        span.set_attribute("policyDecision", policy_decision)
        span.set_attribute("latency", latency_ms)
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
                "simulated": simulated,
                "timestamp": firestore.SERVER_TIMESTAMP
            }
            update_time, ref = db.collection("audit_log").add(log_doc)
            span.set_attribute("auditLogId", ref.id)
            return ref.id
        except Exception as e:
            span.record_exception(e)
            print(f"[AuditLog] Error writing audit log: {e}")
            return None

def verify_token(authorization: Optional[str] = Header(None), x_emulated_sa: Optional[str] = Header(None)) -> str:
    """
    Stage 1: Authentication.
    Verifies Cloud Run OIDC ID token, or uses local auth emulation header ONLY if ALLOW_LOCAL_AUTH_EMULATION is true.
    Returns authenticated caller service account email.
    """
    with tracer.start_as_current_span("Authentication") as span:
        if ALLOW_LOCAL_AUTH_EMULATION and x_emulated_sa:
            span.set_attribute("auth.mode", "emulated")
            span.set_attribute("callerServiceAccount", x_emulated_sa)
            print(f"[Auth] Local Auth Emulation active for caller: {x_emulated_sa}")
            return x_emulated_sa

        if not authorization or not authorization.startswith("Bearer "):
            span.set_attribute("auth.status", "unauthorized_missing_header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or malformed Authorization header with Bearer token."
            )

        token = authorization.split("Bearer ")[1]
        try:
            claim = id_token.verify_oauth2_token(token, google_requests.Request())
            email = claim.get("email")
            if not email:
                span.set_attribute("auth.status", "unauthorized_missing_email")
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing email claim.")
            span.set_attribute("auth.mode", "oidc")
            span.set_attribute("callerServiceAccount", email)
            return email
        except Exception as e:
            span.record_exception(e)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid OIDC token: {str(e)}"
            )

@app.get("/")
def root():
    return {
        "service": "agentmesh-gateway",
        "status": "ok",
        "description": "AgentMesh Gateway — Zero-Trust Control Plane for the AgentMesh fleet. Enforces a 6-stage pipeline: Auth → Identity → Policy → Threat Shield → Tool Access → Audit.",
        "note": "This is a backend API service, not a browsable UI. Try /health for a status check, or visit the AgentMesh Dashboard for the live control plane: https://agentmesh-dashboard-138003672216.asia-south1.run.app"
    }

@app.post("/v1/simulate-policy")
async def simulate_policy(req: PolicyCheckRequest, caller_email: str = Depends(verify_token)):
    start_time = time.time()
    target_sa = req.targetAgentSa

    with tracer.start_as_current_span("Policy Simulation Pipeline") as sim_span:
        sim_span.set_attribute("targetAgentSa", target_sa)
        sim_span.set_attribute("targetResource", req.targetResource)

        # Lookup target agent in registry
        registry_query = db.collection("agent_registry").where("serviceAccountEmail", "==", target_sa).limit(1).stream()
        registry_docs = list(registry_query)

        if not registry_docs:
            latency = (time.time() - start_time) * 1000
            reason = f"Target identity '{target_sa}' not found in agent_registry."
            log_id = write_audit_log("unknown", None, req.action, f"[SIMULATION] Check {target_sa} -> {req.targetResource}", "DENIED", "denied", reason, [], latency, simulated=True)
            sim_span.set_attribute("policyDecision", "denied")
            sim_span.set_attribute("latency", latency)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "denied",
                    "simulated": True,
                    "agentId": "unknown",
                    "targetSa": target_sa,
                    "policyDecision": "denied",
                    "policyReason": reason,
                    "auditLogId": log_id
                }
            )

        agent_doc = registry_docs[0]
        agent_manifest = agent_doc.to_dict()
        agent_id = agent_doc.id
        department = agent_manifest.get("department", "")
        agent_status = agent_manifest.get("status", "")
        allowed_collections = agent_manifest.get("allowedCollections", [])

        sim_span.set_attribute("agentId", agent_id)

        if agent_status != "active":
            latency = (time.time() - start_time) * 1000
            reason = f"Agent '{agent_id}' status is '{agent_status}' (must be 'active')."
            log_id = write_audit_log(agent_id, None, req.action, f"[SIMULATION] Check {agent_id} -> {req.targetResource}", "DENIED", "denied", reason, [], latency, simulated=True)
            sim_span.set_attribute("policyDecision", "denied")
            sim_span.set_attribute("latency", latency)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "denied",
                    "simulated": True,
                    "agentId": agent_id,
                    "targetSa": target_sa,
                    "policyDecision": "denied",
                    "policyReason": reason,
                    "auditLogId": log_id
                }
            )

        if req.collectionName and req.collectionName not in allowed_collections:
            latency = (time.time() - start_time) * 1000
            reason = f"Collection '{req.collectionName}' not listed in allowedCollections for agent '{agent_id}'."
            log_id = write_audit_log(agent_id, None, req.action, f"[SIMULATION] Check {agent_id} -> {req.targetResource}", "DENIED", "denied", reason, [], latency, simulated=True)
            sim_span.set_attribute("policyDecision", "denied")
            sim_span.set_attribute("latency", latency)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "denied",
                    "simulated": True,
                    "agentId": agent_id,
                    "targetSa": target_sa,
                    "policyDecision": "denied",
                    "policyReason": reason,
                    "auditLogId": log_id
                }
            )

        policies_query = db.collection("policies")\
            .where("subjectDepartment", "==", department)\
            .where("resource", "==", req.targetResource)\
            .where("effect", "==", "deny").stream()

        deny_policies = list(policies_query)
        if deny_policies:
            pol_data = deny_policies[0].to_dict()
            reason = pol_data.get("reason") or pol_data.get("description") or f"Denied by policy {deny_policies[0].id}"
            latency = (time.time() - start_time) * 1000
            log_id = write_audit_log(agent_id, None, req.action, f"[SIMULATION] Check {agent_id} -> {req.targetResource}", "DENIED", "denied", reason, [], latency, simulated=True)
            sim_span.set_attribute("policyDecision", "denied")
            sim_span.set_attribute("latency", latency)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "status": "denied",
                    "simulated": True,
                    "agentId": agent_id,
                    "targetSa": target_sa,
                    "policyDecision": "denied",
                    "policyReason": reason,
                    "auditLogId": log_id
                }
            )

        latency = (time.time() - start_time) * 1000
        reason = f"Access to '{req.targetResource}' is allowed for agent '{agent_id}' ({department} dept)."
        log_id = write_audit_log(agent_id, None, req.action, f"[SIMULATION] Check {agent_id} -> {req.targetResource}", "ALLOWED", "allowed", reason, [], latency, simulated=True)
        sim_span.set_attribute("policyDecision", "allowed")
        sim_span.set_attribute("latency", latency)
        return {
            "status": "allowed",
            "simulated": True,
            "agentId": agent_id,
            "targetSa": target_sa,
            "policyDecision": "allowed",
            "policyReason": reason,
            "auditLogId": log_id
        }

@app.post("/v1/simulate-scan")
async def simulate_scan(req: ScanSimulationRequest, caller_email: str = Depends(verify_token)):
    start_time = time.time()
    content_str = req.content or ""

    with tracer.start_as_current_span("Threat Shield Simulation Pipeline") as sim_span:
        sim_span.set_attribute("callerServiceAccount", caller_email)
        sim_span.set_attribute("contentLength", len(content_str))

        # Lookup caller identity in registry if available
        agent_id = "dashboard"
        try:
            registry_query = db.collection("agent_registry").where("serviceAccountEmail", "==", caller_email).limit(1).stream()
            registry_docs = list(registry_query)
            if registry_docs:
                agent_id = registry_docs[0].id
        except Exception:
            pass

        sim_span.set_attribute("agentId", agent_id)

        # Call REAL Guard Pipeline's scan_content()
        is_blocked, flags, clean_content = armor.scan_content(content_str)
        latency = (time.time() - start_time) * 1000

        sim_span.set_attribute("isBlocked", is_blocked)
        sim_span.set_attribute("armorFlags", str(flags))
        sim_span.set_attribute("latency", latency)

        policy_decision = "BLOCKED_BY_ARMOR" if is_blocked else "ALLOWED"
        policy_reason = f"Threat Shield scan triggered flags: {flags}" if is_blocked else "Threat Shield scan passed: Content is safe."

        log_id = write_audit_log(
            agent_id=agent_id,
            workflow_id=None,
            action="simulate_scan",
            request_summary=f"[THREAT_SHIELD_SIMULATION] {content_str[:300]}",
            response_summary=f"Blocked: {is_blocked}, Flags: {flags}",
            policy_decision=policy_decision,
            policy_reason=policy_reason,
            armor_flags=flags,
            latency_ms=latency,
            simulated=True
        )

        return {
            "status": "blocked" if is_blocked else "clean",
            "simulated": True,
            "is_blocked": is_blocked,
            "flags": flags,
            "cleanContent": clean_content,
            "policyDecision": policy_decision,
            "policyReason": policy_reason,
            "auditLogId": log_id,
            "agentId": agent_id,
            "callerServiceAccount": caller_email,
            "latencyMs": round(latency, 2)
        }

@app.post("/v1/execute")
async def execute_request(req: GatewayRequest, request: Request, caller_email: str = Depends(verify_token)):
    start_time = time.time()
    agent_id = "unknown"
    armor_flags = []
    sa_email = caller_email

    from opentelemetry import propagate
    parent_ctx = propagate.extract(dict(request.headers))
    print(f"[Gateway] Received traceparent header: {request.headers.get('traceparent')}")

    with tracer.start_as_current_span("Gateway Full Pipeline", context=parent_ctx) as pipe_span:
        pipe_span.set_attribute("callerServiceAccount", sa_email)
        pipe_span.set_attribute("targetResource", req.targetResource)
        pipe_span.set_attribute("action", req.action)

        # Stage 2: Identity Check
        with tracer.start_as_current_span("Identity Check") as id_span:
            print(f"[Gateway] Stage 2: Identity Check for SA '{sa_email}'...")
            registry_query = db.collection("agent_registry").where("serviceAccountEmail", "==", sa_email).limit(1).stream()
            registry_docs = list(registry_query)
            
            if not registry_docs:
                latency = (time.time() - start_time) * 1000
                reason = f"Caller identity '{sa_email}' is not found in agent_registry."
                write_audit_log("unknown", None, req.action, str(req.dict()), "DENIED", "denied", reason, [], latency)
                pipe_span.set_attribute("agentId", "unknown")
                pipe_span.set_attribute("policyDecision", "denied")
                pipe_span.set_attribute("latency", latency)
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

            agent_doc = registry_docs[0]
            agent_manifest = agent_doc.to_dict()
            agent_id = agent_doc.id
            department = agent_manifest.get("department", "")
            agent_status = agent_manifest.get("status", "")
            allowed_collections = agent_manifest.get("allowedCollections", [])

            id_span.set_attribute("agentId", agent_id)
            id_span.set_attribute("department", department)
            id_span.set_attribute("agent_status", agent_status)
            pipe_span.set_attribute("agentId", agent_id)

            if agent_status != "active":
                latency = (time.time() - start_time) * 1000
                reason = f"Agent '{agent_id}' status is '{agent_status}' (must be 'active')."
                log_id = write_audit_log(agent_id, None, req.action, str(req.dict()), "DENIED", "denied", reason, [], latency)
                pipe_span.set_attribute("policyDecision", "denied")
                pipe_span.set_attribute("latency", latency)
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "status": "denied",
                        "agentId": agent_id,
                        "policyDecision": "denied",
                        "policyReason": reason,
                        "auditLogId": log_id
                    }
                )

        # Stage 3: Policy Check
        with tracer.start_as_current_span("Policy Check") as pol_span:
            print(f"[Gateway] Stage 3: Policy Check for Dept '{department}' on Resource '{req.targetResource}'...")
            
            if req.collectionName and req.collectionName not in allowed_collections:
                latency = (time.time() - start_time) * 1000
                reason = f"Collection '{req.collectionName}' not listed in allowedCollections for agent '{agent_id}'."
                log_id = write_audit_log(agent_id, None, req.action, str(req.dict()), "DENIED", "denied", reason, [], latency)
                pol_span.set_attribute("policyDecision", "denied")
                pipe_span.set_attribute("policyDecision", "denied")
                pipe_span.set_attribute("latency", latency)
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "status": "denied",
                        "agentId": agent_id,
                        "policyDecision": "denied",
                        "policyReason": reason,
                        "auditLogId": log_id
                    }
                )

            policies_query = db.collection("policies")\
                .where("subjectDepartment", "==", department)\
                .where("resource", "==", req.targetResource)\
                .where("effect", "==", "deny").stream()
            
            deny_policies = list(policies_query)
            if deny_policies:
                pol_data = deny_policies[0].to_dict()
                reason = pol_data.get("reason") or pol_data.get("description") or f"Denied by policy {deny_policies[0].id}"
                latency = (time.time() - start_time) * 1000
                log_id = write_audit_log(agent_id, None, req.action, str(req.dict()), "DENIED", "denied", reason, [], latency)
                pol_span.set_attribute("policyDecision", "denied")
                pipe_span.set_attribute("policyDecision", "denied")
                pipe_span.set_attribute("latency", latency)
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "status": "denied",
                        "agentId": agent_id,
                        "policyDecision": "denied",
                        "policyReason": reason,
                        "auditLogId": log_id
                    }
                )
            pol_span.set_attribute("policyDecision", "allowed")

        # Stage 4: Guard Pipeline / Threat Shield (Inbound Prompt / Payload Scan)
        with tracer.start_as_current_span("Threat Shield Scan") as armor_span:
            print(f"[Gateway] Stage 4: Guard Pipeline Inbound Scan...")
            req_str = str(req.payload or "")
            is_blocked, flags, clean_payload = armor.scan_content(req_str)
            armor_flags.extend(flags)
            armor_span.set_attribute("armorFlags", str(flags))
            armor_span.set_attribute("is_blocked", is_blocked)

            if is_blocked:
                latency = (time.time() - start_time) * 1000
                reason = f"Guard Pipeline inbound block flags triggered: {flags}"
                log_id = write_audit_log(agent_id, None, req.action, req_str, "BLOCKED_BY_ARMOR", "denied", reason, armor_flags, latency)
                pipe_span.set_attribute("policyDecision", "denied")
                pipe_span.set_attribute("armorFlags", str(armor_flags))
                pipe_span.set_attribute("latency", latency)
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "status": "denied",
                        "agentId": agent_id,
                        "policyDecision": "denied",
                        "policyReason": reason,
                        "armorFlags": armor_flags,
                        "auditLogId": log_id
                    }
                )

        # Stage 5 & 6: Tool Access & Forwarding to Target
        with tracer.start_as_current_span("Tool Access") as tool_span:
            print(f"[Gateway] Stage 5/6: Forwarding request to target '{req.targetResource}'...")
            tool_span.set_attribute("targetResource", req.targetResource)
            tool_span.set_attribute("action", req.action)
            try:
                if req.targetResource.startswith("github:"):
                    from github_tool import GitHubToolHandler
                    github_tool = GitHubToolHandler(project_id=PROJECT_ID)
                    result = github_tool.execute(action=req.action, payload=req.payload)

                elif req.targetResource.startswith("firestore:"):
                    if req.action == "read":
                        if req.payload and "docId" in req.payload:
                            doc_ref = db.collection(req.collectionName).document(req.payload["docId"]).get()
                            result = doc_ref.to_dict() if doc_ref.exists else None
                        else:
                            docs = db.collection(req.collectionName).limit(50).stream()
                            result = []
                            for d in docs:
                                item = d.to_dict()
                                if isinstance(item, dict) and "docId" not in item:
                                    item["docId"] = d.id
                                result.append(item)

                    elif req.action == "write":
                        doc_id = req.payload.get("docId") if req.payload else None
                        data = req.payload.get("data", {}) if req.payload else {}

                        # Stage 3.1: Workflow Ownership Enforcement Check
                        if req.collectionName == "workflows" and doc_id:
                            existing_wf_doc = db.collection("workflows").document(doc_id).get()
                            if existing_wf_doc.exists:
                                existing_data = existing_wf_doc.to_dict() or {}
                                involved_sa = existing_data.get("involvedServiceAccounts", [])
                                if isinstance(involved_sa, str):
                                    involved_sa = [involved_sa]
                                involved_agents = existing_data.get("involvedAgentIds", [])
                                if isinstance(involved_agents, str):
                                    involved_agents = [involved_agents]
                                init_agent = existing_data.get("initiatingAgentId", "")
                                owner_agent = existing_data.get("agentId", "")
                                assigned_agent = existing_data.get("assignedAgent", "")

                                # The Control Plane Dashboard acts as the Human-in-the-Loop governance operator
                                is_dashboard_operator = (
                                    agent_id == "dashboard" or
                                    sa_email == "agentmesh-dashboard@agentmesh-fleet-2026.iam.gserviceaccount.com"
                                )

                                is_involved = (
                                    is_dashboard_operator or
                                    agent_id in involved_sa or
                                    sa_email in involved_sa or
                                    agent_id in involved_agents or
                                    sa_email in involved_agents or
                                    agent_id == init_agent or
                                    sa_email == init_agent or
                                    agent_id == owner_agent or
                                    sa_email == owner_agent or
                                    agent_id == assigned_agent or
                                    sa_email == assigned_agent
                                )

                                if not is_involved:
                                    latency = (time.time() - start_time) * 1000
                                    reason = f"Workflow ownership check failed: Agent '{agent_id}' ({sa_email}) is not listed as an involved identity for workflow '{doc_id}'."
                                    log_id = write_audit_log(agent_id, doc_id, req.action, str(req.dict()), "DENIED", "denied", reason, armor_flags, latency)
                                    pipe_span.set_attribute("policyDecision", "denied")
                                    pipe_span.set_attribute("latency", latency)
                                    return JSONResponse(
                                        status_code=status.HTTP_403_FORBIDDEN,
                                        content={
                                            "status": "denied",
                                            "agentId": agent_id,
                                            "policyDecision": "denied",
                                            "policyReason": reason,
                                            "auditLogId": log_id
                                        }
                                    )

                        if doc_id:
                            db.collection(req.collectionName).document(doc_id).set(data)
                        else:
                            db.collection(req.collectionName).add(data)
                        result = {"status": "written"}

                    elif req.action == "claim":
                        doc_id = req.payload.get("docId") if req.payload else None
                        data = req.payload.get("data", {}) if req.payload else {}
                        expected_status = req.payload.get("expectedStatus", "queued") if req.payload else "queued"
                        new_status = req.payload.get("newStatus", "running") if req.payload else "running"

                        if not isinstance(expected_status, list):
                            expected_statuses = [expected_status]
                        else:
                            expected_statuses = expected_status

                        if not doc_id:
                            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="docId is required for action 'claim'")

                        # Stage 3.1: Workflow Ownership Enforcement Check
                        if req.collectionName == "workflows":
                            existing_wf_doc = db.collection("workflows").document(doc_id).get()
                            if existing_wf_doc.exists:
                                existing_data = existing_wf_doc.to_dict() or {}
                                involved_sa = existing_data.get("involvedServiceAccounts", [])
                                if isinstance(involved_sa, str):
                                    involved_sa = [involved_sa]
                                involved_agents = existing_data.get("involvedAgentIds", [])
                                if isinstance(involved_agents, str):
                                    involved_agents = [involved_agents]
                                init_agent = existing_data.get("initiatingAgentId", "")
                                owner_agent = existing_data.get("agentId", "")
                                assigned_agent = existing_data.get("assignedAgent", "")

                                is_dashboard_operator = (
                                    agent_id == "dashboard" or
                                    sa_email == "agentmesh-dashboard@agentmesh-fleet-2026.iam.gserviceaccount.com"
                                )

                                is_involved = (
                                    is_dashboard_operator or
                                    agent_id in involved_sa or
                                    sa_email in involved_sa or
                                    agent_id in involved_agents or
                                    sa_email in involved_agents or
                                    agent_id == init_agent or
                                    sa_email == init_agent or
                                    agent_id == owner_agent or
                                    sa_email == owner_agent or
                                    agent_id == assigned_agent or
                                    sa_email == assigned_agent
                                )

                                if not is_involved:
                                    latency = (time.time() - start_time) * 1000
                                    reason = f"Workflow ownership check failed: Agent '{agent_id}' ({sa_email}) is not listed as an involved identity for workflow '{doc_id}'."
                                    log_id = write_audit_log(agent_id, doc_id, req.action, str(req.dict()), "DENIED", "denied", reason, armor_flags, latency)
                                    pipe_span.set_attribute("policyDecision", "denied")
                                    pipe_span.set_attribute("latency", latency)
                                    return JSONResponse(
                                        status_code=status.HTTP_403_FORBIDDEN,
                                        content={
                                            "status": "denied",
                                            "agentId": agent_id,
                                            "policyDecision": "denied",
                                            "policyReason": reason,
                                            "auditLogId": log_id
                                        }
                                    )

                        doc_ref = db.collection(req.collectionName).document(doc_id)
                        transaction = db.transaction()

                        @firestore.transactional
                        def execute_claim(txn, ref):
                            snapshot = ref.get(transaction=txn)
                            if not snapshot.exists:
                                return False, "not_found", {}
                            current_data = snapshot.to_dict() or {}
                            current_status = current_data.get("status")
                            if current_status not in expected_statuses:
                                return False, current_status, current_data

                            merged = {
                                **current_data,
                                **data,
                                "status": new_status,
                                "updatedAt": datetime.now(timezone.utc).isoformat()
                            }
                            txn.set(ref, merged)
                            return True, new_status, merged

                        claimed, final_status, final_data = execute_claim(transaction, doc_ref)
                        result = {
                            "status": "claimed" if claimed else "claim_failed",
                            "claimed": claimed,
                            "currentStatus": final_status,
                            "docId": doc_id,
                            "data": final_data if claimed else {}
                        }
                    else:
                        result = {"status": "forwarded", "collection": req.collectionName}
                else:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported targetResource '{req.targetResource}'")

                # Guard Pipeline Outbound Scan
                res_str = str(result)
                out_blocked, out_flags, clean_result = armor.scan_content(res_str)
                armor_flags.extend(out_flags)

                latency = (time.time() - start_time) * 1000

                if out_blocked:
                    reason = f"Guard Pipeline outbound tool output block flags triggered: {out_flags}"
                    log_id = write_audit_log(agent_id, None, req.action, req_str, f"[BLOCKED_TOOL_OUTPUT: {out_flags}]", "blocked", reason, armor_flags, latency)

                    pipe_span.set_attribute("policyDecision", "blocked")
                    pipe_span.set_attribute("armorFlags", str(armor_flags))
                    pipe_span.set_attribute("latency", latency)

                    return JSONResponse(
                        status_code=status.HTTP_200_OK,
                        content={
                            "status": "blocked",
                            "agentId": agent_id,
                            "policyDecision": "blocked",
                            "policyReason": reason,
                            "armorFlags": armor_flags,
                            "auditLogId": log_id
                        }
                    )

                log_id = write_audit_log(agent_id, None, req.action, req_str, str(clean_result), "allowed", None, armor_flags, latency)

                pipe_span.set_attribute("policyDecision", "allowed")
                pipe_span.set_attribute("armorFlags", str(armor_flags))
                pipe_span.set_attribute("latency", latency)

                return {
                    "status": "allowed",
                    "agentId": agent_id,
                    "policyDecision": "allowed",
                    "auditLogId": log_id,
                    "data": result
                }

            except Exception as e:
                latency = (time.time() - start_time) * 1000
                err_msg = f"Execution error in collection '{req.collectionName}': {str(e)}"
                write_audit_log(agent_id, None, req.action, req_str, err_msg, "error", err_msg, armor_flags, latency)
                pipe_span.set_attribute("policyDecision", "error")
                pipe_span.set_attribute("latency", latency)
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=err_msg)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "agentmesh-gateway", "project": PROJECT_ID}
