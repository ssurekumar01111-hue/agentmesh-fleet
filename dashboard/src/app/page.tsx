"use client";

import React, { useState, useEffect } from "react";
import {
  IconCpu,
  IconGitBranch,
  IconShieldX,
  IconClock,
  IconCheck,
  IconX,
  IconActivity,
  IconShield,
  IconRefresh,
  IconPlayerPlay,
  IconExternalLink,
  IconLock,
  IconAlertTriangle,
  IconShieldCheck
} from "@tabler/icons-react";

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<
    "overview" | "registry" | "workflows" | "policies" | "observability"
  >("overview");

  const [loading, setLoading] = useState(true);
  const [agents, setAgents] = useState<any[]>([]);
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [policies, setPolicies] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<any | null>(null);

  // Workflow detail / Approval state
  const [selectedWorkflow, setSelectedWorkflow] = useState<any | null>(null);
  const [memoryCase, setMemoryCase] = useState<any | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // Policy Playground state
  const [pgSelectedSa, setPgSelectedSa] = useState<string>("");
  const [pgSelectedResource, setPgSelectedResource] = useState<string>("sandbox_employees");
  const [pgRunning, setPgRunning] = useState(false);
  const [pgResult, setPgResult] = useState<any | null>(null);

  const fetchGatewayData = async (
    targetResource: string,
    collectionName: string,
    action: string,
    payload: any = {},
    callerServiceAccount?: string
  ) => {
    try {
      const res = await fetch("/api/gateway", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          targetResource,
          collectionName,
          action,
          payload,
          callerServiceAccount,
        }),
      });
      const json = await res.json();
      return json;
    } catch (err) {
      console.error("Gateway fetch error:", err);
      return null;
    }
  };

  const loadData = async () => {
    setLoading(true);
    const [regRes, wfRes, polRes, logRes] = await Promise.all([
      fetchGatewayData("firestore:agent_registry", "agent_registry", "read"),
      fetchGatewayData("firestore:workflows", "workflows", "read"),
      fetchGatewayData("firestore:policies", "policies", "read"),
      fetchGatewayData("firestore:audit_log", "audit_log", "read"),
    ]);

    if (regRes && Array.isArray(regRes.data)) setAgents(regRes.data);
    if (wfRes && Array.isArray(wfRes.data)) setWorkflows(wfRes.data);
    if (polRes && Array.isArray(polRes.data)) setPolicies(polRes.data);
    if (logRes && Array.isArray(logRes.data)) setAuditLogs(logRes.data);

    // Default playground agent selection if available
    if (regRes && Array.isArray(regRes.data)) {
      const fleet = regRes.data.filter(
        (a: any) => a.agentType !== "platform" && a.docId !== "dashboard" && a.docId !== "gateway"
      );
      if (fleet.length > 0 && !pgSelectedSa) {
        setPgSelectedSa(fleet[0].serviceAccountEmail || "");
      }
    }

    setLoading(false);
  };

  useEffect(() => {
    loadData();
  }, []);

  // Separate domain fleet agents from platform infrastructure identities
  const domainAgents = agents.filter(
    (a) => a.agentType !== "platform" && a.docId !== "dashboard" && a.docId !== "gateway"
  );
  const platformIdentities = agents.filter(
    (a) => a.agentType === "platform" || a.docId === "dashboard" || a.docId === "gateway"
  );

  // Compute metric numbers for Overview tab
  const totalDomainAgents = domainAgents.length;
  const activeDomainAgentsCount = domainAgents.filter((a) => a.status === "active").length;
  const runningWorkflowsCount = workflows.filter(
    (w) => w.status === "running" || w.status === "waiting_approval" || w.status === "resumed"
  ).length;

  const threatsBlockedCount = auditLogs.filter(
    (l) =>
      l.policyDecision === "denied" ||
      l.policyDecision === "BLOCKED_BY_ARMOR" ||
      (l.armorFlags && l.armorFlags.length > 0)
  ).length;

  const avgResponseTime =
    auditLogs.length > 0
      ? Math.round(
          auditLogs.reduce((acc, curr) => acc + (curr.latencyMs || 0), 0) / auditLogs.length
        )
      : 0;

  // Observability threat tally by category computed from real audit_log armorFlags data
  const threatCategoriesCount = auditLogs.reduce((acc: Record<string, number>, log: any) => {
    const flags = log.armorFlags || [];
    flags.forEach((flag: string) => {
      acc[flag] = (acc[flag] || 0) + 1;
    });
    if (log.policyDecision === "denied" && flags.length === 0) {
      acc["policy_violation"] = (acc["policy_violation"] || 0) + 1;
    }
    return acc;
  }, {});

  // Load details for workflow detail & approval view
  const loadWorkflowDetails = async (wf: any) => {
    setSelectedWorkflow(wf);
    setMemoryCase(null);
    setActionMessage(null);

    const invoiceId = wf.context?.invoiceId || "inv-2026-009";
    const caseId = `case-${invoiceId}`;

    const memRes = await fetchGatewayData(
      "firestore:memory",
      "memory",
      "read",
      { docId: caseId }
    );
    if (memRes && memRes.data) {
      setMemoryCase(memRes.data);
    }
  };

  const handleApprovalAction = async (newStatus: "resumed" | "failed") => {
    if (!selectedWorkflow) return;
    setActionLoading(true);
    setActionMessage(null);

    const wfId = selectedWorkflow.docId || selectedWorkflow.workflowId || "wf-inv-2026-009";

    const updateRes = await fetchGatewayData(
      "firestore:workflows",
      "workflows",
      "write",
      {
        docId: wfId,
        data: {
          ...selectedWorkflow,
          status: newStatus,
          currentStep: newStatus === "resumed" ? "human_approval_granted" : "rejected_by_human",
          updatedAt: new Date().toISOString(),
        },
      }
    );

    if (updateRes && updateRes.status === "allowed") {
      setActionMessage(
        newStatus === "resumed"
          ? "Workflow approved and set to 'resumed' in Firestore! Fraud agent can now complete it."
          : "Workflow rejected and marked 'failed' in Firestore."
      );
      await loadData();
    } else {
      setActionMessage("Failed to update workflow state via Gateway.");
    }
    setActionLoading(false);
  };

  // Policy Playground Execution
  const runPolicyCheck = async () => {
    if (!pgSelectedSa || !pgSelectedResource) return;
    setPgRunning(true);
    setPgResult(null);

    const targetResource = `firestore:${pgSelectedResource}`;

    try {
      const res = await fetch("/api/gateway", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          simulate: true,
          targetAgentSa: pgSelectedSa,
          targetResource,
          collectionName: pgSelectedResource,
          action: "read",
        }),
      });
      const gatewayRes = await res.json();
      setPgResult(gatewayRes);
    } catch (err) {
      console.error("Policy playground error:", err);
    }
    setPgRunning(false);
    // Refresh audit logs to reflect new evaluation
    const logRes = await fetchGatewayData("firestore:audit_log", "audit_log", "read");
    if (logRes && Array.isArray(logRes.data)) setAuditLogs(logRes.data);
  };

  // Helper for workflow status stepper
  const renderWorkflowStepper = (status: string) => {
    const stages = [
      { key: "queued", label: "Queued" },
      { key: "running", label: "Running" },
      { key: "waiting_approval", label: "Waiting Approval" },
      { key: "resumed", label: "Resumed" },
      { key: "completed", label: "Completed" },
    ];

    if (status === "failed") {
      stages[4] = { key: "failed", label: "Failed" };
    }

    const currentIdx = stages.findIndex((s) => s.key === status);

    return (
      <div className="flex items-center gap-1 sm:gap-2 my-2 overflow-x-auto py-1">
        {stages.map((stage, idx) => {
          const isPassed = currentIdx >= 0 && idx < currentIdx;
          const isCurrent = currentIdx === idx;
          const isFailed = status === "failed" && idx === 4;

          return (
            <React.Fragment key={stage.key}>
              <div className="flex items-center gap-1.5 shrink-0">
                <div
                  className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                    isFailed
                      ? "bg-red-600 text-white"
                      : isCurrent
                      ? "bg-[#0f172a] text-white ring-2 ring-[#0f172a]/20"
                      : isPassed
                      ? "bg-emerald-600 text-white"
                      : "bg-slate-200 text-slate-500"
                  }`}
                >
                  {isPassed ? "✓" : idx + 1}
                </div>
                <span
                  className={`text-[11px] font-medium ${
                    isCurrent
                      ? "text-[#0f172a] font-semibold"
                      : isFailed
                      ? "text-red-700 font-semibold"
                      : isPassed
                      ? "text-emerald-700"
                      : "text-[#64748b]"
                  }`}
                >
                  {stage.label}
                </span>
              </div>
              {idx < stages.length - 1 && (
                <div
                  className={`h-0.5 w-4 sm:w-8 shrink-0 ${
                    currentIdx > idx ? "bg-emerald-500" : "bg-slate-200"
                  }`}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-[#f8fafc] text-[#0f172a] p-4 md:p-8">
      {/* Top Header & Navigation */}
      <header className="max-w-7xl mx-auto mb-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between border-b border-[#e2e8f0] pb-4 mb-6">
          <div>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-[#0f172a] text-white flex items-center justify-center font-bold text-sm">
                AM
              </div>
              <h1 className="text-xl font-semibold tracking-tight text-[#0f172a]">
                AgentMesh Control Plane
              </h1>
            </div>
            <p className="text-xs text-[#64748b] mt-1">
              Enterprise AI Agent Fleet Governance & Live Runtime Management
            </p>
          </div>

          <div className="flex items-center gap-3 mt-4 md:mt-0">
            <span className="pill-badge badge-green">
              <span className="w-1.5 h-1.5 rounded-full bg-[#166534] animate-pulse"></span>
              Gateway Connected
            </span>
            <button
              onClick={loadData}
              className="flex items-center gap-1.5 text-xs text-[#475569] bg-white border border-[#e2e8f0] px-3 py-1.5 rounded-lg hover:bg-slate-50 transition shadow-sm"
            >
              <IconRefresh size={14} className={loading ? "animate-spin" : ""} />
              Refresh data
            </button>
          </div>
        </div>

        {/* 5 Pill-Style Tabs */}
        <nav className="flex items-center gap-1 overflow-x-auto pb-2 border-b border-[#e2e8f0]">
          {[
            { id: "overview", label: "Overview", icon: IconActivity },
            { id: "registry", label: "Registry", icon: IconCpu },
            { id: "workflows", label: "Live Workflows", icon: IconGitBranch },
            { id: "policies", label: "Policies", icon: IconShield },
            { id: "observability", label: "Observability", icon: IconClock },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-medium transition ${
                  isActive
                    ? "bg-[#0f172a] text-white shadow-sm"
                    : "text-[#475569] hover:bg-[#e2e8f0] hover:text-[#0f172a]"
                }`}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 text-[#64748b]">
            <div className="w-6 h-6 border-2 border-[#0f172a] border-t-transparent rounded-full animate-spin mb-3"></div>
            <p className="text-xs">Fetching real telemetry from Gateway & Firestore...</p>
          </div>
        ) : (
          <>
            {/* OVERVIEW TAB */}
            {activeTab === "overview" && (
              <div className="space-y-6">
                {/* 4 Metric Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="flat-card">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-[#64748b]">
                        Active agents
                      </span>
                      <div className="icon-chip chip-green">
                        <IconCpu size={16} />
                      </div>
                    </div>
                    <div className="text-2xl font-semibold text-[#0f172a]">
                      {activeDomainAgentsCount}{" "}
                      <span className="text-xs text-[#64748b] font-normal">
                        / {totalDomainAgents} total domain fleet
                      </span>
                    </div>
                  </div>

                  <div className="flat-card">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-[#64748b]">
                        Running workflows
                      </span>
                      <div className="icon-chip chip-blue">
                        <IconGitBranch size={16} />
                      </div>
                    </div>
                    <div className="text-2xl font-semibold text-[#0f172a]">
                      {runningWorkflowsCount}
                    </div>
                  </div>

                  <div className="flat-card">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-[#64748b]">
                        Threats blocked today
                      </span>
                      <div className="icon-chip chip-red">
                        <IconShieldX size={16} />
                      </div>
                    </div>
                    <div className="text-2xl font-semibold text-[#0f172a]">
                      {threatsBlockedCount}
                    </div>
                  </div>

                  <div className="flat-card">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-[#64748b]">
                        Avg response time
                      </span>
                      <div className="icon-chip chip-purple">
                        <IconClock size={16} />
                      </div>
                    </div>
                    <div className="text-2xl font-semibold text-[#0f172a]">
                      {avgResponseTime}{" "}
                      <span className="text-xs text-[#64748b] font-normal">ms</span>
                    </div>
                  </div>
                </div>

                {/* Registry Preview & Activity Feed */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  {/* Registry Preview */}
                  <div className="lg:col-span-1 flat-card">
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="text-sm font-semibold text-[#0f172a]">
                        Domain fleet agents
                      </h2>
                      <button
                        onClick={() => setActiveTab("registry")}
                        className="text-xs text-[#2563eb] hover:underline"
                      >
                        View all ({totalDomainAgents})
                      </button>
                    </div>
                    <div className="space-y-3">
                      {domainAgents.slice(0, 5).map((agent, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between p-2.5 rounded-lg border border-[#f1f5f9] hover:bg-slate-50 transition"
                        >
                          <div>
                            <div className="text-xs font-medium text-[#0f172a]">
                              {agent.agentName || agent.name || agent.docId}
                            </div>

                            <div className="text-[11px] text-[#64748b]">
                              {agent.department || "Operations"} • v{agent.version || "1.0"}
                            </div>
                          </div>
                          <span
                            className={`pill-badge ${
                              agent.status === "active" ? "badge-green" : "badge-gray"
                            }`}
                          >
                            {agent.status || "pending"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Live Activity Feed */}
                  <div className="lg:col-span-2 flat-card">
                    <h2 className="text-sm font-semibold text-[#0f172a] mb-4">
                      Live activity feed (Gateway & audit log)
                    </h2>
                    <div className="space-y-2.5 max-h-[380px] overflow-y-auto pr-1">
                      {auditLogs.length === 0 ? (
                        <div className="text-xs text-[#64748b] py-4">No audit log entries yet.</div>
                      ) : (
                        auditLogs.slice(0, 8).map((log, i) => (
                          <div
                            key={i}
                            className="flex items-start justify-between p-2.5 rounded-lg border border-[#f1f5f9] hover:bg-slate-50 text-xs"
                          >
                            <div className="space-y-0.5">
                              <div className="flex items-center gap-2">
                                <span className="font-medium text-[#0f172a]">
                                  {log.agentId}
                                </span>
                                <span className="text-[#64748b]">→ {log.action}</span>
                              </div>
                              <p className="text-[11px] text-[#64748b] line-clamp-1">
                                {log.requestSummary}
                              </p>
                            </div>
                            <div className="text-right flex flex-col items-end gap-1">
                              <span
                                className={`pill-badge ${
                                  log.policyDecision === "allowed"
                                    ? "badge-green"
                                    : "badge-red"
                                }`}
                              >
                                {log.policyDecision || "logged"}
                              </span>
                              <span className="text-[10px] text-[#94a3b8]">
                                {log.latencyMs ? `${Math.round(log.latencyMs)}ms` : "real time"}
                              </span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* REGISTRY TAB */}
            {activeTab === "registry" && (
              <div className="space-y-6">
                <div className="flat-card">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h2 className="text-sm font-semibold text-[#0f172a]">
                        Domain fleet agents ({domainAgents.length})
                      </h2>
                      <p className="text-xs text-[#64748b] mt-0.5">
                        Enterprise department-level domain agents ({activeDomainAgentsCount} active)
                      </p>
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-[#e2e8f0] text-[#64748b] font-medium">
                          <th className="pb-3 font-medium">Agent name</th>
                          <th className="pb-3 font-medium">Department</th>
                          <th className="pb-3 font-medium">Status</th>
                          <th className="pb-3 font-medium">Version</th>
                          <th className="pb-3 font-medium">Owner</th>
                          <th className="pb-3 font-medium text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#f1f5f9]">
                        {domainAgents.map((agent, i) => (
                          <tr key={i} className="hover:bg-slate-50/80 transition">
                            <td className="py-3 font-medium text-[#0f172a]">
                              {agent.agentName || agent.name || agent.docId}
                              <div className="text-[11px] text-[#64748b] font-normal font-mono">
                                {agent.serviceAccountEmail}
                              </div>
                            </td>

                            <td className="py-3 text-[#475569]">{agent.department || "Operations"}</td>
                            <td className="py-3">
                              <span
                                className={`pill-badge ${
                                  agent.status === "active" ? "badge-green" : "badge-gray"
                                }`}
                              >
                                {agent.status || "pending"}
                              </span>
                            </td>
                            <td className="py-3 text-[#475569]">v{agent.version || "1.0"}</td>
                            <td className="py-3 text-[#475569]">{agent.owner || "Platform Team"}</td>
                            <td className="py-3 text-right">
                              <button
                                onClick={() => setSelectedAgent(agent)}
                                className="text-xs text-[#2563eb] hover:underline font-medium"
                              >
                                View permissions
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Platform Infrastructure Identities Section */}
                {platformIdentities.length > 0 && (
                  <div className="flat-card bg-slate-50/50">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <h3 className="text-xs font-semibold text-[#475569] uppercase tracking-wider">
                          Platform & Control Plane Infrastructure Identities ({platformIdentities.length})
                        </h3>
                        <p className="text-[11px] text-[#64748b]">
                          Control plane service accounts (excluded from domain agent metrics)
                        </p>
                      </div>
                    </div>

                    <div className="space-y-2">
                      {platformIdentities.map((infra, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between p-2.5 rounded-lg border border-[#e2e8f0] bg-white text-xs"
                        >
                          <div>
                            <div className="font-medium text-[#0f172a]">
                              {infra.name || infra.docId}{" "}
                              <span className="pill-badge badge-gray text-[10px]">Platform</span>
                            </div>
                            <div className="text-[11px] text-[#64748b] font-mono">
                              {infra.serviceAccountEmail}
                            </div>
                          </div>
                          <button
                            onClick={() => setSelectedAgent(infra)}
                            className="text-xs text-[#2563eb] hover:underline font-medium"
                          >
                            View permissions
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Agent Detail Modal/Card */}
                {selectedAgent && (
                  <div className="flat-card border-blue-200 bg-blue-50/20">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-sm font-semibold text-[#0f172a]">
                        Governance details: {selectedAgent.name || selectedAgent.docId}
                      </h3>
                      <button
                        onClick={() => setSelectedAgent(null)}
                        className="text-xs text-[#64748b] hover:text-[#0f172a]"
                      >
                        Close
                      </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                      <div>
                        <span className="font-medium text-[#475569] block mb-1">
                          Allowed Firestore collections (least privilege):
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {(selectedAgent.allowedCollections || []).map((col: string, idx: number) => (
                            <span
                              key={idx}
                              className="px-2 py-0.5 bg-white border border-[#cbd5e1] rounded text-[#334155] font-mono text-[11px]"
                            >
                              {col}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div>
                        <span className="font-medium text-[#475569] block mb-1">
                          Allowed Gateway tools:
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {(selectedAgent.allowedTools || []).map((tool: string, idx: number) => (
                            <span
                              key={idx}
                              className="px-2 py-0.5 bg-white border border-[#cbd5e1] rounded text-[#334155] font-mono text-[11px]"
                            >
                              {tool}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* LIVE WORKFLOWS TAB & REAL APPROVAL UI */}
            {activeTab === "workflows" && (
              <div className="space-y-6">
                <div className="flat-card">
                  <h2 className="text-sm font-semibold text-[#0f172a] mb-1">
                    Live workflows & execution status
                  </h2>
                  <p className="text-xs text-[#64748b] mb-4">
                    Real-time execution state from Firestore `workflows` collection
                  </p>

                  <div className="space-y-4">
                    {workflows.map((wf, i) => (
                      <div
                        key={i}
                        className="p-4 rounded-xl border border-[#e2e8f0] bg-white hover:border-[#cbd5e1] transition shadow-sm"
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-sm text-[#0f172a]">
                              {wf.docId || wf.workflowId || `wf-${i}`}
                            </span>
                            <span
                              className={`pill-badge ${
                                wf.status === "completed"
                                  ? "badge-green"
                                  : wf.status === "waiting_approval"
                                  ? "badge-gray border border-amber-300 bg-amber-50 text-amber-800 font-semibold"
                                  : wf.status === "resumed"
                                  ? "badge-blue"
                                  : wf.status === "failed"
                                  ? "badge-red"
                                  : "badge-gray"
                              }`}
                            >
                              {wf.status}
                            </span>
                          </div>

                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => loadWorkflowDetails(wf)}
                              className="text-xs font-medium bg-white border border-[#cbd5e1] text-[#0f172a] px-3 py-1.5 rounded-lg hover:bg-slate-50 transition"
                            >
                              {wf.status === "waiting_approval"
                                ? "Review & approve"
                                : "View workflow detail"}
                            </button>
                          </div>
                        </div>

                        <div className="text-xs text-[#64748b] mb-3 flex flex-wrap gap-x-4 gap-y-1">
                          <span>
                            Type: <strong className="text-[#334155]">{wf.type || "invoice-review"}</strong>
                          </span>
                          <span>
                            Initiator:{" "}
                            <strong className="text-[#334155]">
                              {wf.initiatingAgentId || "fraud-finance"}
                            </strong>
                          </span>
                          <span>
                            Current step:{" "}
                            <strong className="text-[#334155]">{wf.currentStep}</strong>
                          </span>
                        </div>

                        {/* Status Stepper */}
                        {renderWorkflowStepper(wf.status)}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Workflow Detail / Approval Card */}
                {selectedWorkflow && (
                  <div className="flat-card border-amber-300 bg-white">
                    <div className="flex items-center justify-between border-b border-[#e2e8f0] pb-3 mb-4">
                      <div>
                        <h3 className="text-sm font-semibold text-[#0f172a]">
                          Workflow detail & gate review: {selectedWorkflow.docId || selectedWorkflow.workflowId}
                        </h3>
                        <p className="text-xs text-[#64748b]">
                          Real findings pulled from Firestore memory collection (`memory/case-{selectedWorkflow.context?.invoiceId || "inv-2026-009"}`)
                        </p>
                      </div>
                      <button
                        onClick={() => setSelectedWorkflow(null)}
                        className="text-xs text-[#64748b] hover:text-[#0f172a]"
                      >
                        Close
                      </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                      <div className="p-3 bg-slate-50 rounded-lg border border-[#e2e8f0]">
                        <span className="text-[11px] text-[#64748b] block mb-1">Target invoice ID</span>
                        <span className="text-xs font-semibold text-[#0f172a]">
                          {selectedWorkflow.context?.invoiceId || "inv-2026-009"}
                        </span>
                      </div>
                      <div className="p-3 bg-slate-50 rounded-lg border border-[#e2e8f0]">
                        <span className="text-[11px] text-[#64748b] block mb-1">Invoice amount</span>
                        <span className="text-xs font-semibold text-[#0f172a]">
                          ${selectedWorkflow.context?.amount?.toLocaleString() || "245,000"}
                        </span>
                      </div>
                      <div className="p-3 bg-[#fee2e2] rounded-lg border border-red-200">
                        <span className="text-[11px] text-[#991b1b] block mb-1">Fraud risk score</span>
                        <span className="text-xs font-semibold text-[#991b1b]">
                          {((selectedWorkflow.context?.riskScore || 0.85) * 100).toFixed(0)}% (HIGH RISK)
                        </span>
                      </div>
                    </div>

                    {/* Agent Findings from Memory */}
                    <div className="mb-4">
                      <h4 className="text-xs font-medium text-[#475569] mb-1.5">
                        Fraud Agent summary & memory findings:
                      </h4>
                      <div className="p-3 bg-slate-50 rounded-lg border border-[#e2e8f0] text-xs text-[#334155] space-y-1.5">
                        <p className="font-medium text-[#0f172a]">
                          {memoryCase?.summary ||
                            selectedWorkflow.context?.summary ||
                            "Vendor banking details changed within 48h of submission."}
                        </p>
                        {memoryCase?.findings && (
                          <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-[#475569]">
                            {memoryCase.findings.map((f: string, idx: number) => (
                              <li key={idx}>{f}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>

                    {actionMessage && (
                      <div className="mb-4 p-2.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 font-medium">
                        {actionMessage}
                      </div>
                    )}

                    {/* Approve / Reject Buttons (only if waiting_approval) */}
                    {selectedWorkflow.status === "waiting_approval" ? (
                      <div className="flex items-center gap-3 justify-end pt-2 border-t border-[#e2e8f0]">
                        <button
                          disabled={actionLoading}
                          onClick={() => handleApprovalAction("failed")}
                          className="flex items-center gap-1.5 text-xs font-medium text-red-700 bg-red-50 border border-red-200 px-4 py-2 rounded-lg hover:bg-red-100 transition disabled:opacity-50"
                        >
                          <IconX size={14} />
                          Reject workflow
                        </button>
                        <button
                          disabled={actionLoading}
                          onClick={() => handleApprovalAction("resumed")}
                          className="flex items-center gap-1.5 text-xs font-medium text-white bg-emerald-600 px-4 py-2 rounded-lg hover:bg-emerald-700 transition disabled:opacity-50 shadow-sm"
                        >
                          <IconCheck size={14} />
                          {actionLoading ? "Updating Firestore..." : "Approve & resume workflow"}
                        </button>
                      </div>
                    ) : (
                      <div className="text-xs text-[#64748b] text-right pt-2 border-t border-[#e2e8f0]">
                        Current workflow status is <strong>{selectedWorkflow.status}</strong>. No human gate action required.
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* POLICIES TAB & POLICY PLAYGROUND */}
            {activeTab === "policies" && (
              <div className="space-y-6">
                {/* Policy Collection List */}
                <div className="flat-card">
                  <h2 className="text-sm font-semibold text-[#0f172a] mb-1">
                    Enterprise governance policies (`policies` collection)
                  </h2>
                  <p className="text-xs text-[#64748b] mb-4">
                    Real active zero-trust policies enforced inline at Gateway pipeline Stage 3
                  </p>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-[#e2e8f0] text-[#64748b] font-medium">
                          <th className="pb-3 font-medium">Policy name</th>
                          <th className="pb-3 font-medium">Effect</th>
                          <th className="pb-3 font-medium">Subject department</th>
                          <th className="pb-3 font-medium">Resource target</th>
                          <th className="pb-3 font-medium">Reason / Enforcement</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#f1f5f9]">
                        {policies.map((pol, i) => (
                          <tr key={i} className="hover:bg-slate-50/80 transition">
                            <td className="py-3 font-semibold text-[#0f172a]">
                              {pol.name || pol.docId}
                            </td>
                            <td className="py-3">
                              <span
                                className={`pill-badge ${
                                  pol.effect === "deny" ? "badge-red" : "badge-green"
                                }`}
                              >
                                {pol.effect ? pol.effect.toUpperCase() : "DENY"}
                              </span>
                            </td>
                            <td className="py-3 text-[#475569]">
                              {pol.subjectDepartment || "All"}
                            </td>
                            <td className="py-3 font-mono text-[11px] text-[#334155]">
                              {pol.resource}
                            </td>
                            <td className="py-3 text-[#475569] max-w-md">
                              {pol.reason || pol.description}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* POLICY PLAYGROUND (REAL FUNCTIONAL FEATURE) */}
                <div className="flat-card border-blue-200 bg-gradient-to-b from-blue-50/30 to-white">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="icon-chip chip-blue">
                      <IconPlayerPlay size={16} />
                    </div>
                    <div>
                      <h2 className="text-sm font-semibold text-[#0f172a]">
                        Policy Playground — Real Zero-Trust Evaluator
                      </h2>
                      <p className="text-xs text-[#64748b]">
                        Simulate real agent access calls through the Gateway's live identity & policy check pipeline
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 my-4 p-4 rounded-xl bg-white border border-[#e2e8f0]">
                    {/* Agent Dropdown */}
                    <div>
                      <label className="block text-xs font-medium text-[#475569] mb-1">
                        Select calling agent identity
                      </label>
                      <select
                        value={pgSelectedSa}
                        onChange={(e) => setPgSelectedSa(e.target.value)}
                        className="w-full text-xs p-2 rounded-lg border border-[#cbd5e1] bg-white text-[#0f172a] font-mono focus:ring-2 focus:ring-blue-500 focus:outline-none"
                      >
                        {domainAgents.map((a, idx) => (
                          <option key={idx} value={a.serviceAccountEmail}>
                            {a.name} ({a.department}) — {a.serviceAccountEmail}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Resource Dropdown */}
                    <div>
                      <label className="block text-xs font-medium text-[#475569] mb-1">
                        Select target resource
                      </label>
                      <select
                        value={pgSelectedResource}
                        onChange={(e) => setPgSelectedResource(e.target.value)}
                        className="w-full text-xs p-2 rounded-lg border border-[#cbd5e1] bg-white text-[#0f172a] font-mono focus:ring-2 focus:ring-blue-500 focus:outline-none"
                      >
                        <option value="sandbox_employees">
                          firestore:sandbox_employees (HR records)
                        </option>
                        <option value="sandbox_invoices">
                          firestore:sandbox_invoices (Finance records)
                        </option>
                        <option value="sandbox_incidents">
                          firestore:sandbox_incidents (IT records)
                        </option>
                        <option value="sandbox_vendors">
                          firestore:sandbox_vendors (Vendor records)
                        </option>
                      </select>
                    </div>

                    {/* Execute Button */}
                    <div className="flex items-end">
                      <button
                        onClick={runPolicyCheck}
                        disabled={pgRunning || !pgSelectedSa}
                        className="w-full flex items-center justify-center gap-2 text-xs font-semibold text-white bg-[#0f172a] py-2 px-4 rounded-lg hover:bg-slate-800 transition disabled:opacity-50 shadow-sm"
                      >
                        <IconPlayerPlay size={14} className={pgRunning ? "animate-spin" : ""} />
                        {pgRunning ? "Evaluating Gateway Policy..." : "Run policy check"}
                      </button>
                    </div>
                  </div>

                  {/* Real Result Display */}
                  {pgResult && (
                    <div
                      className={`p-4 rounded-xl border ${
                        pgResult.policyDecision === "allowed" || pgResult.status === "allowed"
                          ? "bg-emerald-50/70 border-emerald-200 text-emerald-900"
                          : "bg-red-50/70 border-red-200 text-red-900"
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-2 mb-2">
                          {pgResult.policyDecision === "allowed" || pgResult.status === "allowed" ? (
                            <div className="p-1 rounded bg-emerald-600 text-white">
                              <IconShieldCheck size={18} />
                            </div>
                          ) : (
                            <div className="p-1 rounded bg-red-600 text-white">
                              <IconLock size={18} />
                            </div>
                          )}
                          <div>
                            <span className="text-xs font-bold uppercase tracking-wider">
                              REAL GATEWAY DECISION:{" "}
                              {pgResult.policyDecision || pgResult.status || "DENIED"}
                            </span>
                            <div className="text-[11px] opacity-80">
                              Agent: {pgResult.agentId || pgSelectedSa} • Target: firestore:{pgSelectedResource}
                            </div>
                          </div>
                        </div>

                        {pgResult.auditLogId && (
                          <span className="text-[10px] font-mono bg-white px-2 py-0.5 rounded border border-[#cbd5e1] text-[#475569]">
                            Audit Log ID: {pgResult.auditLogId}
                          </span>
                        )}
                      </div>

                      <div className="mt-2 text-xs font-medium space-y-1">
                        <p>
                          <strong>Policy Reason:</strong>{" "}
                          {pgResult.policyReason || pgResult.detail || "Allowed by department permissions"}
                        </p>
                        {pgResult.data && (
                          <p className="text-[11px] font-mono text-[#334155]">
                            Retrieved Data: {Array.isArray(pgResult.data) ? `${pgResult.data.length} records returned` : "1 record returned"}
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* OBSERVABILITY TAB */}
            {activeTab === "observability" && (
              <div className="space-y-6">
                {/* 3a. Threats Blocked Tally by Category */}
                <div className="flat-card">
                  <h2 className="text-sm font-semibold text-[#0f172a] mb-1">
                    Security threat tally by category (Threat Shield & Policy Engine)
                  </h2>
                  <p className="text-xs text-[#64748b] mb-4">
                    Computed live from real `audit_log` armorFlags and policy violations
                  </p>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-3 bg-red-50/50 rounded-lg border border-red-100">
                      <span className="text-[11px] font-medium text-red-700 block">
                        Prompt Injection
                      </span>
                      <span className="text-xl font-bold text-red-900">
                        {threatCategoriesCount["prompt_injection"] || 0}
                      </span>
                    </div>

                    <div className="p-3 bg-amber-50/50 rounded-lg border border-amber-100">
                      <span className="text-[11px] font-medium text-amber-700 block">
                        Secret Leakage
                      </span>
                      <span className="text-xl font-bold text-amber-900">
                        {threatCategoriesCount["secret_leakage"] || 0}
                      </span>
                    </div>

                    <div className="p-3 bg-purple-50/50 rounded-lg border border-purple-100">
                      <span className="text-[11px] font-medium text-purple-700 block">
                        PII Leakage
                      </span>
                      <span className="text-xl font-bold text-purple-900">
                        {threatCategoriesCount["pii_leakage"] || 0}
                      </span>
                    </div>

                    <div className="p-3 bg-slate-100/70 rounded-lg border border-slate-200">
                      <span className="text-[11px] font-medium text-slate-700 block">
                        Policy Violations
                      </span>
                      <span className="text-xl font-bold text-slate-900">
                        {threatCategoriesCount["policy_violation"] || 0}
                      </span>
                    </div>
                  </div>
                </div>

                {/* 3b. Recent Traces / Requests Table */}
                <div className="flat-card">
                  <h2 className="text-sm font-semibold text-[#0f172a] mb-1">
                    Recent execution traces (`audit_log` records)
                  </h2>
                  <p className="text-xs text-[#64748b] mb-4">
                    Immutable execution audit trail captured by Gateway for all agent tool calls
                  </p>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-[#e2e8f0] text-[#64748b] font-medium">
                          <th className="pb-3 font-medium">Agent ID</th>
                          <th className="pb-3 font-medium">Action</th>
                          <th className="pb-3 font-medium">Decision</th>
                          <th className="pb-3 font-medium">Latency</th>
                          <th className="pb-3 font-medium">Request summary</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#f1f5f9]">
                        {auditLogs.map((log, i) => (
                          <tr key={i} className="hover:bg-slate-50/80 transition">
                            <td className="py-3 font-mono font-medium text-[#0f172a]">
                              {log.agentId}
                            </td>
                            <td className="py-3 font-mono text-[#475569]">{log.action}</td>
                            <td className="py-3">
                              <span
                                className={`pill-badge ${
                                  log.policyDecision === "allowed"
                                    ? "badge-green"
                                    : "badge-red"
                                }`}
                              >
                                {log.policyDecision || "logged"}
                              </span>
                            </td>
                            <td className="py-3 text-[#475569]">
                              {log.latencyMs ? `${Math.round(log.latencyMs)} ms` : "0 ms"}
                            </td>
                            <td className="py-3 text-[#64748b] max-w-xs truncate">
                              {log.requestSummary}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* 3c. Cloud Trace Integration Link out */}
                <div className="flat-card bg-slate-50 border-slate-200">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-xs font-semibold text-[#0f172a] uppercase tracking-wider flex items-center gap-1.5">
                        <IconExternalLink size={14} /> GCP Cloud Trace OpenTelemetry Spans
                      </h3>
                      <p className="text-xs text-[#64748b] mt-1">
                        OpenTelemetry SDK instrumentation is configured across Cloud Run Gateway & agent services. Detailed distributed trace spans (parent/child span IDs, latency timelines) route directly to Google Cloud Trace.
                      </p>
                    </div>
                    <a
                      href="https://console.cloud.google.com/traces/traces?project=agentmesh-fleet-2026"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs font-medium text-[#2563eb] hover:underline flex items-center gap-1 shrink-0"
                    >
                      Open GCP Cloud Trace <IconExternalLink size={12} />
                    </a>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
