import os
from typing import Dict, Any
from gateway_client import GatewayClient
from reasoning import ComplianceReasoningEngine

class ComplianceAgent:
    """
    Compliance & Policy Agent.
    Handles Responsibility 1 (workflow policy review & assessment) and Responsibility 2 (zero-trust HR access attempt).
    """

    def __init__(self, gateway_client: GatewayClient = None, reasoning_engine: ComplianceReasoningEngine = None):
        self.client = gateway_client or GatewayClient()
        self.engine = reasoning_engine or ComplianceReasoningEngine()

    def review_workflow_compliance(self, workflow_id: str) -> Dict[str, Any]:
        """RESPONSIBILITY 1: Perform formal compliance review on a paused workflow."""
        print(f"\n[*] [ComplianceAgent] Reviewing workflow '{workflow_id}' via Gateway...")

        workflow = self.client.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow '{workflow_id}' not found via Gateway.")

        case_id = f"case-{workflow.get('context', {}).get('invoiceId', 'inv-2026-007')}"
        memory = self.client.get_memory(case_id) or {}
        policies = self.client.get_policies()

        decision, summary, findings = self.engine.evaluate_workflow_compliance(workflow, memory, policies)

        history_log = [
            f"Compliance audit initiated for workflow {workflow_id}.",
            f"Queried {len(policies)} active enterprise policies via Gateway.",
            f"Reasoning completed: Decision={decision}."
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

        return {
            "workflowId": workflow_id,
            "caseId": case_id,
            "complianceCaseId": compliance_case_id,
            "assessmentDecision": decision,
            "summary": summary,
            "findings": findings
        }

    def test_hr_data_access(self) -> Dict[str, Any]:
        """RESPONSIBILITY 2: Attempt unauthorized read of HR data (sandbox_employees) via Gateway."""
        print("\n[*] [ComplianceAgent] Executing Responsibility 2: Attempting unauthorized HR data read via Gateway...")
        res = self.client.read_hr_employees()
        return res
