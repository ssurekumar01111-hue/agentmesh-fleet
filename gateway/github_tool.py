import os
import requests
from typing import Dict, Any, Optional
from google.cloud import secretmanager

class GitHubToolHandler:
    """Handles GitHub API operations via Gateway, retrieving PAT securely from Secret Manager."""
    
    def __init__(self, project_id: str = "agentmesh-fleet-2026"):
        self.project_id = project_id
        self._pat: Optional[str] = None

    def _get_pat(self) -> str:
        if not self._pat:
            try:
                client = secretmanager.SecretManagerServiceClient()
                name = f"projects/{self.project_id}/secrets/github-sandbox-pat/versions/latest"
                res = client.access_secret_version(request={"name": name})
                self._pat = res.payload.data.decode("UTF-8").strip()
            except Exception as e:
                print(f"[Gateway:GitHubTool] Secret Manager access error: {e}")
                raise RuntimeError(f"Failed to access GitHub PAT from Secret Manager: {e}")
        return self._pat

    def execute(self, action: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = payload or {}
        repo = payload.get("repo", "ssurekumar01111-hue/Northbridge-Retail-Co.")
        pat = self._get_pat()
        headers = {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AgentMesh-Gateway"
        }

        if action == "list_issues":
            url = f"https://api.github.com/repos/{repo}/issues?state=open"
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code != 200:
                raise RuntimeError(f"GitHub API error [{res.status_code}]: {res.text}")
            issues_data = []
            for item in res.json():
                issues_data.append({
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "body": item.get("body"),
                    "state": item.get("state"),
                    "html_url": item.get("html_url")
                })
            return {"issues": issues_data}

        elif action == "list_commits":
            url = f"https://api.github.com/repos/{repo}/commits?per_page=10"
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 409: # Empty repository
                return {"commits": []}
            if res.status_code != 200:
                raise RuntimeError(f"GitHub API error [{res.status_code}]: {res.text}")
            commits_data = []
            for c in res.json():
                commits_data.append({
                    "sha": c.get("sha"),
                    "message": c.get("commit", {}).get("message"),
                    "author": c.get("commit", {}).get("author", {}).get("name"),
                    "date": c.get("commit", {}).get("author", {}).get("date"),
                    "html_url": c.get("html_url")
                })
            return {"commits": commits_data}

        elif action == "create_issue":
            title = payload.get("title", "Security Alert: Suspicious Activity Detected")
            body = payload.get("body", "Suspicious activity flagged by AgentMesh IT/Security Agent.")
            url = f"https://api.github.com/repos/{repo}/issues"
            data = {"title": title, "body": body}
            res = requests.post(url, headers=headers, json=data, timeout=15)
            if res.status_code not in (200, 201):
                raise RuntimeError(f"GitHub Issue Creation error [{res.status_code}]: {res.text}")
            return res.json()

        else:
            raise ValueError(f"Unsupported GitHub tool action: '{action}'")
