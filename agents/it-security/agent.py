import os
from typing import Dict, Any
from gateway_client import GatewayClient
from reasoning import SecurityReasoningEngine

class ITSecurityAgent:
    """IT & Security Monitoring Agent handling automated repository security scanning via Gateway."""

    def __init__(self, gateway_client: GatewayClient = None, reasoning_engine: SecurityReasoningEngine = None):
        self.client = gateway_client or GatewayClient()
        self.engine = reasoning_engine or SecurityReasoningEngine()

    def audit_repository(self, repo: str = "ssurekumar01111-hue/Northbridge-Retail-Co.") -> Dict[str, Any]:
        print(f"\n[*] [ITSecurityAgent] Auditing repository '{repo}' via Gateway...")

        # 2a. Call Gateway to list issues and commits
        issues = self.client.list_repo_issues(repo)
        commits = self.client.list_repo_commits(repo)

        # 2b. Gemini security reasoning
        risk_score, summary, findings, assessment_status = self.engine.analyze_repo_activity(issues, commits)

        github_issue_created = None
        if risk_score >= 0.70 or assessment_status == "HIGH_RISK":
            print(f"[!] [ITSecurityAgent] HIGH RISK detected ({risk_score:.2f}). Opening real GitHub issue via Gateway...")
            issue_title = f"[AUTOMATED INCIDENT] Security Risk Detected in {repo}"
            issue_body = f"## AgentMesh Security Findings\n\n**Risk Score**: {risk_score:.2f}\n**Summary**: {summary}\n\n### Findings:\n" + "\n".join([f"- {f}" for f in findings])
            
            created_issue = self.client.create_github_issue(repo, issue_title, issue_body)
            github_issue_created = {
                "issueNumber": created_issue.get("number"),
                "htmlUrl": created_issue.get("html_url"),
                "title": created_issue.get("title")
            }
            print(f"[+] [ITSecurityAgent] Opened GitHub Issue #{created_issue.get('number')} at {created_issue.get('html_url')}")

            # 2d. Update/Create incident record linked to sandbox_incidents
            self.client.update_incident(
                incident_id="inc-2026-001",
                status="investigating",
                severity="HIGH",
                title=f"Security Leak in {repo}",
                description=summary
            )

        # 2c. Write finding to memory collection
        case_id = f"sec-case-{repo.replace('/', '-')}"
        workflow_id = f"sec-wf-{repo.replace('/', '-')}"

        history_log = [
            f"Repository scan initiated for {repo}.",
            f"Retrieved {len(issues)} issues and {len(commits)} commits via Gateway.",
            f"Reasoning completed: Risk score {risk_score:.2f} ({assessment_status})."
        ]

        self.client.write_memory(
            case_id=case_id,
            workflow_id=workflow_id,
            entity_type="repository",
            summary=summary,
            findings=findings,
            risk_score=risk_score,
            history=history_log
        )

        wf_status = "in_progress" if (risk_score >= 0.70) else "completed"
        context = {
            "repo": repo,
            "riskScore": risk_score,
            "summary": summary,
            "findings": findings,
            "githubIssue": github_issue_created
        }

        self.client.update_workflow(
            workflow_id=workflow_id,
            status=wf_status,
            current_step="sec_incident_remediation" if wf_status == "in_progress" else "audit_complete",
            context=context
        )

        return {
            "repo": repo,
            "caseId": case_id,
            "workflowId": workflow_id,
            "riskScore": risk_score,
            "assessmentStatus": assessment_status,
            "summary": summary,
            "findings": findings,
            "githubIssue": github_issue_created
        }
