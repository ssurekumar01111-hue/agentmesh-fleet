#!/usr/bin/env python3
"""
Query Cloud Trace for the FRESH test call (just made at ~12:57 UTC).
Lists all traces from the last 15 minutes and fetches full span detail for each,
looking for the custom 'Review Expense Workflow' and 'Gemini Expense Reasoning Call' spans.
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

import google.auth
import google.auth.transport.requests

PROJECT_ID = "agentmesh-fleet-2026"


def get_token():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def api_get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def list_traces(token, minutes_back=15):
    start = (datetime.now(timezone.utc) - timedelta(minutes=minutes_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://cloudtrace.googleapis.com/v1/projects/{PROJECT_ID}/traces"
           f"?pageSize=20&startTime={start}&orderBy=start+desc")
    return api_get(url, token)


def get_trace(token, trace_id):
    url = f"https://cloudtrace.googleapis.com/v1/projects/{PROJECT_ID}/traces/{trace_id}"
    return api_get(url, token)


if __name__ == "__main__":
    token = get_token()

    print("=" * 70)
    print(f"Listing traces from last 15 minutes (looking for expense-approval spans)")
    print("=" * 70)

    result = list_traces(token, minutes_back=15)
    traces = result.get("traces", [])
    print(f"Found {len(traces)} trace(s) in list response\n")

    for t in traces:
        tid = t["traceId"]
        detail = get_trace(token, tid)
        spans = detail.get("spans", [])

        # Check if this trace has any expense-approval custom spans
        span_names = [s.get("name", "") for s in spans]
        has_custom = any(
            name in ("Review Expense Workflow", "Gemini Expense Reasoning Call")
            for name in span_names
        )
        has_expense_url = any(
            "expense-approval" in str(s.get("labels", {}))
            for s in spans
        )

        marker = " *** EXPENSE-APPROVAL TRACE ***" if (has_custom or has_expense_url) else ""
        print(f"Trace {tid} — {len(spans)} spans{marker}")

        if has_custom or has_expense_url:
            print(f"\n{'='*70}")
            print(f"FOUND EXPENSE-APPROVAL TRACE: {tid}")
            print(f"Cloud Trace URL: https://console.cloud.google.com/traces/list?project={PROJECT_ID}&tid={tid}")
            print(f"{'='*70}\n")
            for s in spans:
                name = s.get("name", "")
                labels = s.get("labels", {})
                start_t = s.get("startTime", "")
                end_t = s.get("endTime", "")
                print(f"  SPAN: {name}")
                print(f"    spanId:    {s.get('spanId')}")
                print(f"    start:     {start_t}")
                print(f"    end:       {end_t}")
                if labels:
                    interesting = {k: v for k, v in labels.items()
                                   if any(x in k.lower() for x in
                                          ['url', 'status', 'expense', 'risk', 'assessment',
                                           'model', 'category', 'receipt', 'method'])}
                    if interesting:
                        for k, v in interesting.items():
                            print(f"    {k}: {v}")
                print()
        else:
            # Show just a summary line
            url_spans = [s for s in spans if "expense-approval" in str(s.get("labels", {}))]
            review_spans = [s for s in spans if "/review" in s.get("name", "")]
            if review_spans:
                print(f"  -> has /review span but no custom spans yet")
            # Just print span names without full detail
            for s in spans[:3]:
                print(f"  span: {s.get('name')} @ {s.get('startTime','')[:19]}")
            print()
