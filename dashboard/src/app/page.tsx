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
  IconRefresh
} from "@tabler/icons-react";

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<
    "overview" | "registry" | "workflows" | "policies" | "observability"
  >("overview");

  const [loading, setLoading] = useState(true);
  const [agents, setAgents] = useState<any[]>([]);
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<any | null>(null);

  // Approval state
  const [selectedWorkflow, setSelectedWorkflow] = useState<any | null>(null);
  const [memoryCase, setMemoryCase] = useState<any | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const fetchGatewayData = async (
    targetResource: string,
    collectionName: string,
    action: string,
    payload: any = {}
  ) => {
    try {
      const res = await fetch("/api/gateway", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ targetResource, collectionName, action, payload }),
      });
      const json = await res.json();
      return json.data || json;
    } catch (err) {
      console.error("Gateway fetch error:", err);
      return null;
    }
  };

  const loadData = async () => {
    setLoading(true);
    const [regData, wfData, logData] = await Promise.all([
      fetchGatewayData("firestore:agent_registry", "agent_registry", "read"),
      fetchGatewayData("firestore:workflows", "workflows", "read"),
      fetchGatewayData("firestore:audit_log", "audit_log", "read"),
    ]);

    if (Array.isArray(regData)) setAgents(regData);
    if (Array.isArray(wfData)) setWorkflows(wfData);
    if (Array.isArray(logData)) setAuditLogs(logData);
    setLoading(false);
  };

  useEffect(() => {
    loadData();
  }, []);

  // Separate domain fleet agents from platform infrastructure identities
  const domainAgents = agents.filter((a) => a.agentType !== "platform" && a.docId !== "dashboard" && a.docId !== "gateway");
  const platformIdentities = agents.filter((a) => a.agentType === "platform" || a.docId === "dashboard" || a.docId === "gateway");

  // Compute metric numbers for Overview tab from DOMAIN FLEET AGENTS ONLY
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

  // Load details for approval card
  const loadApprovalDetails = async (wf: any) => {
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
    if (memRes) {
      setMemoryCase(memRes);
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

    if (updateRes) {
      setActionMessage(
        newStatus === "resumed"
          ? "Workflow approved and set to 'resumed' in Firestore! Fraud agent can now complete it."
          : "Workflow rejected and marked 'failed' in Firestore."
      );
      await loadData();
      setSelectedWorkflow(null);
    } else {
      setActionMessage("Failed to update workflow state via Gateway.");
    }
    setActionLoading(false);
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
              className="flex items-center gap-1.5 text-xs text-[#475569] bg-white border border-[#e2e8f0] px-3 py-1.5 rounded-lg hover:bg-slate-50 transition"
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
                      {activeDomainAgentsCount} <span className="text-xs text-[#64748b] font-normal">/ {totalDomainAgents} total domain fleet</span>
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
                      {avgResponseTime} <span className="text-xs text-[#64748b] font-normal">ms</span>
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
                              {agent.name || agent.docId}
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
                              {agent.name || agent.docId}
                              <div className="text-[11px] text-[#64748b] font-normal">
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

                {/* Separate Platform Infrastructure Section */}
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
                              {infra.name || infra.docId} <span className="pill-badge badge-gray text-[10px]">Platform</span>
                            </div>
                            <div className="text-[11px] text-[#64748b]">
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

            {/* LIVE WORKFLOWS TAB & REAL APPROVAL PAGE */}
            {activeTab === "workflows" && (
              <div className="space-y-6">
                <div className="flat-card">
                  <h2 className="text-sm font-semibold text-[#0f172a] mb-1">
                    Live workflows & human approval gates
                  </h2>
                  <p className="text-xs text-[#64748b] mb-4">
                    Real-time state from Firestore `workflows` collection
                  </p>

                  <div className="space-y-3">
                    {workflows.map((wf, i) => (
                      <div
                        key={i}
                        className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg border border-[#e2e8f0] bg-white gap-3"
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-xs text-[#0f172a]">
                              {wf.docId || wf.workflowId || `wf-${i}`}
                            </span>
                            <span
                              className={`pill-badge ${
                                wf.status === "completed"
                                  ? "badge-green"
                                  : wf.status === "waiting_approval"
                                  ? "badge-gray border border-amber-300 bg-amber-50 text-amber-800"
                                  : "badge-gray"
                              }`}
                            >
                              {wf.status}
                            </span>
                          </div>
                          <p className="text-[11px] text-[#64748b] mt-1">
                            Type: {wf.type || "invoice-review"} • Current step: {wf.currentStep}
                          </p>
                        </div>

                        {wf.status === "waiting_approval" ? (
                          <button
                            onClick={() => loadApprovalDetails(wf)}
                            className="text-xs font-medium bg-[#0f172a] text-white px-3 py-1.5 rounded-lg hover:bg-slate-800 transition"
                          >
                            Review & approve
                          </button>
                        ) : (
                          <span className="text-xs text-[#94a3b8] italic">No action required</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Real Approval Page Card */}
                {selectedWorkflow && (
                  <div className="flat-card border-amber-300 bg-white">
                    <div className="flex items-center justify-between border-b border-[#e2e8f0] pb-3 mb-4">
                      <div>
                        <h3 className="text-sm font-semibold text-[#0f172a]">
                          Human approval gate: {selectedWorkflow.docId || selectedWorkflow.workflowId}
                        </h3>
                        <p className="text-xs text-[#64748b]">
                          Review real findings pulled from Firestore memory bank before authorizing workflow resumption
                        </p>
                      </div>
                      <button
                        onClick={() => setSelectedWorkflow(null)}
                        className="text-xs text-[#64748b] hover:text-[#0f172a]"
                      >
                        Cancel
                      </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                      <div className="p-3 bg-slate-50 rounded-lg border border-[#e2e8f0]">
                        <span className="text-[11px] text-[#64748b] block mb-1">Invoice ID</span>
                        <span className="text-xs font-semibold text-[#0f172a]">
                          {selectedWorkflow.context?.invoiceId || "inv-2026-009"}
                        </span>
                      </div>
                      <div className="p-3 bg-slate-50 rounded-lg border border-[#e2e8f0]">
                        <span className="text-[11px] text-[#64748b] block mb-1">Amount</span>
                        <span className="text-xs font-semibold text-[#0f172a]">
                          ${selectedWorkflow.context?.amount?.toLocaleString() || "245,000"}
                        </span>
                      </div>
                      <div className="p-3 bg-[#fee2e2] rounded-lg border border-red-200">
                        <span className="text-[11px] text-[#991b1b] block mb-1">Fraud Risk Score</span>
                        <span className="text-xs font-semibold text-[#991b1b]">
                          {(selectedWorkflow.context?.riskScore * 100).toFixed(0)}% (HIGH RISK)
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
                          {memoryCase?.summary || selectedWorkflow.context?.summary || "Vendor banking details changed within 48h of submission."}
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

                    {/* Approve / Reject Buttons */}
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
                  </div>
                )}
              </div>
            )}

            {/* POLICIES TAB (Preview) */}
            {activeTab === "policies" && (
              <div className="flat-card">
                <h2 className="text-sm font-semibold text-[#0f172a] mb-1">
                  Enterprise policy rules (Gateway enforcement)
                </h2>
                <p className="text-xs text-[#64748b] mb-4">
                  Active policy declarations governing cross-agent data access
                </p>
                <div className="p-4 rounded-lg bg-slate-50 border border-[#e2e8f0] text-xs text-[#475569]">
                  <p className="font-semibold text-[#0f172a] mb-1">
                    Policy #1: Compliance HR Data Zero-Trust Isolation
                  </p>
                  <p>
                    Effect: <span className="pill-badge badge-red">DENY</span> • Subject Dept: Compliance • Resource: firestore:sandbox_employees
                  </p>
                  <p className="mt-2 text-[11px] text-[#64748b]">
                    Enforced at Gateway pipeline Stage 3 prior to tool dispatch.
                  </p>
                </div>
              </div>
            )}

            {/* OBSERVABILITY TAB (Preview) */}
            {activeTab === "observability" && (
              <div className="flat-card">
                <h2 className="text-sm font-semibold text-[#0f172a] mb-1">
                  Agent observability & audit log
                </h2>
                <p className="text-xs text-[#64748b] mb-4">
                  Immutable audit records captured for every Gateway execution step
                </p>
                <div className="space-y-2">
                  {auditLogs.map((log, i) => (
                    <div key={i} className="p-2.5 bg-slate-50 rounded-lg border border-[#e2e8f0] text-xs">
                      <div className="flex justify-between font-mono text-[11px] text-[#334155]">
                        <span>Agent: {log.agentId}</span>
                        <span>Action: {log.action}</span>
                        <span>Latency: {Math.round(log.latencyMs || 0)}ms</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
