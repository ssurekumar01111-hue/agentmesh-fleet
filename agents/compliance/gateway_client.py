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
        if os.getenv("ALLOW_LOCAL_AUTH_EMULATION", "false").lower() == "true":
            headers["x-emulated-sa"] = self.sa_email
            headers["Authorization"] = f"Bearer {self.sa_email}"
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
        res = requests.post(url, json=body, headers=self._headers(), timeout=15)
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
        res = self.call_gateway(
            target_resource="firestore:policies",
            collection_name="policies",
            action="query",
            payload={"query": []}
        )
        return res.get("data", {}).get("documents", []) if res.get("success") else []

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
                "updatedAt": "AUTO_TIMESTAMP"
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
