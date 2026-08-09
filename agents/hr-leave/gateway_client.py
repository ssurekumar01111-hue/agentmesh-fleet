import os
import requests
from typing import Dict, Any, Optional, List

GATEWAY_URL = os.getenv("GATEWAY_URL", "https://agentmesh-gateway-138003672216.asia-south1.run.app")
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
SERVICE_ACCOUNT_EMAIL = f"agentmesh-hr-leave@{PROJECT_ID}.iam.gserviceaccount.com"


class GatewayClient:
    """Client for making all data/memory/workflow calls strictly through AgentMesh Gateway.

    This agent NEVER touches Firestore directly — every call routes through Gateway.
    Identity: agentmesh-hr-leave@agentmesh-fleet-2026.iam.gserviceaccount.com
    """

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

    def call_gateway(
        self,
        target_resource: str,
        collection_name: str,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.gateway_url}/v1/execute"
        body = {
            "callerServiceAccount": self.sa_email,
            "targetResource": target_resource,
            "collectionName": collection_name,
            "action": action,
            "payload": payload or {},
        }
        res = requests.post(url, json=body, headers=self._headers(), timeout=30)
        if res.status_code != 200:
            raise RuntimeError(f"Gateway call failed [{res.status_code}]: {res.text}")
        return res.json().get("data", {})

    # ------------------------------------------------------------------
    # Domain-specific helpers
    # ------------------------------------------------------------------

    def get_leave_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single leave request via Gateway (sandbox_leave_requests collection)."""
        return self.call_gateway(
            target_resource="firestore:sandbox_leave_requests",
            collection_name="sandbox_leave_requests",
            action="read",
            payload={"docId": request_id},
        )

    def get_employee(self, employee_id: str) -> Optional[Dict[str, Any]]:
        """Fetch employee info via Gateway (sandbox_employees collection)."""
        return self.call_gateway(
            target_resource="firestore:sandbox_employees",
            collection_name="sandbox_employees",
            action="read",
            payload={"docId": employee_id},
        )

    # ------------------------------------------------------------------
    # Memory & workflow helpers
    # ------------------------------------------------------------------

    def write_memory(
        self,
        case_id: str,
        workflow_id: str,
        entity_type: str,
        summary: str,
        findings: List[str],
        risk_score: float,
        history: List[str],
    ) -> str:
        payload = {
            "docId": case_id,
            "data": {
                "workflowId": workflow_id,
                "entityType": entity_type,
                "entityId": case_id,
                "summary": summary,
                "findings": findings,
                "riskScore": risk_score,
                "history": history,
                "updatedAt": "AUTO_TIMESTAMP",
            },
        }
        self.call_gateway(
            target_resource="firestore:memory",
            collection_name="memory",
            action="write",
            payload=payload,
        )
        return case_id

    def update_workflow(
        self,
        workflow_id: str,
        status: str,
        current_step: str,
        context: Dict[str, Any],
    ) -> str:
        payload = {
            "docId": workflow_id,
            "data": {
                "type": "leave-review",
                "status": status,
                "initiatingAgentId": "leave-assistant",
                "involvedAgentIds": ["leave-assistant"],
                "involvedServiceAccounts": [
                    self.sa_email,
                    f"agentmesh-gateway@{PROJECT_ID}.iam.gserviceaccount.com",
                ],
                "currentStep": current_step,
                "context": context,
                "updatedAt": "AUTO_TIMESTAMP",
            },
        }
        self.call_gateway(
            target_resource="firestore:workflows",
            collection_name="workflows",
            action="write",
            payload=payload,
        )
        return workflow_id
