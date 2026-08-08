import os
from typing import Dict, Any

from gateway_client import GatewayClient
from reasoning import ContractReasoningEngine


class LegalContractAgent:
    """
    Legal Contract & NDA Reviewer Agent (ADK-compliant framework agent).

    Performs end-to-end legal contract assessment via AgentMesh Gateway:
      a. Fetches contract from Firestore via Gateway (sandbox_contracts collection).
      b. Uses Gemini reasoning to independently analyze text/clauses for legal policy compliance.
      c. Writes assessment findings to Memory via Gateway.
      d. For FLAGGED or ESCALATED contracts, creates/updates a workflows document
         at 'waiting_approval', following the standard AgentMesh workflow schema.

    CRITICAL: The agent NEVER reads pre-set policy violation flags.
    All assessment is derived from raw contract text/fields by the reasoning engine.
    """

    def __init__(
        self,
        gateway_client: GatewayClient = None,
        reasoning_engine: ContractReasoningEngine = None,
    ):
        self.client = gateway_client or GatewayClient()
        self.engine = reasoning_engine or ContractReasoningEngine()

    def process_contract(self, contract_id: str) -> Dict[str, Any]:
        print(f"\n[*] [LegalContractAgent] Starting legal review for Contract ID '{contract_id}'...")

        # Step a — Fetch contract via Gateway
        contract = self.client.get_contract(contract_id)
        if not contract:
            raise ValueError(f"Contract '{contract_id}' not found via Gateway.")

        print(
            f"[*] [LegalContractAgent] Fetched contract: {contract.get('contractType')} "
            f"with counterparty '{contract.get('vendorOrCounterparty')}'"
        )

        # Step b — Gemini reasoning (independent clause analysis from raw text)
        risk_score, summary, findings, assessment_status = self.engine.analyze_contract(contract)
        print(
            f"[*] [LegalContractAgent] Reasoning complete: "
            f"riskScore={risk_score:.2f}, status={assessment_status}"
        )

        # Step c — Write findings to Memory via Gateway
        case_id = f"case-{contract_id}"
        workflow_id = f"wf-{contract_id}"

        history_log = [
            f"Legal review initiated for contract {contract_id}.",
            f"Counterparty: {contract.get('vendorOrCounterparty')}, Type: {contract.get('contractType')}.",
            f"Governing Law: {contract.get('governingLaw')}, Liability Cap: ${contract.get('liabilityCapAmount')}.",
            f"Reasoning completed: Risk score {risk_score:.2f} ({assessment_status}).",
        ]

        self.client.write_memory(
            case_id=case_id,
            workflow_id=workflow_id,
            entity_type="contract",
            summary=summary,
            findings=findings,
            risk_score=risk_score,
            history=history_log,
        )
        print(f"[+] [LegalContractAgent] Memory written via Gateway for Case ID '{case_id}'.")

        # Step d — Set workflow status
        if assessment_status in ("FLAGGED", "ESCALATED"):
            wf_status = "waiting_approval"
            current_step = "human_approval_gate"
            print(
                f"[!] [LegalContractAgent] {assessment_status} detected "
                f"(score={risk_score:.2f}). Escalating workflow to 'waiting_approval'."
            )
        else:
            wf_status = "completed"
            current_step = "review_complete"

        context = {
            "contractId": contract_id,
            "vendorOrCounterparty": contract.get("vendorOrCounterparty"),
            "contractType": contract.get("contractType"),
            "governingLaw": contract.get("governingLaw"),
            "liabilityCapAmount": contract.get("liabilityCapAmount"),
            "riskScore": risk_score,
            "assessmentStatus": assessment_status,
            "summary": summary,
            "findings": findings,
        }

        self.client.update_workflow(
            workflow_id=workflow_id,
            status=wf_status,
            current_step=current_step,
            context=context,
        )
        print(
            f"[+] [LegalContractAgent] Workflow '{workflow_id}' "
            f"set to status '{wf_status}' via Gateway."
        )

        return {
            "contractId": contract_id,
            "caseId": case_id,
            "workflowId": workflow_id,
            "riskScore": risk_score,
            "assessmentStatus": assessment_status,
            "workflowStatus": wf_status,
            "summary": summary,
            "findings": findings,
        }
