import os
import asyncio
from typing import Dict, Any, List
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from gateway_client import GatewayClient
from reasoning import ContractReasoningEngine


class LegalContractAgent:
    """
    Legal Contract & NDA Reviewer Agent powered by Google ADK (Agent Development Kit v2.6+).

    Performs end-to-end legal contract assessment via AgentMesh Gateway:
      a. Fetches contract from Firestore via Gateway (sandbox_contracts collection).
      b. Uses Gemini reasoning to independently analyze text/clauses for legal policy compliance.
      c. Writes assessment findings to Memory via Gateway.
      d. For FLAGGED or ESCALATED contracts, creates/updates a workflows document
         at 'waiting_approval', following the standard AgentMesh workflow schema.

    CRITICAL: The agent NEVER reads pre-set policy violation flags.
    All assessment is derived from raw contract text/fields by the reasoning engine.
    All data access strictly via GatewayClient → Gateway → target resource.
    """

    def __init__(
        self,
        gateway_client: GatewayClient = None,
        reasoning_engine: ContractReasoningEngine = None,
    ):
        self.client = gateway_client or GatewayClient()
        self.engine = reasoning_engine or ContractReasoningEngine()
        self.session_service = InMemorySessionService()

        # Define ADK Function Tools wrapping Gateway client operations
        def fetch_contract(contract_id: str) -> dict:
            """Fetch a contract or NDA document by ID from sandbox_contracts via AgentMesh Gateway."""
            contract = self.client.get_contract(contract_id)
            if not contract:
                raise ValueError(f"Contract '{contract_id}' not found via Gateway.")
            return contract

        def write_memory(case_id: str, workflow_id: str, entity_type: str, summary: str, findings: List[str], risk_score: float, history: List[str]) -> str:
            """Write legal assessment findings to Firestore Memory collection via AgentMesh Gateway."""
            return self.client.write_memory(
                case_id=case_id,
                workflow_id=workflow_id,
                entity_type=entity_type,
                summary=summary,
                findings=findings,
                risk_score=risk_score,
                history=history
            )

        def update_workflow(workflow_id: str, status: str, current_step: str, context: dict) -> str:
            """Update contract review workflow state in Firestore Workflows collection via AgentMesh Gateway."""
            return self.client.update_workflow(
                workflow_id=workflow_id,
                status=status,
                current_step=current_step,
                context=context
            )

        self.adk_tools = [
            FunctionTool(fetch_contract),
            FunctionTool(write_memory),
            FunctionTool(update_workflow),
        ]

        self.adk_agent = LlmAgent(
            name="LegalContractAgent",
            model="gemini-3.5-flash",
            instruction="""You are an expert Enterprise Legal Contract & NDA Reviewer Agent built on Google ADK.
Your role is to review contracts and NDAs, analyze clauses for legal policy compliance
from raw contract text and fields (contractType, governingLaw, liabilityCapAmount, terminationClause, disputeResolution),
write findings to memory via Gateway, and update workflow state via Gateway.
You NEVER read pre-set policy violation flags.""",
            tools=self.adk_tools
        )

        self.runner = Runner(
            agent=self.adk_agent,
            app_name="agentmesh-legal-contract",
            session_service=self.session_service
        )

    def process_contract(self, contract_id: str) -> Dict[str, Any]:
        print(f"\n[*] [LegalContractAgent - ADK] Starting ADK legal review for Contract ID '{contract_id}'...")

        # Step a — Fetch contract via Gateway
        contract = self.client.get_contract(contract_id)
        if not contract:
            raise ValueError(f"Contract '{contract_id}' not found via Gateway.")

        print(
            f"[*] [LegalContractAgent - ADK] Fetched contract: {contract.get('contractType')} "
            f"with counterparty '{contract.get('vendorOrCounterparty')}'"
        )

        # Step b — Gemini reasoning (independent clause analysis from raw text)
        risk_score, summary, findings, assessment_status = self.engine.analyze_contract(contract)
        print(
            f"[*] [LegalContractAgent - ADK] Reasoning complete: "
            f"riskScore={risk_score:.2f}, status={assessment_status}"
        )

        # Step c — Write findings to Memory via Gateway
        case_id = f"case-{contract_id}"
        workflow_id = f"wf-{contract_id}"

        history_log = [
            f"ADK Agent legal review initiated for contract {contract_id}.",
            f"Counterparty: {contract.get('vendorOrCounterparty')}, Type: {contract.get('contractType')}.",
            f"Governing Law: {contract.get('governingLaw')}, Liability Cap: ${contract.get('liabilityCapAmount')}.",
            f"Gemini reasoning completed: Risk score {risk_score:.2f} ({assessment_status}).",
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
        print(f"[+] [LegalContractAgent - ADK] Memory written via Gateway for Case ID '{case_id}'.")

        # Step d — Set workflow status
        if assessment_status in ("FLAGGED", "ESCALATED"):
            wf_status = "waiting_approval"
            current_step = "human_approval_gate"
            print(
                f"[!] [LegalContractAgent - ADK] {assessment_status} detected "
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
            f"[+] [LegalContractAgent - ADK] Workflow '{workflow_id}' "
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
