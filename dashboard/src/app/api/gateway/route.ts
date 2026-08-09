import { NextResponse } from 'next/server';
import { GoogleAuth } from 'google-auth-library';

const GATEWAY_URL = process.env.GATEWAY_URL || "https://agentmesh-gateway-138003672216.asia-south1.run.app";
const DASHBOARD_SA = "agentmesh-dashboard@agentmesh-fleet-2026.iam.gserviceaccount.com";
const auth = new GoogleAuth();

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { targetResource, collectionName, action, payload, simulate, targetAgentSa } = body;

    // Derived collection name if not passed directly
    const derivedCollection = collectionName || (targetResource && targetResource.includes(":") ? targetResource.split(":")[1] : targetResource) || "";

    const endpoint = simulate ? `${GATEWAY_URL}/v1/simulate-policy` : `${GATEWAY_URL}/v1/execute`;

    const requestBody = simulate
      ? {
          targetAgentSa: targetAgentSa || payload?.targetAgentSa,
          targetResource,
          collectionName: derivedCollection,
          action: action || "read",
        }
      : {
          callerServiceAccount: DASHBOARD_SA,
          targetResource,
          collectionName: derivedCollection,
          action: action || "read",
          payload: payload || {},
        };

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
