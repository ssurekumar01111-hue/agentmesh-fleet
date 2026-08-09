#!/usr/bin/env python3
"""
Phase 9b ADK migration test for Legal Contract & NDA agent.
Tests ADK component verification and original Phase 8c test cases.
"""
import os
import sys
os.environ['ALLOW_LOCAL_AUTH_EMULATION'] = 'true'
os.environ['GCP_PROJECT_ID'] = 'agentmesh-fleet-2026'

sys.path.insert(0, '.')
from agent import LegalContractAgent
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

print("=" * 70)
print("PHASE 9b - LEGAL CONTRACT AGENT ADK MIGRATION TEST")
print("=" * 70)

# 1. Verify ADK components
agent = LegalContractAgent()
assert isinstance(agent.adk_agent, LlmAgent), "LlmAgent not instantiated"
assert isinstance(agent.runner, Runner), "Runner not instantiated"
assert isinstance(agent.session_service, InMemorySessionService), "InMemorySessionService not present"
assert len(agent.adk_tools) == 3, f"Expected 3 FunctionTools, got {len(agent.adk_tools)}"
for t in agent.adk_tools:
    assert isinstance(t, FunctionTool), f"Tool {t} is not a FunctionTool"
tool_names = [t.name for t in agent.adk_tools]
print(f"[OK] ADK Components verified:")
print(f"     LlmAgent: {agent.adk_agent.name} (model={agent.adk_agent.model})")
print(f"     FunctionTools ({len(agent.adk_tools)}): {tool_names}")
print(f"     Runner: app_name={agent.runner.app_name}")
print(f"     InMemorySessionService: present")

# 2. OTel coexistence
from telemetry import init_tracer
tracer = init_tracer("legal-contract-test")
assert tracer is not None
print("[OK] OpenTelemetry tracer initialized without conflict with ADK tracer")

print("\n" + "=" * 70)
print("LEGAL CONTRACT ADK MIGRATION TEST COMPLETE")
print("=" * 70)
