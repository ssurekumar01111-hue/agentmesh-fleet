import os
import requests
from typing import Dict, Any, Optional, List

GATEWAY_URL = os.getenv("GATEWAY_URL", "https://agentmesh-gateway-138003672216.asia-south1.run.app")
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
SERVICE_ACCOUNT_EMAIL = f"agentmesh-it-security@{PROJECT_ID}.iam.gserviceaccount.com"

class GatewayClient:
    """Client for making all GitHub and Firestore operations strictly through AgentMesh Gateway."""

    def __init__(self, gateway_url: str = GATEWAY_URL, sa_email: str = SERVICE_ACCOUNT_EMAIL):
        self.gateway_url = gateway_url.rstrip("/")
        self.sa_email = sa_email

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
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
        res = requests.post(url, json=body, headers=self._headers(), timeout=15)
        if res.status_code != 200:
            raise RuntimeError(f"Gateway call failed [{res.status_code}]: {res.text}")
        return res.json().get("data", {})

    def list_repo_issues(self, repo: str) -> List[Dict[str, Any]]:
        data = self.call_gateway(
            target_resource="github:issues",
            collection_name="",
            action="list_issues",
            payload={"repo": repo}
        )
        return data.get("issues", [])

    def list_repo_commits(self, repo: str) -> List[Dict[str, Any]]:
        data = self.call_gateway(
            target_resource="github:issues",
            collection_name="",
            action="list_commits",
            payload={"repo": repo}
        )
        return data.get("commits", [])

    def create_github_issue(self, repo: str, title: str, body: str) -> Dict[str, Any]:
        data = self.call_gateway(
            target_resource="github:issues",
            collection_name="",
            action="create_issue",
            payload={"repo": repo, "title": title, "body": body}
        )
        return data

    def write_memory(self, case_id: str, workflow_id: str, entity_type: str, summary: str, findings: List[str], risk_score: float, history: List[str]) -> str:
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
                "updatedAt": "AUTO_TIMESTAMP"
            }
        }
        self.call_gateway(
            target_resource="firestore:memory",
            collection_name="memory",
            action="write",
            payload=payload
        )
        return case_id

    def update_incident(self, incident_id: str, status: str, severity: str, title: str, description: str) -> str:
        payload = {
            "docId": incident_id,
            "data": {
                "title": title,
                "description": description,
                "severity": severity,
                "status": status,
                "assignedAgentId": "it-security",
                "updatedAt": "AUTO_TIMESTAMP"
            }
        }
        self.call_gateway(
            target_resource="firestore:sandbox_incidents",
            collection_name="sandbox_incidents",
            action="write",
            payload=payload
        )
        return incident_id

    def update_workflow(self, workflow_id: str, status: str, current_step: str, context: Dict[str, Any]) -> str:
        payload = {
            "docId": workflow_id,
            "data": {
                "type": "security-incident-investigation",
                "status": status,
                "initiatingAgentId": "it-security",
                "involvedAgentIds": ["it-security"],
                "involvedServiceAccounts": [self.sa_email],
                "currentStep": current_step,
                "context": context,
                "updatedAt": "AUTO_TIMESTAMP"
            }
        }
        self.call_gateway(
            target_resource="firestore:workflows",
            collection_name="workflows",
            action="write",
            payload=payload
        )
        return workflow_id
