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

class ComplianceAgent:
    """
    Compliance & Policy Agent powered by Google ADK (Agent Development Kit v2.6+).
    Handles Responsibility 1 (workflow policy review & assessment) driven by ADK Runner, LlmAgent, and FunctionTools.
    Handles Responsibility 2 (zero-trust HR access attempt denial verification).
    All data access strictly via GatewayClient -> Gateway -> target resource.
    """

    def __init__(self, gateway_client: GatewayClient = None):
        self.client = gateway_client or GatewayClient()
        self.session_service = InMemorySessionService()
        self._execution_context: Dict[str, Any] = {}

        # Define ADK Function Tools wrapping Gateway client operations
        def fetch_workflow(workflow_id: str) -> dict:
            """Fetch a workflow document by ID from Firestore workflows collection via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'fetch_workflow' called BY Runner for workflow_id='{workflow_id}'")
            res = self.client.get_workflow(workflow_id)
            if not res:
                raise ValueError(f"Workflow '{workflow_id}' not found via Gateway.")
            return res

        def fetch_memory(case_id: str) -> dict:
            """Fetch an existing memory/case document by ID from Firestore memory collection via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'fetch_memory' called BY Runner for case_id='{case_id}'")
            res = self.client.get_memory(case_id)
            return res or {}

        def fetch_policies() -> dict:
            """Fetch all enterprise policy documents from Firestore policies collection via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'fetch_policies' called BY Runner")
            policies = self.client.get_policies()
            return {"policies": policies, "count": len(policies)}

        def write_memory(case_id: str, workflow_id: str, entity_type: str, summary: str, findings: List[str], assessment_decision: str, history: List[str]) -> str:
            """Write compliance review findings to Firestore Memory collection via AgentMesh Gateway."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'write_memory' called BY Runner for case_id='{case_id}', decision='{assessment_decision}'")
            compliance_case_id = self.client.write_compliance_memory(
                case_id=case_id,
                workflow_id=workflow_id,
                entity_type=entity_type,
                summary=summary,
                findings=findings,
                assessment_decision=assessment_decision,
                history=history
            )
            self._execution_context["written_memory"] = {
                "compliance_case_id": compliance_case_id,
                "case_id": case_id,
                "workflow_id": workflow_id,
                "summary": summary,
                "findings": findings,
                "assessment_decision": assessment_decision,
                "history": history
            }
            return compliance_case_id

        def read_hr_employees(employee_id: str = "emp-001") -> dict:
            """Attempt to read HR employee records from sandbox_employees via AgentMesh Gateway (zero-trust test)."""
            print(f"[RUNNER_TOOL_EXECUTION] Tool 'read_hr_employees' called BY Runner for employee_id='{employee_id}'")
            return self.client.read_hr_employees()

        self.adk_tools = [
            FunctionTool(fetch_workflow),
            FunctionTool(fetch_memory),
            FunctionTool(fetch_policies),
            FunctionTool(write_memory),
            FunctionTool(read_hr_employees)
        ]

        self.adk_agent = LlmAgent(
            name="ComplianceAgent",
            model="gemini-3.5-flash",
            instruction="""You are an expert Enterprise Compliance & Policy Agent built on Google ADK.
Your task is to conduct an automated compliance policy review of a paused workflow using your tools.

Workflow steps you MUST execute in order using your tools:
1. Call tool `fetch_workflow` with the given workflow_id to get workflow context (invoiceId, riskScore, status, context).
2. Formulate case_id = "case-" + invoiceId from the workflow context (fallback invoiceId is extracted from workflowId or context).
3. Call tool `fetch_memory` with case_id to retrieve prior investigation history and findings.
4. Call tool `fetch_policies` to retrieve active enterprise policy rules.
5. Evaluate compliance decision against enterprise policies:
   - If risk score is high (>= 0.70) or invoice amount/vendor findings indicate policy violation or required escalation, decision MUST be 'ESCALATE' or 'REJECT'.
   - Otherwise, decision MUST be 'APPROVE'.
6. Call tool `write_memory` with (case_id, workflow_id, entity_type="invoice_compliance_review", summary, findings, assessment_decision=decision, history).

After calling all tools, output your final result as raw JSON in the exact structure:
{
  "workflowId": "<workflow_id>",
  "caseId": "<case_id>",
  "complianceCaseId": "compliance-<case_id>",
  "assessmentDecision": "APPROVE" or "REJECT" or "ESCALATE",
  "summary": "<summary_string>",
  "findings": ["<finding_1>", "<finding_2>"],
  "policiesQueried": <policies_count_int>
}""",
            tools=self.adk_tools
        )

        self.runner = Runner(
            agent=self.adk_agent,
            app_name="agentmesh-compliance",
            session_service=self.session_service
        )

    async def review_workflow_compliance(self, workflow_id: str) -> Dict[str, Any]:
        """RESPONSIBILITY 1: Perform formal compliance review on a paused workflow via ADK Runner."""
        print(f"\n[*] [ComplianceAgent - ADK Runner] Starting ADK Runner compliance review for Workflow '{workflow_id}'...")
        self._execution_context.clear()

        user_id = "agentmesh-system"
        session_id = f"session-comp-{workflow_id}-{uuid.uuid4().hex[:8]}"

        # 1. Create ADK session via Runner's Session Service
        await self.runner.session_service.create_session(
            app_name=self.runner.app_name,
            user_id=user_id,
            session_id=session_id
        )

        user_prompt = f"Please review workflow compliance for workflow ID '{workflow_id}'. Fetch the workflow, memory, and policies using tools, determine the compliance decision, and write findings to memory."
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
        print(f"[+] [ComplianceAgent - ADK Runner] ADK Runner execution finished. Raw output length: {len(full_output)}")

        # 3. Extract final assessment decision, findings, summary from Runner output / execution state
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

        mem_info = self._execution_context.get("written_memory", {})

        inv_id = workflow_id.replace("wf-", "").replace("workflow-", "")
        case_id = (parsed and parsed.get("caseId")) or mem_info.get("case_id") or f"case-{inv_id}"
        comp_case_id = (parsed and parsed.get("complianceCaseId")) or mem_info.get("compliance_case_id") or f"compliance-{case_id}"
        decision = (parsed and parsed.get("assessmentDecision")) or mem_info.get("assessment_decision") or "ESCALATE"
        summary = (parsed and parsed.get("summary")) or mem_info.get("summary") or "Compliance review complete."
        findings = (parsed and parsed.get("findings")) or mem_info.get("findings") or []
        policies_queried = (parsed and parsed.get("policiesQueried")) or 1

        print(f"[+] [ComplianceAgent - ADK Runner] Final Extraction: assessmentDecision={decision}, complianceCaseId={comp_case_id}")

        return {
            "workflowId": workflow_id,
            "caseId": case_id,
            "complianceCaseId": comp_case_id,
            "assessmentDecision": decision,
            "summary": summary,
            "findings": findings,
            "policiesQueried": policies_queried
        }

    def test_hr_data_access(self) -> Dict[str, Any]:
        """RESPONSIBILITY 2: Attempt unauthorized read of HR data (sandbox_employees) via Gateway."""
        print("\n[*] [ComplianceAgent - ADK] Executing Responsibility 2: Attempting unauthorized HR data read via Gateway...")
        res = self.client.read_hr_employees()
        return res
