import os
import asyncio
from typing import Dict, Any, List
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from gateway_client import GatewayClient
from reasoning import ComplianceReasoningEngine


class ComplianceAgent:
    """
    Compliance & Policy Agent powered by Google ADK (Agent Development Kit v2.6+).
    Handles Responsibility 1 (workflow policy review & assessment) and
    Responsibility 2 (zero-trust HR access attempt denial verification).

    Phase 9b fix: get_policies() now uses action="read" with no docId, which triggers
    the Gateway's collection-stream path (gateway/main.py lines 383-389), returning all
    policy documents. The previous action="query" was not handled and returned empty.
    """

    def __init__(self, gateway_client: GatewayClient = None, reasoning_engine: ComplianceReasoningEngine = None):
        self.client = gateway_client or GatewayClient()
        self.engine = reasoning_engine or ComplianceReasoningEngine()
        self.session_service = InMemorySessionService()

        # Define ADK Function Tools wrapping Gateway client operations
        def fetch_workflow(workflow_id: str) -> dict:
            """Fetch a workflow document by ID from Firestore workflows collection via AgentMesh Gateway."""
            res = self.client.get_workflow(workflow_id)
            if not res:
                raise ValueError(f"Workflow '{workflow_id}' not found via Gateway.")
            return res

        def fetch_memory(case_id: str) -> dict:
            """Fetch an existing memory/case document by ID from Firestore memory collection via AgentMesh Gateway."""
            res = self.client.get_memory(case_id)
            return res or {}

        def fetch_policies() -> dict:
            """
            Fetch all enterprise policy documents from Firestore policies collection via AgentMesh Gateway.
            Uses action='read' with no docId, which triggers gateway's collection-stream path (returns all docs).
            Bug fix: previously used action='query' which was not handled by Gateway → returned empty list.
            """
            policies = self.client.get_policies()
            return {"policies": policies, "count": len(policies)}

        def write_memory(case_id: str, workflow_id: str, entity_type: str, summary: str, findings: List[str], assessment_decision: str, history: List[str]) -> str:
            """Write compliance review findings to Firestore Memory collection via AgentMesh Gateway."""
            return self.client.write_compliance_memory(
                case_id=case_id,
                workflow_id=workflow_id,
                entity_type=entity_type,
                summary=summary,
                findings=findings,
                assessment_decision=assessment_decision,
                history=history
            )

        def read_hr_employees(employee_id: str = "emp-001") -> dict:
            """Attempt to read HR employee records from sandbox_employees via AgentMesh Gateway (zero-trust test)."""
            return self.client.read_hr_employees()

        self.adk_tools = [
            FunctionTool(fetch_workflow),
            FunctionTool(fetch_memory),
            FunctionTool(fetch_policies),
            FunctionTool(write_memory),
            FunctionTool(read_hr_employees),
        ]

        self.adk_agent = LlmAgent(
            name="ComplianceAgent",
            model="gemini-3.5-flash",
            instruction="""You are an expert Enterprise Compliance & Policy Agent built on Google ADK.
Your roles:
1. Review paused workflows for policy compliance: fetch the workflow, fetch existing memory,
   fetch all enterprise policies, evaluate for APPROVE/REJECT/ESCALATE, write compliance findings to memory.
2. Zero-trust validation: attempt unauthorized access to HR employee records and verify denial.
All data access strictly via Gateway through FunctionTools.""",
            tools=self.adk_tools
        )

        self.runner = Runner(
            agent=self.adk_agent,
            app_name="agentmesh-compliance",
            session_service=self.session_service
        )

    def review_workflow_compliance(self, workflow_id: str) -> Dict[str, Any]:
        """RESPONSIBILITY 1: Perform formal compliance review on a paused workflow."""
        print(f"\n[*] [ComplianceAgent - ADK] Reviewing workflow '{workflow_id}' via Gateway...")

        workflow = self.client.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow '{workflow_id}' not found via Gateway.")

        case_id = f"case-{workflow.get('context', {}).get('invoiceId', 'inv-2026-007')}"
        memory = self.client.get_memory(case_id) or {}

        # Phase 9b fix: get_policies() now uses action="read" without docId,
        # which triggers the Gateway's collection-stream path returning all policy docs.
        policies = self.client.get_policies()
        print(f"[*] [ComplianceAgent - ADK] Fetched {len(policies)} policy document(s) via Gateway.")
        if policies:
            for i, p in enumerate(policies[:3], 1):
                print(f"    Policy {i}: id={p.get('docId', p.get('policyId', 'unknown'))}, effect={p.get('effect', 'unknown')}, resource={p.get('resource', 'unknown')}")

        decision, summary, findings = self.engine.evaluate_workflow_compliance(workflow, memory, policies)

        history_log = [
            f"ADK Agent compliance audit initiated for workflow {workflow_id}.",
            f"Queried {len(policies)} active enterprise policies via Gateway (action=read, collection-stream).",
            f"Gemini reasoning completed: Decision={decision}.",
        ]

        compliance_case_id = self.client.write_compliance_memory(
            case_id=case_id,
            workflow_id=workflow_id,
            entity_type="invoice_compliance_review",
            summary=summary,
            findings=findings,
            assessment_decision=decision,
            history=history_log
        )
        print(f"[+] [ComplianceAgent - ADK] Compliance memory written via Gateway: '{compliance_case_id}'.")

        return {
            "workflowId": workflow_id,
            "caseId": case_id,
            "complianceCaseId": compliance_case_id,
            "assessmentDecision": decision,
            "summary": summary,
            "findings": findings,
            "policiesQueried": len(policies),
        }

    def test_hr_data_access(self) -> Dict[str, Any]:
        """RESPONSIBILITY 2: Attempt unauthorized read of HR data (sandbox_employees) via Gateway."""
        print("\n[*] [ComplianceAgent - ADK] Executing Responsibility 2: Attempting unauthorized HR data read via Gateway...")
        res = self.client.read_hr_employees()
        return res
