import os
import asyncio
from typing import Dict, Any, List
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from gateway_client import GatewayClient
from reasoning import SecurityReasoningEngine


class ITSecurityAgent:
    """
    IT & Security Monitoring Agent powered by Google ADK (Agent Development Kit v2.6+).
    Performs automated repository security scanning using ADK Agent, Tools, and GatewayClient.
    All data/GitHub/memory/workflow access strictly via GatewayClient → Gateway → target resource.
    """

    def __init__(self, gateway_client: GatewayClient = None, reasoning_engine: SecurityReasoningEngine = None):
        self.client = gateway_client or GatewayClient()
        self.engine = reasoning_engine or SecurityReasoningEngine()
        self.session_service = InMemorySessionService()

        # Define ADK Function Tools wrapping Gateway client operations
        def list_issues(repo: str) -> dict:
            """List all open GitHub issues for the specified repository via AgentMesh Gateway."""
            issues = self.client.list_repo_issues(repo)
            return {"issues": issues, "count": len(issues)}

        def list_commits(repo: str) -> dict:
            """List recent GitHub commits for the specified repository via AgentMesh Gateway."""
            commits = self.client.list_repo_commits(repo)
            return {"commits": commits, "count": len(commits)}

        def create_issue(repo: str, title: str, body: str) -> dict:
            """Create a new GitHub issue in the specified repository via AgentMesh Gateway."""
            result = self.client.create_github_issue(repo, title, body)
            return result

        def write_memory(case_id: str, workflow_id: str, entity_type: str, summary: str, findings: List[str], risk_score: float, history: List[str]) -> str:
            """Write security investigation findings to Firestore Memory collection via AgentMesh Gateway."""
            return self.client.write_memory(
                case_id=case_id,
                workflow_id=workflow_id,
                entity_type=entity_type,
                summary=summary,
                findings=findings,
                risk_score=risk_score,
                history=history
            )

        def update_incident(incident_id: str, status: str, severity: str, title: str, description: str) -> str:
            """Create or update a security incident record in Firestore sandbox_incidents via AgentMesh Gateway."""
            return self.client.update_incident(
                incident_id=incident_id,
                status=status,
                severity=severity,
                title=title,
                description=description
            )

        def update_workflow(workflow_id: str, status: str, current_step: str, context: dict) -> str:
            """Update security investigation workflow state in Firestore Workflows collection via AgentMesh Gateway."""
            return self.client.update_workflow(
                workflow_id=workflow_id,
                status=status,
                current_step=current_step,
                context=context
            )

        self.adk_tools = [
            FunctionTool(list_issues),
            FunctionTool(list_commits),
            FunctionTool(create_issue),
            FunctionTool(write_memory),
            FunctionTool(update_incident),
            FunctionTool(update_workflow),
        ]

        self.adk_agent = LlmAgent(
            name="ITSecurityAgent",
            model="gemini-3.5-flash",
            instruction="""You are an expert Enterprise IT & Security Monitoring Agent built on Google ADK.
Your role is to audit GitHub repositories for security risks, analyze open issues and recent commits,
compute risk scores, create automated GitHub issues for high-risk findings via Gateway,
update incident records via Gateway, and persist all findings to memory and workflow state via Gateway.""",
            tools=self.adk_tools
        )

        self.runner = Runner(
            agent=self.adk_agent,
            app_name="agentmesh-it-security",
            session_service=self.session_service
        )

    def audit_repository(self, repo: str = "ssurekumar01111-hue/Northbridge-Retail-Co.") -> Dict[str, Any]:
        print(f"\n[*] [ITSecurityAgent - ADK] Auditing repository '{repo}' via Gateway...")

        # 1. Fetch issues & commits via Gateway
        issues = self.client.list_repo_issues(repo)
        commits = self.client.list_repo_commits(repo)

        # 2. Gemini security reasoning
        risk_score, summary, findings, assessment_status = self.engine.analyze_repo_activity(issues, commits)

        github_issue_created = None
        if risk_score >= 0.70 or assessment_status == "HIGH_RISK":
            print(f"[!] [ITSecurityAgent - ADK] HIGH RISK detected ({risk_score:.2f}). Opening real GitHub issue via Gateway...")
            issue_title = f"[AUTOMATED INCIDENT] Security Risk Detected in {repo}"
            issue_body = (
                f"## AgentMesh Security Findings\n\n"
                f"**Risk Score**: {risk_score:.2f}\n"
                f"**Summary**: {summary}\n\n"
                f"### Findings:\n" + "\n".join([f"- {f}" for f in findings])
            )
            created_issue = self.client.create_github_issue(repo, issue_title, issue_body)
            github_issue_created = {
                "issueNumber": created_issue.get("number"),
                "htmlUrl": created_issue.get("html_url"),
                "title": created_issue.get("title")
            }
            print(f"[+] [ITSecurityAgent - ADK] Opened GitHub Issue #{created_issue.get('number')} at {created_issue.get('html_url')}")

            # Update/Create incident record via Gateway
            self.client.update_incident(
                incident_id="inc-2026-001",
                status="investigating",
                severity="HIGH",
                title=f"Security Leak in {repo}",
                description=summary
            )

        # 3. Write finding to memory via Gateway
        case_id = f"sec-case-{repo.replace('/', '-')}"
        workflow_id = f"sec-wf-{repo.replace('/', '-')}"

        history_log = [
            f"ADK Agent repository scan initiated for {repo}.",
            f"Retrieved {len(issues)} issues and {len(commits)} commits via Gateway.",
            f"Gemini reasoning completed: Risk score {risk_score:.2f} ({assessment_status})."
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
        print(f"[+] [ITSecurityAgent - ADK] Memory written via Gateway for Case ID '{case_id}'.")

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
        print(f"[+] [ITSecurityAgent - ADK] Workflow '{workflow_id}' set to status '{wf_status}' via Gateway.")

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
