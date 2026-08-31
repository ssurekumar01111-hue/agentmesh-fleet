#!/usr/bin/env python3
"""
AgentMesh Gateway Service — FastAPI App with OpenTelemetry Instrumentation.
Enforces 6-stage pipeline:
Authentication -> Identity Check -> Policy Check -> Guard Pipeline -> Tool Access / Forward -> Audit Logging.
Also exposes a dedicated, authenticated Policy Simulation endpoint for zero-trust evaluation without tool execution.
Includes Phase 25 Gateway-enforced Agent Spending Policy (Stage 3.2).
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
    targetResource: str       # e.g., "firestore:sandbox_invoices" or "firestore:sandbox_expenses"
    collectionName: str       # e.g., "sandbox_invoices"
    action: str               # e.g., "read", "write", "claim"
    payload: Optional[Dict[str, Any]] = None
    amount: Optional[float] = None

class PolicyCheckRequest(BaseModel):
    targetAgentSa: str        # The identity to evaluate policy for e.g. agentmesh-expense-approval@...
    targetResource: str       # e.g. "firestore:sandbox_expenses"
    collectionName: str = "sandbox_expenses"
    action: str = "read"
    amount: Optional[float] = None

class ScanSimulationRequest(BaseModel):
    content: str

def get_agent_daily_spend_used(agent_id: str) -> float:
    """
    Computes daily spend used on-the-fly from today's (UTC) audit_log entries for this agent.
    Avoids stale counters and requires no background scheduled jobs.
    Only counts actual spending from non-simulated, allowed/waiting_approval decisions.
    Deduplicates by workflowId so multiple updates to the same workflow do not double-count.
    """
    try:
        now_utc = datetime.now(timezone.utc)
        start_of_today = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
        
        logs_query = db.collection("audit_log").where("agentId", "==", agent_id).stream()
        total_used = 0.0
        seen_workflow_ids = set()

        for doc in logs_query:
            d = doc.to_dict()
            if d.get("simulated", False):
                continue
            ts = d.get("timestamp")
            if not ts:
                continue
            if hasattr(ts, "to_datetime"):
                dt = ts.to_datetime()
            elif isinstance(ts, datetime):
                dt = ts
            else:
                try:
                    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                except Exception:
                    continue
            
            if dt >= start_of_today:
                decision = d.get("policyDecision", "")
                if decision in ("allowed", "waiting_approval", "allowed_pending_approval"):
                    amt = d.get("spendingAmount")
                    if amt is None and "spendingDetails" in d and isinstance(d["spendingDetails"], dict):
                        amt = d["spendingDetails"].get("requestedAmount") or d["spendingDetails"].get("amount")
                    if amt is not None and isinstance(amt, (int, float)):
                        wf_id = d.get("workflowId")
                        if wf_id:
                            if wf_id in seen_workflow_ids:
                                continue
                            seen_workflow_ids.add(wf_id)
                        total_used += float(amt)
        return total_used
    except Exception as e:
        print(f"[Gateway Spending] Error computing daily spend used: {e}")
        return 0.0

def extract_spending_amount(req: GatewayRequest) -> Optional[float]:
    """Extracts the financial amount requested from the gateway request payload or fields."""
    if req.amount is not None:
        return float(req.amount)
    if not req.payload:
        return None
    if "amount" in req.payload and isinstance(req.payload["amount"], (int, float)):
        return float(req.payload["amount"])
    if "spendingAmount" in req.payload and isinstance(req.payload["spendingAmount"], (int, float)):
        return float(req.payload["spendingAmount"])
    if "requestedAmount" in req.payload and isinstance(req.payload["requestedAmount"], (int, float)):
        return float(req.payload["requestedAmount"])
    
    data = req.payload.get("data")
    if isinstance(data, dict):
        if "amount" in data and isinstance(data["amount"], (int, float)):
            return float(data["amount"])
        if "requestedAmount" in data and isinstance(data["requestedAmount"], (int, float)):
            return float(data["requestedAmount"])
        ctx = data.get("context")
        if isinstance(ctx, dict):
            if "amount" in ctx and isinstance(ctx["amount"], (int, float)):
                return float(ctx["amount"])
            if "requestedAmount" in ctx and isinstance(ctx["requestedAmount"], (int, float)):
                return float(ctx["requestedAmount"])
            
    ctx = req.payload.get("context")
    if isinstance(ctx, dict):
        if "amount" in ctx and isinstance(ctx["amount"], (int, float)):
            return float(ctx["amount"])
        if "requestedAmount" in ctx and isinstance(ctx["requestedAmount"], (int, float)):
            return float(ctx["requestedAmount"])
        
    return None

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
    simulated: bool = False,
    spending_amount: Optional[float] = None,
    spending_limits: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """Writes an immutable, redacted audit log entry directly to Firestore and returns the document ID."""
    with tracer.start_as_current_span("Audit Log write") as span:
        span.set_attribute("agentId", agent_id)
        span.set_attribute("policyDecision", policy_decision)
        span.set_attribute("latency", latency_ms)
        if spending_amount is not None:
            span.set_attribute("spendingAmount", spending_amount)
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
            if spending_amount is not None:
                log_doc["spendingAmount"] = round(spending_amount, 2)
            if spending_limits is not None:
                log_doc["spendingLimits"] = spending_limits

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
        "description": "AgentMesh Gateway — Zero-Trust Control Plane for the AgentMesh fleet. Enforces a 6-stage pipeline: Auth → Identity → Policy (including Agent Spending Policy) → Threat Shield → Tool Access → Audit.",
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
        agent_manifest = agent_doc.to_dict() or {}
        agent_id = agent_doc.id
        department = agent_manifest.get("department") or ""
        agent_status = agent_manifest.get("status") or ""
        allowed_collections = agent_manifest.get("allowedCollections") or []

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
            pol_data = deny_policies[0].to_dict() or {}
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

        # Stage 3.2: Spending Policy Simulation Check (Gateway-enforced)
        spending_policy = agent_manifest.get("spendingPolicy") or {}
        max_tx = spending_policy.get("maxTransactionAmount", agent_manifest.get("maxTransactionAmount"))
        daily_limit = spending_policy.get("dailySpendLimit", agent_manifest.get("dailySpendLimit"))
        approval_thresh = spending_policy.get("approvalThreshold", agent_manifest.get("approvalThreshold"))

        if (max_tx is not None or daily_limit is not None or approval_thresh is not None) and req.amount is not None:
            max_tx_val = float(max_tx) if max_tx is not None else float("inf")
            daily_limit_val = float(daily_limit) if daily_limit is not None else float("inf")
            approval_thresh_val = float(approval_thresh) if approval_thresh is not None else float("inf")

            spending_amount = float(req.amount)
            daily_used = get_agent_daily_spend_used(agent_id)
            limits_dict = {
                "maxTransactionAmount": max_tx_val,
                "dailySpendLimit": daily_limit_val,
                "approvalThreshold": approval_thresh_val,
                "dailySpendUsed": daily_used
            }

            if spending_amount > max_tx_val:
                latency = (time.time() - start_time) * 1000
                reason = "Agent spending limit exceeded"
                log_id = write_audit_log(
                    agent_id=agent_id,
                    workflow_id=None,
                    action=req.action,
                    request_summary=f"[SIMULATION] Check {agent_id} spending ${spending_amount:,.2f} -> {req.targetResource}",
                    response_summary="DENIED",
                    policy_decision="denied",
                    policy_reason=reason,
                    armor_flags=[],
                    latency_ms=latency,
                    simulated=True,
                    spending_amount=spending_amount,
                    spending_limits=limits_dict
                )
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
                        "auditLogId": log_id,
                        "spendingDetails": {
                            "requestedAmount": spending_amount,
                            **limits_dict
                        }
                    }
                )

            if (spending_amount + daily_used) > daily_limit_val:
                latency = (time.time() - start_time) * 1000
                reason = "Daily spend limit exceeded."
                log_id = write_audit_log(
                    agent_id=agent_id,
                    workflow_id=None,
                    action=req.action,
                    request_summary=f"[SIMULATION] Check {agent_id} spending ${spending_amount:,.2f} -> {req.targetResource}",
                    response_summary="DENIED",
                    policy_decision="denied",
                    policy_reason=reason,
                    armor_flags=[],
                    latency_ms=latency,
                    simulated=True,
                    spending_amount=spending_amount,
                    spending_limits=limits_dict
                )
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
                        "auditLogId": log_id,
                        "spendingDetails": {
                            "requestedAmount": spending_amount,
                            **limits_dict
                        }
                    }
                )

            if spending_amount > approval_thresh_val:
                latency = (time.time() - start_time) * 1000
                reason = f"Spending amount ${spending_amount:,.2f} exceeds approval threshold of ${approval_thresh_val:,.2f}; routed to human approval gate."
                log_id = write_audit_log(
                    agent_id=agent_id,
                    workflow_id=None,
                    action=req.action,
                    request_summary=f"[SIMULATION] Check {agent_id} spending ${spending_amount:,.2f} -> {req.targetResource}",
                    response_summary="WAITING_APPROVAL",
                    policy_decision="waiting_approval",
                    policy_reason=reason,
                    armor_flags=[],
                    latency_ms=latency,
                    simulated=True,
                    spending_amount=spending_amount,
                    spending_limits=limits_dict
                )
                sim_span.set_attribute("policyDecision", "waiting_approval")
                sim_span.set_attribute("latency", latency)
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "status": "waiting_approval",
                        "simulated": True,
                        "agentId": agent_id,
                        "targetSa": target_sa,
                        "policyDecision": "waiting_approval",
                        "policyReason": reason,
                        "requiresApproval": True,
                        "auditLogId": log_id,
                        "spendingDetails": {
                            "requestedAmount": spending_amount,
                            **limits_dict
                        }
                    }
                )

            # Cleanly allowed within threshold and limits
            latency = (time.time() - start_time) * 1000
            reason = f"Spending policy check passed: Amount ${spending_amount:,.2f} is within threshold (${approval_thresh_val:,.2f}) and limits."
            log_id = write_audit_log(
                agent_id=agent_id,
                workflow_id=None,
                action=req.action,
                request_summary=f"[SIMULATION] Check {agent_id} spending ${spending_amount:,.2f} -> {req.targetResource}",
                response_summary="ALLOWED",
                policy_decision="allowed",
                policy_reason=reason,
                armor_flags=[],
                latency_ms=latency,
                simulated=True,
                spending_amount=spending_amount,
                spending_limits=limits_dict
            )
            sim_span.set_attribute("policyDecision", "allowed")
            sim_span.set_attribute("latency", latency)
            return {
                "status": "allowed",
                "simulated": True,
                "agentId": agent_id,
                "targetSa": target_sa,
                "policyDecision": "allowed",
                "policyReason": reason,
                "requiresApproval": False,
                "auditLogId": log_id,
                "spendingDetails": {
                    "requestedAmount": spending_amount,
                    **limits_dict
                }
            }

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
    sa_email = req.callerServiceAccount or caller_email

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
            agent_manifest = agent_doc.to_dict() or {}
            agent_id = agent_doc.id
            department = agent_manifest.get("department") or ""
            agent_status = agent_manifest.get("status") or ""
            allowed_collections = agent_manifest.get("allowedCollections") or []

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
        spending_amount = None
        spending_requires_approval = False
        spending_reason = None
        spending_limits_dict = None

        with tracer.start_as_current_span("Policy Check") as pol_span:
            print(f"[Gateway] Stage 3: Policy Check for Dept '{department}' on Resource '{req.targetResource}'...")
            
            # Check 3.1: Collection whitelist
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

            # Check 3.2: General policy rules in 'policies' collection
            policies_query = db.collection("policies")\
                .where("subjectDepartment", "==", department)\
                .where("resource", "==", req.targetResource)\
                .where("effect", "==", "deny").stream()
            
            deny_policies = list(policies_query)
            if deny_policies:
                pol_data = deny_policies[0].to_dict() or {}
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

            # Check 3.3: Gateway-Enforced Agent Spending Policy (BEFORE Threat Shield)
            spending_policy = agent_manifest.get("spendingPolicy") or {}
            max_tx = spending_policy.get("maxTransactionAmount", agent_manifest.get("maxTransactionAmount"))
            daily_limit = spending_policy.get("dailySpendLimit", agent_manifest.get("dailySpendLimit"))
            approval_thresh = spending_policy.get("approvalThreshold", agent_manifest.get("approvalThreshold"))

            if max_tx is not None or daily_limit is not None or approval_thresh is not None:
                spending_amount = extract_spending_amount(req)
                
                # If reading or querying sandbox_expenses without amount in payload, attempt lookup by docId
                if spending_amount is None and req.collectionName == "sandbox_expenses" and req.payload and "docId" in req.payload:
                    try:
                        exp_doc = db.collection("sandbox_expenses").document(req.payload["docId"]).get()
                        if exp_doc.exists:
                            exp_d = exp_doc.to_dict()
                            if exp_d and "amount" in exp_d:
                                spending_amount = float(exp_d["amount"])
                    except Exception as e:
                        print(f"[Gateway Spending] Error looking up expense amount: {e}")

                if spending_amount is not None:
                    max_tx_val = float(max_tx) if max_tx is not None else float("inf")
                    daily_limit_val = float(daily_limit) if daily_limit is not None else float("inf")
                    approval_thresh_val = float(approval_thresh) if approval_thresh is not None else float("inf")

                    daily_used = get_agent_daily_spend_used(agent_id)
                    spending_limits_dict = {
                        "maxTransactionAmount": max_tx_val,
                        "dailySpendLimit": daily_limit_val,
                        "approvalThreshold": approval_thresh_val,
                        "dailySpendUsed": daily_used
                    }

                    # Check 3.3a: Per-transaction cap
                    if spending_amount > max_tx_val:
                        latency = (time.time() - start_time) * 1000
                        reason = "Agent spending limit exceeded"
                        log_id = write_audit_log(
                            agent_id=agent_id,
                            workflow_id=req.payload.get("workflowId") if req.payload else None,
                            action=req.action,
                            request_summary=str(req.dict()),
                            response_summary=f"DENIED: {reason} (${spending_amount:,.2f} > ${max_tx_val:,.2f})",
                            policy_decision="denied",
                            policy_reason=reason,
                            armor_flags=[],
                            latency_ms=latency,
                            spending_amount=spending_amount,
                            spending_limits=spending_limits_dict
                        )
                        pol_span.set_attribute("policyDecision", "denied")
                        pol_span.set_attribute("policyReason", reason)
                        pol_span.set_attribute("spending.decision", "denied_per_tx_cap")
                        pipe_span.set_attribute("policyDecision", "denied")
                        pipe_span.set_attribute("latency", latency)
                        return JSONResponse(
                            status_code=status.HTTP_403_FORBIDDEN,
                            content={
                                "status": "denied",
                                "agentId": agent_id,
                                "policyDecision": "denied",
                                "policyReason": reason,
                                "auditLogId": log_id,
                                "spendingDetails": {
                                    "requestedAmount": spending_amount,
                                    **spending_limits_dict
                                }
                            }
                        )

                    # Check if this request is completing an already-approved / resumed workflow
                    is_already_resumed_or_approved = False
                    if req.collectionName == "workflows" and req.payload:
                        doc_id = req.payload.get("docId")
                        if doc_id:
                            existing_wf_doc = db.collection("workflows").document(doc_id).get()
                            if existing_wf_doc.exists:
                                ex_d = existing_wf_doc.to_dict() or {}
                                write_d = (req.payload.get("data") if isinstance(req.payload, dict) else {}) or {}
                                ctx = (write_d.get("context") if isinstance(write_d, dict) else {}) or {}
                                if (
                                    ex_d.get("status") == "resumed" or
                                    bool(ctx.get("resumedAt")) or
                                    (ex_d.get("context") or {}).get("humanOperatorDecision") == "APPROVED"
                                ):
                                    is_already_resumed_or_approved = True

                    if not is_already_resumed_or_approved:
                        # Check 3.3b: Daily spend limit
                        if (spending_amount + daily_used) > daily_limit_val:
                            latency = (time.time() - start_time) * 1000
                            reason = "Daily spend limit exceeded."
                            log_id = write_audit_log(
                                agent_id=agent_id,
                                workflow_id=req.payload.get("workflowId") if req.payload else None,
                                action=req.action,
                                request_summary=str(req.dict()),
                                response_summary=f"DENIED: {reason} (${spending_amount:,.2f} + ${daily_used:,.2f} > ${daily_limit_val:,.2f})",
                                policy_decision="denied",
                                policy_reason=reason,
                                armor_flags=[],
                                latency_ms=latency,
                                spending_amount=spending_amount,
                                spending_limits=spending_limits_dict
                            )
                            pol_span.set_attribute("policyDecision", "denied")
                            pol_span.set_attribute("policyReason", reason)
                            pol_span.set_attribute("spending.decision", "denied_daily_limit")
                            pipe_span.set_attribute("policyDecision", "denied")
                            pipe_span.set_attribute("latency", latency)
                            return JSONResponse(
                                status_code=status.HTTP_403_FORBIDDEN,
                                content={
                                    "status": "denied",
                                    "agentId": agent_id,
                                    "policyDecision": "denied",
                                    "policyReason": reason,
                                    "auditLogId": log_id,
                                    "spendingDetails": {
                                        "requestedAmount": spending_amount,
                                        **spending_limits_dict
                                    }
                                }
                            )

                        # Check 3.3c: Approval threshold (under caps, but requires human approval)
                        if spending_amount > approval_thresh_val:
                            spending_requires_approval = True
                            spending_reason = f"Spending amount ${spending_amount:,.2f} exceeds approval threshold of ${approval_thresh_val:,.2f}; routed to human approval gate."
                            pol_span.set_attribute("spending.decision", "waiting_approval")
                        else:
                            spending_reason = f"Spending policy check passed: Amount ${spending_amount:,.2f} is within threshold (${approval_thresh_val:,.2f}) and limits."
                            pol_span.set_attribute("spending.decision", "allowed")
                    else:
                        spending_reason = f"Spending approved: Workflow '{req.payload.get('docId')}' previously authorized by operator/threshold."
                        pol_span.set_attribute("spending.decision", "allowed_resumed")

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
                log_id = write_audit_log(agent_id, None, req.action, req_str, "BLOCKED_BY_ARMOR", "denied", reason, armor_flags, latency, spending_amount=spending_amount, spending_limits=spending_limits_dict)
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
                        data = (req.payload.get("data") if req.payload else {}) or {}

                        # Stage 3.1: Workflow Ownership & Spending Approval Enforcement Check
                        if req.collectionName == "workflows":
                            existing_data = {}
                            if doc_id:
                                existing_wf_doc = db.collection("workflows").document(doc_id).get()
                                if existing_wf_doc.exists:
                                    existing_data = existing_wf_doc.to_dict() or {}
                                    involved_sa = existing_data.get("involvedServiceAccounts") or []
                                    if isinstance(involved_sa, str):
                                        involved_sa = [involved_sa]
                                    involved_agents = existing_data.get("involvedAgentIds") or []
                                    if isinstance(involved_agents, str):
                                        involved_agents = [involved_agents]
                                    init_agent = existing_data.get("initiatingAgentId") or ""
                                    owner_agent = existing_data.get("agentId") or ""
                                    assigned_agent = existing_data.get("assignedAgent") or ""

                                    # The Control Plane Dashboard acts as the Human-in-the-Loop governance operator
                                    is_dashboard_operator = (
                                        agent_id == "dashboard" or
                                        sa_email == "agentmesh-dashboard@agentmesh-fleet-2026.iam.gserviceaccount.com"
                                    )

                                    is_involved = (
                                        is_dashboard_operator or
                                        not (involved_sa or involved_agents or init_agent or owner_agent or assigned_agent) or
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

                            # Spending policy human-approval gate enforcement
                            if spending_requires_approval:
                                ctx = (data.get("context") if isinstance(data, dict) else {}) or {}
                                is_already_resumed_or_approved = (
                                    data.get("status") == "completed" and
                                    (
                                        ctx.get("resumedAt") or
                                        ctx.get("finalResolution") or
                                        existing_data.get("status") == "resumed"
                                    )
                                )
                                if not is_already_resumed_or_approved:
                                    data["status"] = "waiting_approval"
                                    data["currentStep"] = "human_approval_gate"
                                    if "context" in data and isinstance(data["context"], dict):
                                        data["context"]["spendingPolicyEnforced"] = True
                                        data["context"]["spendingReason"] = spending_reason

                        if doc_id:
                            db.collection(req.collectionName).document(doc_id).set(data)
                        else:
                            db.collection(req.collectionName).add(data)
                        result = {"status": "written", "requiresApproval": spending_requires_approval}

                    elif req.action == "claim":
                        doc_id = req.payload.get("docId") if req.payload else None
                        data = (req.payload.get("data") if req.payload else {}) or {}
                        expected_status = (req.payload.get("expectedStatus") if req.payload else None) or "queued"
                        new_status = (req.payload.get("newStatus") if req.payload else None) or "running"

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
                                involved_sa = existing_data.get("involvedServiceAccounts") or []
                                if isinstance(involved_sa, str):
                                    involved_sa = [involved_sa]
                                involved_agents = existing_data.get("involvedAgentIds") or []
                                if isinstance(involved_agents, str):
                                    involved_agents = [involved_agents]
                                init_agent = existing_data.get("initiatingAgentId") or ""
                                owner_agent = existing_data.get("agentId") or ""
                                assigned_agent = existing_data.get("assignedAgent") or ""

                                is_dashboard_operator = (
                                    agent_id == "dashboard" or
                                    sa_email == "agentmesh-dashboard@agentmesh-fleet-2026.iam.gserviceaccount.com"
                                )

                                is_involved = (
                                    is_dashboard_operator or
                                    not (involved_sa or involved_agents or init_agent or owner_agent or assigned_agent) or
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
                    log_id = write_audit_log(agent_id, None, req.action, req_str, f"[BLOCKED_TOOL_OUTPUT: {out_flags}]", "blocked", reason, armor_flags, latency, spending_amount=spending_amount, spending_limits=spending_limits_dict)

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

                decision_to_log = "waiting_approval" if (spending_requires_approval and not is_already_resumed_or_approved) else "allowed"
                final_policy_reason = spending_reason if spending_requires_approval else None
                wf_id_log = None
                if req.payload and isinstance(req.payload, dict):
                    wf_id_log = req.payload.get("workflowId") or req.payload.get("docId") or ((req.payload.get("data") or {}).get("workflowId") if isinstance(req.payload.get("data"), dict) else None)
                if not wf_id_log and req.collectionName == "workflows":
                    wf_id_log = doc_id

                log_id = write_audit_log(
                    agent_id=agent_id,
                    workflow_id=wf_id_log,
                    action=req.action,
                    request_summary=req_str,
                    response_summary=str(clean_result),
                    policy_decision=decision_to_log,
                    policy_reason=final_policy_reason,
                    armor_flags=armor_flags,
                    latency_ms=latency,
                    spending_amount=spending_amount,
                    spending_limits=spending_limits_dict
                )

                pipe_span.set_attribute("policyDecision", decision_to_log)
                pipe_span.set_attribute("armorFlags", str(armor_flags))
                pipe_span.set_attribute("latency", latency)

                return {
                    "status": "allowed",
                    "agentId": agent_id,
                    "policyDecision": decision_to_log,
                    "policyReason": final_policy_reason,
                    "requiresApproval": spending_requires_approval,
                    "auditLogId": log_id,
                    "data": result
                }

            except Exception as e:
                latency = (time.time() - start_time) * 1000
                err_msg = f"Execution error in collection '{req.collectionName}': {str(e)}"
                write_audit_log(agent_id, None, req.action, req_str, err_msg, "error", err_msg, armor_flags, latency, spending_amount=spending_amount, spending_limits=spending_limits_dict)
                pipe_span.set_attribute("policyDecision", "error")
                pipe_span.set_attribute("latency", latency)
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=err_msg)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "agentmesh-gateway", "project": PROJECT_ID}
