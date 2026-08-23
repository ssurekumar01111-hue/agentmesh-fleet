import { NextResponse } from 'next/server';
import { GoogleAuth } from 'google-auth-library';

const GATEWAY_URL = process.env.GATEWAY_URL || "https://agentmesh-gateway-138003672216.asia-south1.run.app";
const DASHBOARD_SA = "agentmesh-dashboard@agentmesh-fleet-2026.iam.gserviceaccount.com";
const auth = new GoogleAuth();

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { targetResource, collectionName, action, payload, simulate, targetAgentSa, simulateScan, content, amount } = body;

    // Derived collection name if not passed directly
    const derivedCollection = collectionName || (targetResource && targetResource.includes(":") ? targetResource.split(":")[1] : targetResource) || "";

    let endpoint = `${GATEWAY_URL}/v1/execute`;
    let requestBody: any = {
      callerServiceAccount: DASHBOARD_SA,
      targetResource,
      collectionName: derivedCollection,
      action: action || "read",
      payload: payload || {},
      amount: amount !== undefined ? amount : (payload?.amount !== undefined ? payload.amount : undefined),
    };

    if (simulateScan || action === "simulate_scan") {
      endpoint = `${GATEWAY_URL}/v1/simulate-scan`;
      requestBody = {
        content: content !== undefined ? content : (payload?.content || ""),
      };
    } else if (simulate) {
      endpoint = `${GATEWAY_URL}/v1/simulate-policy`;
      requestBody = {
        targetAgentSa: targetAgentSa || payload?.targetAgentSa,
        targetResource,
        collectionName: derivedCollection,
        action: action || "read",
        amount: amount !== undefined ? amount : (payload?.amount !== undefined ? payload.amount : undefined),
      };
    }

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "x-emulated-sa": DASHBOARD_SA,
    };

    // Acquire GCP OIDC ID token for service-to-service Cloud Run IAM authentication
    try {
      const client = await auth.getIdTokenClient(GATEWAY_URL);
      const authHeaders = await client.getRequestHeaders(GATEWAY_URL);
      const token = authHeaders.Authorization || authHeaders.authorization;
      if (token) {
        headers["Authorization"] = token;
      }
    } catch (authErr: any) {
      console.warn("[Dashboard API] Note: ID token acquisition via GoogleAuth:", authErr.message);
    }

    const gatewayRes = await fetch(endpoint, {
      method: "POST",
      headers,
      body: JSON.stringify(requestBody),
      cache: "no-store",
    });

    const data = await gatewayRes.json();
    return NextResponse.json(data, { status: gatewayRes.status });
  } catch (error: any) {
    return NextResponse.json(
      { status: "error", detail: error.message || "Failed to contact Gateway" },
      { status: 500 }
    );
  }
}
