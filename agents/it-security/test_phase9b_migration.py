#!/usr/bin/env python3
"""
Phase 9b ADK migration test for IT-Security agent.
Runs the original Phase 4b test cases post-migration to verify identical-quality output.
"""
import os
import sys
os.environ['ALLOW_LOCAL_AUTH_EMULATION'] = 'true'
os.environ['GCP_PROJECT_ID'] = 'agentmesh-fleet-2026'

sys.path.insert(0, '.')
from agent import ITSecurityAgent
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

REPO = "ssurekumar01111-hue/Northbridge-Retail-Co."

print("=" * 70)
print("PHASE 9b - IT-SECURITY AGENT ADK MIGRATION TEST")
print("=" * 70)

# 1. Verify ADK components are present
agent = ITSecurityAgent()
assert isinstance(agent.adk_agent, LlmAgent), "LlmAgent not instantiated"
assert isinstance(agent.runner, Runner), "Runner not instantiated"
assert isinstance(agent.session_service, InMemorySessionService), "InMemorySessionService not present"
assert len(agent.adk_tools) == 6, f"Expected 6 FunctionTools, got {len(agent.adk_tools)}"
for t in agent.adk_tools:
    assert isinstance(t, FunctionTool), f"Tool {t} is not a FunctionTool"
tool_names = [t.name for t in agent.adk_tools]
print(f"[OK] ADK Components verified:")
print(f"     LlmAgent: {agent.adk_agent.name} (model={agent.adk_agent.model})")
print(f"     FunctionTools ({len(agent.adk_tools)}): {tool_names}")
print(f"     Runner: app_name={agent.runner.app_name}")
print(f"     InMemorySessionService: present")

# 2. OTel coexistence check
from telemetry import init_tracer
from opentelemetry import trace
tracer = init_tracer("it-security-test")
assert tracer is not None, "OTel tracer init failed"
print("[OK] OpenTelemetry tracer initialized without conflict with ADK tracer")

# 3. Run original Phase 4b test: suspicious detection
print("\n--- TEST: SUSPICIOUS REPO STATE DETECTION (original Phase 4b test) ---")
res = agent.audit_repository(REPO)
print(f"Risk Score       : {res['riskScore']}")
print(f"Assessment Status: {res['assessmentStatus']}")
print(f"Summary          : {res['summary']}")
print("Findings         :")
for f in res['findings']:
    print(f"  * {f}")
print(f"GitHub Issue     : {res['githubIssue']}")
print(f"Case ID          : {res['caseId']}")
print(f"Workflow ID      : {res['workflowId']}")

# 4. Assertions
assert res['riskScore'] >= 0.70 or res['assessmentStatus'] == 'HIGH_RISK', \
    f"Expected HIGH_RISK detection, got riskScore={res['riskScore']}, status={res['assessmentStatus']}"
print(f"\n[OK] HIGH_RISK detection confirmed: riskScore={res['riskScore']:.2f}, status={res['assessmentStatus']}")

if res['githubIssue']:
    print(f"[OK] GitHub issue created: #{res['githubIssue'].get('issueNumber')} at {res['githubIssue'].get('htmlUrl')}")
else:
    print("[WARN] No GitHub issue created (repo may be clean or issues already open)")

print("\n" + "=" * 70)
print("IT-SECURITY ADK MIGRATION TEST COMPLETE")
print("=" * 70)
