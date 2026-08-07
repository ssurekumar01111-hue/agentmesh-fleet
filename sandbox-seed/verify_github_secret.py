#!/usr/bin/env python3
"""
Verification script for GitHub PAT stored in GCP Secret Manager.
Path: Secret Manager -> python -> GitHub REST API.
"""

import os
import sys
import requests
from google.cloud import secretmanager

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
SECRET_ID = os.getenv("GITHUB_TOKEN_SECRET_NAME", "github-sandbox-pat")
REPO_NAME = os.getenv("GITHUB_SANDBOX_REPO", "ssurekumar01111-hue/Northbridge-Retail-Co.")

def access_secret_version(project_id: str, secret_id: str, version_id: str = "latest") -> str:
    """Access the payload for the given secret version from GCP Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8").strip()

def main():
    print(f"[*] Accessing secret '{SECRET_ID}' from Secret Manager for project '{PROJECT_ID}'...")
    try:
        token = access_secret_version(PROJECT_ID, SECRET_ID)
        print("[+] Secret retrieved successfully from Secret Manager.")
    except Exception as e:
        print(f"[-] FAILED to retrieve secret from Secret Manager: {e}")
        sys.exit(1)

    url = f"https://api.github.com/repos/{REPO_NAME}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AgentMesh-Verification-Script"
    }

    print(f"[*] Testing GitHub API access to repo '{REPO_NAME}'...")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            repo_data = response.json()
            print(f"[+] PASS: Successfully authenticated with GitHub API!")
            print(f"    Repository: {repo_data.get('full_name')}")
            print(f"    Private: {repo_data.get('private')}")
            print(f"    Description: {repo_data.get('description')}")
            print(f"    Default Branch: {repo_data.get('default_branch')}")
        else:
            print(f"[-] FAILED: GitHub API returned status code {response.status_code}")
            print(f"    Response: {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"[-] FAILED to connect to GitHub API: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
