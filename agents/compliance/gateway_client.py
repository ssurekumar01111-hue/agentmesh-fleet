from datetime import datetime, timezone
import os
import requests
from typing import Dict, Any, Optional, List

GATEWAY_URL = os.getenv("GATEWAY_URL", "https://agentmesh-gateway-138003672216.asia-south1.run.app")
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
SERVICE_ACCOUNT_EMAIL = f"agentmesh-compliance@{PROJECT_ID}.iam.gserviceaccount.com"

class GatewayClient:
    """Client for making all data/memory/workflow calls strictly through AgentMesh Gateway."""

    def __init__(self, gateway_url: str = GATEWAY_URL, sa_email: str = SERVICE_ACCOUNT_EMAIL):
        self.gateway_url = gateway_url.rstrip("/")
        self.sa_email = sa_email

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        try:
            from opentelemetry import propagate
            propagate.inject(headers)
        except Exception as e:
            print(f"[GatewayClient] Note: Could not inject traceparent context: {e}")

        if os.getenv("ALLOW_LOCAL_AUTH_EMULATION", "false").lower() == "true":
            headers["x-emulated-sa"] = self.sa_email
        else:
            try:
                import google.auth.transport.requests
                import google.oauth2.id_token
                auth_req = google.auth.transport.requests.Request()
                token = google.oauth2.id_token.fetch_id_token(auth_req, self.gateway_url)
                headers["Authorization"] = f"Bearer {token}"
            except Exception as e:
                print(f"[GatewayClient] Note: Could not fetch OIDC ID token ({e})")
        return headers


    def call_gateway(self, target_resource: str, collection_name: str, action: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.gateway_url}/v1/execute"
        body = {
            "callerServiceAccount": self.sa_email,
            "targetResource": target_resource,
            "collectionName": collection_name,
            "action": action,
            "payload": payload or {}
        }
        res = requests.post(url, json=body, headers=self._headers(), timeout=45)
        if res.status_code != 200:
            try:
                err_json = res.json()
            except Exception:
                err_json = {}
            return {
                "status_code": res.status_code,
                "error": res.text,
                "detail": err_json.get("detail") or err_json.get("policyReason"),
                "policyReason": err_json.get("policyReason"),
                "auditLogId": err_json.get("auditLogId"),
                "success": False
            }
        return {"status_code": 200, "data": res.json().get("data", {}), "auditLogId": res.json().get("auditLogId"), "success": True}

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        res = self.call_gateway(
            target_resource="firestore:workflows",
            collection_name="workflows",
            action="read",
            payload={"docId": workflow_id}
        )
        return res.get("data") if res.get("success") else None

    def get_memory(self, case_id: str) -> Optional[Dict[str, Any]]:
        res = self.call_gateway(
            target_resource="firestore:memory",
            collection_name="memory",
            action="read",
            payload={"docId": case_id}
        )
        return res.get("data") if res.get("success") else None

    def get_policies(self) -> List[Dict[str, Any]]:
        """
        Fetch all enterprise policy documents from the 'policies' collection via Gateway.

        Phase 9b bug fix: changed action from 'query' to 'read' with no docId.
        The Gateway's /v1/execute handler (gateway/main.py lines 383-389) routes
        action='read' with no docId to db.collection(collectionName).limit(50).stream(),
        streaming all documents in the collection.
        The old action='query' fell into the else-branch returning {"status":"forwarded","collection":"policies"}
        with no actual document data — causing the compliance agent to always reason with zero policies.
        """
        res = self.call_gateway(
            target_resource="firestore:policies",
            collection_name="policies",
            action="read",
            payload={}
        )
        # Gateway returns: {"status":"allowed","data":[{...},{...},...]} for collection-stream reads
        data = res.get("data", {})
        if isinstance(data, list):
            return data
        # Fallback: if data is a dict with "success" key (error path)
        if res.get("success") is False:
            return []
        return []

    def write_compliance_memory(self, case_id: str, workflow_id: str, entity_type: str, summary: str, findings: List[str], assessment_decision: str, history: List[str]) -> str:
        compliance_case_id = f"compliance-{case_id}"
        payload = {
            "docId": compliance_case_id,
            "data": {
                "workflowId": workflow_id,
                "entityType": entity_type,
                "entityId": case_id,
                "summary": summary,
                "findings": findings,
                "assessmentDecision": assessment_decision,
                "history": history,
                "updatedAt": datetime.now(timezone.utc).isoformat()
            }
        }
        self.call_gateway(
            target_resource="firestore:memory",
            collection_name="memory",
            action="write",
            payload=payload
        )
        return compliance_case_id

    def read_hr_employees(self) -> Dict[str, Any]:
        """RESPONSIBILITY 2: Attempts to read HR employee records from sandbox_employees collection."""
        return self.call_gateway(
            target_resource="firestore:sandbox_employees",
            collection_name="sandbox_employees",
            action="read",
            payload={"docId": "emp-001"}
        )

    def update_workflow(self, workflow_id: str, status: str, current_step: str, context: Dict[str, Any]) -> str:
        payload = {
            "docId": workflow_id,
            "data": {
                "type": "compliance-review",
                "status": status,
                "initiatingAgentId": "compliance",
                "involvedAgentIds": ["fraud-finance", "compliance"],
                "involvedServiceAccounts": [self.sa_email, f"agentmesh-gateway@{PROJECT_ID}.iam.gserviceaccount.com"],
                "currentStep": current_step,
                "context": context,
                "updatedAt": datetime.now(timezone.utc).isoformat()
            }
        }
        self.call_gateway(
            target_resource="firestore:workflows",
            collection_name="workflows",
            action="write",
            payload=payload
        )
        return workflow_id
