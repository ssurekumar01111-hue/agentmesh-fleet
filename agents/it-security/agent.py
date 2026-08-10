import os
import json
import uuid
from typing import Dict, Any, List
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from gateway_client import GatewayClient

# Ensure Vertex AI environment variables are set for google-adk execution
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026"))
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", os.getenv("VERTEX_AI_LOCATION", "asia-south1"))

class ITSecurityAgent:
    """
    IT & Security Monitoring Agent powered by Google ADK (Agent Development Kit v2.6+).
    Performs automated repository security scanning driven by ADK Runner, LlmAgent, and FunctionTools.
    All operations strictly via GatewayClient -> Gateway -> target resource.
    """

    def __init__(self, gateway_client: GatewayClient = None):
        self.client = gateway_client or GatewayClient()
        self.session_service = InMemorySessionService()
        self._execution_context: Dict[str, Any] = {}

        # Define ADK Function Tools wrapping Gateway client operations
        def list_issues(repo: str) -> dict:
            """List all open GitHub issues for the specified repository via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'list_issues' called BY Runner for repo='{repo}'")
            issues = self.client.list_repo_issues(repo)
            return {"issues": issues, "count": len(issues)}

        def list_commits(repo: str) -> dict:
            """List recent GitHub commits for the specified repository via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'list_commits' called BY Runner for repo='{repo}'")
            commits = self.client.list_repo_commits(repo)
            return {"commits": commits, "count": len(commits)}

        def create_issue(repo: str, title: str, body: str) -> dict:
            """Create a new GitHub issue in the specified repository via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'create_issue' called BY Runner for repo='{repo}', title='{title}'")
            result = self.client.create_github_issue(repo, title, body)
            self._execution_context["github_issue"] = {
                "issueNumber": result.get("number"),
                "htmlUrl": result.get("html_url"),
                "title": result.get("title")
            }
            return result

        def write_memory(case_id: str, workflow_id: str, entity_type: str, summary: str, findings: List[str], risk_score: float, history: List[str]) -> str:
            """Write security investigation findings to Firestore Memory collection via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'write_memory' called BY Runner for case_id='{case_id}', risk_score={risk_score}")
            self._execution_context["written_memory"] = {
                "case_id": case_id,
                "workflow_id": workflow_id,
                "summary": summary,
                "findings": findings,
                "risk_score": risk_score,
                "history": history
            }
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
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'update_incident' called BY Runner for incident_id='{incident_id}', status='{status}'")
            self._execution_context["updated_incident"] = {
                "incident_id": incident_id,
                "status": status,
                "severity": severity,
                "title": title,
                "description": description
            }
            return self.client.update_incident(
                incident_id=incident_id,
                status=status,
                severity=severity,
                title=title,
                description=description
            )

        def update_workflow(workflow_id: str, status: str, current_step: str, context: dict) -> str:
            """Update security investigation workflow state in Firestore Workflows collection via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'update_workflow' called BY Runner for workflow_id='{workflow_id}', status='{status}'")
            self._execution_context["updated_workflow"] = {
                "workflow_id": workflow_id,
                "status": status,
                "current_step": current_step,
                "context": context
            }
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
            FunctionTool(update_workflow)
        ]

        self.adk_agent = LlmAgent(
            name="ITSecurityAgent",
            model="gemini-3.5-flash",
            instruction="""You are an expert Enterprise IT & Security Monitoring Agent built on Google ADK.
Your task is to conduct an automated security audit of a target GitHub repository using your tools.

Workflow steps you MUST execute in order using your tools:
1. Call tool `list_issues` with the given repo name to get open repository issues.
2. Call tool `list_commits` with the given repo name to get recent repository commits.
3. Analyze issues and commits for security risks (e.g. exposed API keys, secret credentials, AWS keys, security vulnerabilities):
   - If severe security risks or exposed credentials/keys are found, risk_score MUST be >= 0.70 and assessmentStatus MUST be 'HIGH_RISK'.
   - Otherwise (clean repository or normal commits), risk_score MUST be < 0.50 and assessmentStatus MUST be 'LOW_RISK'.
4. Formulate case_id = "sec-case-" + repo.replace('/', '-') and workflow_id = "sec-wf-" + repo.replace('/', '-').
5. If assessmentStatus is 'HIGH_RISK':
   - Call tool `create_issue` with repo, title="[AUTOMATED INCIDENT] Security Risk Detected in " + repo, and detailed markdown body.
   - Call tool `update_incident` with incident_id="inc-2026-001", status="investigating", severity="HIGH", title="Security Leak in " + repo, description=summary.
6. Call tool `write_memory` with (case_id, workflow_id, entity_type="repository", summary, findings, risk_score, history).
7. Call tool `update_workflow`:
   - If HIGH_RISK: status = "in_progress", current_step = "sec_incident_remediation".
   - If LOW_RISK: status = "completed", current_step = "audit_complete".
   - context = {"repo": repo, "riskScore": risk_score, "summary": summary, "findings": findings, "githubIssue": github_issue_info_if_created_else_null}.

After calling all tools, output your final result as raw JSON in the exact structure:
{
  "repo": "<repo>",
  "caseId": "sec-case-<repo_slug>",
  "workflowId": "sec-wf-<repo_slug>",
  "riskScore": <risk_score_float>,
  "assessmentStatus": "HIGH_RISK" or "LOW_RISK",
  "summary": "<summary_string>",
  "findings": ["<finding_1>", "<finding_2>"],
  "githubIssue": {"issueNumber": <number>, "htmlUrl": "<url>", "title": "<title>"} or null
}""",
            tools=self.adk_tools
        )

        self.runner = Runner(
            agent=self.adk_agent,
            app_name="agentmesh-it-security",
            session_service=self.session_service
        )

    async def audit_repository(self, repo: str = "ssurekumar01111-hue/Northbridge-Retail-Co.") -> Dict[str, Any]:
        print(f"\n[*] [ITSecurityAgent - ADK Runner] Starting ADK Runner repository audit for '{repo}'...")
        self._execution_context.clear()

        user_id = "agentmesh-system"
        repo_slug = repo.replace('/', '-')
        session_id = f"session-sec-{repo_slug}-{uuid.uuid4().hex[:8]}"

        # 1. Create ADK session via Runner's Session Service
        await self.runner.session_service.create_session(
            app_name=self.runner.app_name,
            user_id=user_id,
            session_id=session_id
        )

        user_prompt = f"Please perform an IT & Security audit on the GitHub repository '{repo}'. Fetch issues and commits using tools, evaluate security risk, open issues/incidents if high risk, write memory, and update workflow state."
        new_msg = types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_prompt)]
        )

        # 2. Execute ADK Runner drive loop
        final_text_parts = []
        async for event in self.runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_msg
        ):
            if hasattr(event, "content") and event.content and hasattr(event.content, "parts"):
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        final_text_parts.append(part.text)

        full_output = "".join(final_text_parts).strip()
        print(f"[+] [ITSecurityAgent - ADK Runner] ADK Runner execution finished. Raw output length: {len(full_output)}")

        # 3. Extract final risk score, assessment, findings, workflow status from Runner output / session execution state
        parsed = None
        cleaned_text = full_output
        if "```json" in cleaned_text:
            cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned_text:
            cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()

        try:
            parsed = json.loads(cleaned_text)
        except Exception:
            start = full_output.find("{")
            end = full_output.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(full_output[start:end+1])
                except Exception:
                    pass

        # Fall back or augment from tool execution context if LLM JSON missing any key
        mem_info = self._execution_context.get("written_memory", {})
        wf_info = self._execution_context.get("updated_workflow", {})
        github_issue = self._execution_context.get("github_issue") or (parsed and parsed.get("githubIssue"))

        case_id = (parsed and parsed.get("caseId")) or mem_info.get("case_id") or f"sec-case-{repo_slug}"
        workflow_id = (parsed and parsed.get("workflowId")) or wf_info.get("workflow_id") or f"sec-wf-{repo_slug}"

        raw_risk = parsed.get("riskScore") if (parsed and "riskScore" in parsed) else mem_info.get("risk_score")
        if raw_risk is None:
            raw_risk = 0.05
        risk_score = float(raw_risk)

        assessment_status = (parsed and parsed.get("assessmentStatus")) or ("HIGH_RISK" if risk_score >= 0.70 else "LOW_RISK")
        summary = (parsed and parsed.get("summary")) or mem_info.get("summary") or "Security repository scan complete."
        findings = (parsed and parsed.get("findings")) or mem_info.get("findings") or []

        print(f"[+] [ITSecurityAgent - ADK Runner] Final Extraction: riskScore={risk_score:.2f}, assessmentStatus={assessment_status}, issue={github_issue}")

        return {
            "repo": repo,
            "caseId": case_id,
            "workflowId": workflow_id,
            "riskScore": risk_score,
            "assessmentStatus": assessment_status,
            "summary": summary,
            "findings": findings,
            "githubIssue": github_issue
        }
