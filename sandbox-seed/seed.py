#!/usr/bin/env python3
"""
Seed script for AgentMesh — Northbridge Retail Co. sandbox company & Fleet Registry.
Writes real documents to Firestore database (agentmesh-fleet-2026).
"""

import os
import sys
from datetime import datetime, timezone
from google.cloud import firestore

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "agentmesh-fleet-2026")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE", "(default)")

def get_firestore_client():
    return firestore.Client(project=PROJECT_ID, database=DATABASE_ID)

# -----------------------------------------------------------------------------
# Seed Data Definitions
# -----------------------------------------------------------------------------

# 1. sandbox_vendors (5 vendors)
VENDORS = [
    {
        "id": "v-101",
        "name": "Apex Logistics Group",
        "category": "Freight & Warehousing",
        "historicalPaymentPattern": "Monthly recurring, $15,000 - $25,000",
        "riskNotes": "Established supplier, 0 anomalies in 3 years",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "v-102",
        "name": "CloudScale IT Solutions",
        "category": "Software & Cloud Services",
        "historicalPaymentPattern": "Annual subscription + variable usage, $5,000 - $12,000",
        "riskNotes": "Low risk, verified MSA on file",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "v-103",
        "name": "Global Packaging Supplies",
        "category": "Retail Packaging Materials",
        "historicalPaymentPattern": "Bi-weekly orders, $8,000 - $18,000",
        "riskNotes": "Standard supplier, occasional shipping delays",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "v-104",
        "name": "Metro Facilities Maintenance",
        "category": "Building Maintenance",
        "historicalPaymentPattern": "Monthly retainer, $4,000 - $6,000",
        "riskNotes": "Verified local vendor",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "v-105",
        "name": "Vortex Digital Marketing LLC",
        "category": "Ad Campaigns & Media",
        "historicalPaymentPattern": "Project-based, $10,000 - $30,000",
        "riskNotes": "New vendor onboarded 6 months ago, requires dual sign-off over $50k",
        "createdAt": datetime.now(timezone.utc)
    }
]

# 2. sandbox_invoices (8 invoices)
# =============================================================================
# PLANTED ANOMALOUS INVOICE: "inv-2026-007"
# Reason: Issued by "Vortex Digital Marketing LLC" (v-105) for $185,000.00.
# Historical range for v-105 is $10k - $30k with a $50k dual sign-off policy.
# An invoice of $185,000 is 6x the maximum historical payment pattern and
# triggers immediate high-risk fraud investigation workflow.
# =============================================================================
INVOICES = [
    {
        "id": "inv-2026-001",
        "vendorId": "v-101",
        "vendorName": "Apex Logistics Group",
        "amount": 18450.00,
        "currency": "USD",
        "status": "paid",
        "description": "Monthly regional freight shipment - North Region",
        "invoiceDate": "2026-07-01",
        "dueDate": "2026-07-31",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "inv-2026-002",
        "vendorId": "v-102",
        "vendorName": "CloudScale IT Solutions",
        "amount": 8900.00,
        "currency": "USD",
        "status": "paid",
        "description": "Q3 Cloud infrastructure reservation & storage",
        "invoiceDate": "2026-07-05",
        "dueDate": "2026-08-04",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "inv-2026-003",
        "vendorId": "v-103",
        "vendorName": "Global Packaging Supplies",
        "amount": 12300.50,
        "currency": "USD",
        "status": "approved",
        "description": "Custom branded eco-friendly shopping bags - 50k units",
        "invoiceDate": "2026-07-15",
        "dueDate": "2026-08-15",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "inv-2026-004",
        "vendorId": "v-104",
        "vendorName": "Metro Facilities Maintenance",
        "amount": 5200.00,
        "currency": "USD",
        "status": "pending_payment",
        "description": "Store #42 HVAC emergency repair & routine inspection",
        "invoiceDate": "2026-07-20",
        "dueDate": "2026-08-20",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "inv-2026-005",
        "vendorId": "v-101",
        "vendorName": "Apex Logistics Group",
        "amount": 21300.00,
        "currency": "USD",
        "status": "pending_approval",
        "description": "August logistics distribution - South Region hubs",
        "invoiceDate": "2026-08-01",
        "dueDate": "2026-08-31",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "inv-2026-006",
        "vendorId": "v-103",
        "vendorName": "Global Packaging Supplies",
        "amount": 15800.00,
        "currency": "USD",
        "status": "pending_approval",
        "description": "Corrugated shipping boxes - Q3 restock",
        "invoiceDate": "2026-08-02",
        "dueDate": "2026-09-01",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "inv-2026-007",  # <--- PLANTED ANOMALY
        "vendorId": "v-105",
        "vendorName": "Vortex Digital Marketing LLC",
        "amount": 185000.00,  # Extreme anomaly ($185k vs max historical $30k)
        "currency": "USD",
        "status": "flagged_review",
        "description": "Urgent Global Q3 Brand Overhaul Media Placement - Wire Required",
        "invoiceDate": "2026-08-05",
        "dueDate": "2026-08-10",
        "isAnomalous": True,
        "anomalyReason": "Invoice amount ($185,000.00) exceeds historical vendor max ($30,000.00) by 516% with urgent wire request.",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "inv-2026-008",
        "vendorId": "v-102",
        "vendorName": "CloudScale IT Solutions",
        "amount": 6400.00,
        "currency": "USD",
        "status": "pending_approval",
        "description": "Monthly Kubernetes cluster management",
        "invoiceDate": "2026-08-06",
        "dueDate": "2026-09-05",
        "createdAt": datetime.now(timezone.utc)
    }
]

# 3. sandbox_expenses (7 expense reports)
# =============================================================================
# PLANTED POLICY-VIOLATING EXPENSE: "exp-2026-006"
# Category: meals — Northbridge policy hard cap is $150 per claim.
# Amount: $1,240.00 — 8× the hard cap.
# Submission lag: expenseDate 2026-05-15, submittedDate 2026-08-07 = 84 days late.
#   Northbridge policy requires receipts submitted within 30 days of expense.
#   The lag of 84 days is 54 days beyond the policy window.
# Receipt: receiptAttached = False — no receipt provided.
# Three independent policy-violation signals the agent must compute from raw fields:
#   1. amount ($1,240) vs meals hard cap ($150) → 8× overage
#   2. (submittedDate - expenseDate) = 84 days > 30-day window → 54-day violation
#   3. receiptAttached = False → automatic policy flag
# The agent must NOT read any pre-set policyViolation or anomalyReason flag.
# =============================================================================
EXPENSES = [
    {
        "id": "exp-2026-001",
        "employeeId": "emp-002",
        "department": "Finance",
        "amount": 345.80,
        "category": "travel",
        "description": "Train tickets NYC to Boston — vendor on-site meeting, 2-day trip",
        "submittedDate": "2026-07-10",
        "expenseDate": "2026-07-08",
        "receiptAttached": True,
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "exp-2026-002",
        "employeeId": "emp-005",
        "department": "IT",
        "amount": 599.00,
        "category": "equipment",
        "description": "USB-C docking station for home office setup — WFH peripherals refresh",
        "submittedDate": "2026-07-15",
        "expenseDate": "2026-07-12",
        "receiptAttached": True,
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "exp-2026-003",
        "employeeId": "emp-001",
        "department": "Finance",
        "amount": 210.00,
        "category": "accommodation",
        "description": "Marriott hotel — 1 night, annual finance summit in Chicago",
        "submittedDate": "2026-07-20",
        "expenseDate": "2026-07-17",
        "receiptAttached": True,
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "exp-2026-004",
        "employeeId": "emp-007",
        "department": "Compliance",
        "amount": 68.50,
        "category": "meals",
        "description": "Working lunch with external auditor — 2 people",
        "submittedDate": "2026-07-22",
        "expenseDate": "2026-07-21",
        "receiptAttached": True,
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "exp-2026-005",
        "employeeId": "emp-006",
        "department": "Legal",
        "amount": 249.00,
        "category": "software",
        "description": "Annual DocuSign Business plan renewal — e-signature for contract workflows",
        "submittedDate": "2026-08-01",
        "expenseDate": "2026-07-31",
        "receiptAttached": True,
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "exp-2026-006",   # <--- PLANTED POLICY-VIOLATING EXPENSE
        "employeeId": "emp-002",
        "department": "Finance",
        "amount": 1240.00,      # 8x the $150 meals hard cap
        "category": "meals",
        "description": "Team dinner and client entertainment — invited 3 clients + 4 internal staff, upscale steakhouse",
        "submittedDate": "2026-08-07",   # 84 days after the expense date
        "expenseDate": "2026-05-15",     # actual expense incurred in May
        "receiptAttached": False,        # no receipt attached
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "exp-2026-007",
        "employeeId": "emp-003",
        "department": "HR",
        "amount": 1150.00,
        "category": "travel",
        "description": "Round-trip flights to San Francisco — HR tech conference, pre-approved by CPO",
        "submittedDate": "2026-08-05",
        "expenseDate": "2026-08-03",
        "receiptAttached": True,
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    }
]

# 4. sandbox_leave_requests (7 leave requests)
# =============================================================================
# PLANTED POLICY-VIOLATING LEAVE REQUEST: "lvr-2026-006"
# Employee: emp-002 (Marcus Chen, Senior AP Lead, Finance)
# Leave Type: annual
# Days Requested: 15 days (2026-09-01 to 2026-09-21)
# Remaining Balance: 4 days (11-day deficit, 275% over balance)
# Submission Date: 2026-08-07 -> 25 days notice for a 15-day leave request
#   (Northbridge policy requires at least 30 days notice for leave > 10 days)
# Computable signals for the HR Leave Agent:
#   1. daysRequested (15) > remainingBalance (4) -> 11-day balance deficit
#   2. Notice period (25 days) < 30-day requirement for >10 day leave
# The agent must NOT read any pre-set policyViolation or anomalyReason flag.
# =============================================================================
LEAVE_REQUESTS = [
    {
        "id": "lvr-2026-001",
        "employeeId": "emp-002",
        "department": "Finance",
        "leaveType": "annual",
        "startDate": "2026-08-18",
        "endDate": "2026-08-22",
        "daysRequested": 5,
        "remainingBalance": 18,
        "submittedDate": "2026-07-20",
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "lvr-2026-002",
        "employeeId": "emp-005",
        "department": "IT",
        "leaveType": "sick",
        "startDate": "2026-08-03",
        "endDate": "2026-08-05",
        "daysRequested": 2,
        "remainingBalance": 10,
        "submittedDate": "2026-08-03",
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "lvr-2026-003",
        "employeeId": "emp-006",
        "department": "Legal",
        "leaveType": "annual",
        "startDate": "2026-09-10",
        "endDate": "2026-09-15",
        "daysRequested": 3,
        "remainingBalance": 12,
        "submittedDate": "2026-08-01",
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "lvr-2026-004",
        "employeeId": "emp-007",
        "department": "Compliance",
        "leaveType": "annual",
        "startDate": "2026-08-25",
        "endDate": "2026-08-29",
        "daysRequested": 4,
        "remainingBalance": 8,
        "submittedDate": "2026-07-25",
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "lvr-2026-005",
        "employeeId": "emp-004",
        "department": "HR",
        "leaveType": "bereavement",
        "startDate": "2026-08-10",
        "endDate": "2026-08-12",
        "daysRequested": 3,
        "remainingBalance": 5,
        "submittedDate": "2026-08-09",
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "lvr-2026-006",   # <--- PLANTED POLICY VIOLATION
        "employeeId": "emp-002",
        "department": "Finance",
        "leaveType": "annual",
        "startDate": "2026-09-01",
        "endDate": "2026-09-21",
        "daysRequested": 15,    # 15 days requested vs 4 remaining (11-day deficit)
        "remainingBalance": 4,
        "submittedDate": "2026-08-07", # 25 days notice vs 30 days required for >10 day leave
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "lvr-2026-007",
        "employeeId": "emp-003",
        "department": "HR",
        "leaveType": "annual",
        "startDate": "2026-10-01",
        "endDate": "2026-10-07",
        "daysRequested": 5,
        "remainingBalance": 15,
        "submittedDate": "2026-08-05",
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    }
]

# 5. sandbox_contracts (5 contracts & NDAs)
# =============================================================================
# PLANTED POLICY-VIOLATING CONTRACT: "ctr-2026-005"
# Counterparty: Vortex Digital Marketing LLC (v-105)
# Contract Type: Vendor Agreement
# Governing Law: Cayman Islands (Northbridge policy requires Delaware, NY, or CA)
# Liability Cap Amount: 0 (Unlimited liability exposure / missing cap)
# Auto-Renew Notice: 3 days (30 days minimum notice required)
# Clause Summary Text: Unilateral indemnification, unlimited liability, 3-day notice.
# Computable signals for Legal Contract Agent:
#   1. governingLaw ('Cayman Islands') != Delaware/New York/California
#   2. liabilityCapAmount == 0 (unlimited liability exposure)
#   3. autoRenewNoticeDays (3) < 30-day minimum notice requirement
# The agent must NOT read any pre-set policyViolation or anomalyReason flag.
# =============================================================================
CONTRACTS = [
    {
        "id": "ctr-2026-001",
        "vendorOrCounterparty": "CloudScale IT Solutions",
        "contractType": "MSA",
        "clauseSummary": "Master Services Agreement for enterprise cloud infrastructure management. Governing law: Delaware. Liability capped at 2x annual fees ($1,000,000). Mutual indemnification for breach of confidentiality and IP infringement. 60 days written notice required prior to auto-renewal.",
        "fullText": "This Master Services Agreement ('Agreement') is entered into as of August 1, 2026 by and between CloudScale IT Solutions Inc. and Northbridge Retail Co. Section 12.1 Governing Law: This Agreement shall be governed by and construed in accordance with the laws of the State of Delaware. Section 14.2 Limitation of Liability: Neither party's aggregate liability under this Agreement shall exceed two times (2x) the total fees paid in the preceding 12 months ($1,000,000 USD). Section 15.1 Renewal: This Agreement shall automatically renew for successive 1-year terms unless either party provides written notice of non-renewal at least sixty (60) days prior to the expiration of the initial term.",
        "effectiveDate": "2026-08-01",
        "expirationDate": "2027-08-01",
        "autoRenew": True,
        "autoRenewNoticeDays": 60,
        "governingLaw": "Delaware",
        "liabilityCapAmount": 1000000.0,
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "ctr-2026-002",
        "vendorOrCounterparty": "Apex Logistics Network",
        "contractType": "SLA",
        "clauseSummary": "Service Level Agreement for regional warehouse freight dispatch. Governing law: New York. Liability cap set to $500,000 per incident. Standard mutual indemnification. 45 days notice for non-renewal.",
        "fullText": "Apex Logistics Network Freight Dispatch SLA. Section 9.1 Jurisdiction: Governed by the laws of the State of New York. Section 11.4 Limitation of Liability: Total liability for logistics delays or damages is capped at $500,000 per incident. Section 13.2 Auto-Renewal: Requires 45 days advance notice to prevent auto-renewal.",
        "effectiveDate": "2026-07-15",
        "expirationDate": "2027-07-15",
        "autoRenew": True,
        "autoRenewNoticeDays": 45,
        "governingLaw": "New York",
        "liabilityCapAmount": 500000.0,
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "ctr-2026-003",
        "vendorOrCounterparty": "Sterling HR Systems",
        "contractType": "NDA",
        "clauseSummary": "Mutual Non-Disclosure Agreement for HR software evaluation. Governing law: Delaware. Term: 2 years. Confidentiality obligations survive for 3 years post-termination. Standard mutual remedies.",
        "fullText": "Mutual Non-Disclosure Agreement between Sterling HR Systems LLC and Northbridge Retail Co. Section 8. Governing Law: State of Delaware. Section 4. Duration: Information shared under this Agreement shall remain confidential for a period of three (3) years from disclosure date.",
        "effectiveDate": "2026-08-01",
        "expirationDate": "2028-08-01",
        "autoRenew": False,
        "autoRenewNoticeDays": 0,
        "governingLaw": "Delaware",
        "liabilityCapAmount": 250000.0,
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "ctr-2026-004",
        "vendorOrCounterparty": "Pinnacle Retail Advisory",
        "contractType": "Vendor Agreement",
        "clauseSummary": "Retail strategy consulting agreement. Governing law: California. Liability cap: $100,000. 30 days notice for termination for convenience.",
        "fullText": "Consulting Agreement with Pinnacle Retail Advisory Group. Section 10. Governing Law: State of California. Section 12. Limitation of Liability: Cap of $100,000 USD. Termination for convenience requires 30 days written notice.",
        "effectiveDate": "2026-06-01",
        "expirationDate": "2026-12-01",
        "autoRenew": False,
        "autoRenewNoticeDays": 0,
        "governingLaw": "California",
        "liabilityCapAmount": 100000.0,
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "ctr-2026-005",   # <--- PLANTED POLICY VIOLATION
        "vendorOrCounterparty": "Vortex Digital Marketing LLC",
        "contractType": "Vendor Agreement",
        "clauseSummary": "Vortex Digital Marketing LLC Master Media Agreement. Governing law: Cayman Islands. Northbridge Retail Co. agrees to unlimited liability for any claims arising under this agreement. Agreement auto-renews for 3-year term unless written notice is received 3 days prior to expiration. Northbridge provides full unilateral indemnification for all counterparty losses.",
        "fullText": "Master Media Services Agreement between Vortex Digital Marketing LLC and Northbridge Retail Co. Section 14.1 Governing Law and Dispute Resolution: This Agreement and any disputes arising out of or related to it shall be exclusively governed by the laws of the Cayman Islands, without regard to conflict of laws principles. Section 16.3 Limitation of Liability: Northbridge Retail Co. expressly agrees that its liability under this Agreement shall be UNLIMITED for any indirect, direct, or consequential damages. Counterparty's total liability shall not exceed $100. Section 18.1 Renewal: This Agreement shall automatically renew for an additional three (3) year term unless Northbridge provides written notice of non-renewal at least three (3) business days prior to the expiration date. Section 19.2 Indemnification: Northbridge agrees to fully indemnify, defend, and hold harmless Vortex Digital Marketing LLC against any third-party claims, liabilities, or losses including counterparty gross negligence.",
        "effectiveDate": "2026-08-01",
        "expirationDate": "2027-08-01",
        "autoRenew": True,
        "autoRenewNoticeDays": 3,      # 3 days notice vs 30 required (27 days deficit)
        "governingLaw": "Cayman Islands", # Cayman Islands vs Delaware/NY/CA required
        "liabilityCapAmount": 0.0,    # 0 = unlimited liability / missing cap
        "status": "pending_review",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    }
]

# 6. sandbox_employees (7 employees)
EMPLOYEES = [
    {
        "id": "emp-001",
        "name": "Eleanor Vance",
        "email": "eleanor.vance@northbridge-retail.com",
        "department": "Finance",
        "role": "VP of Finance & Accounting",
        "clearance": "Executive",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "emp-002",
        "name": "Marcus Chen",
        "email": "marcus.chen@northbridge-retail.com",
        "department": "Finance",
        "role": "Senior AP Lead",
        "clearance": "Standard",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "emp-003",
        "name": "Sarah Jenkins",
        "email": "sarah.jenkins@northbridge-retail.com",
        "department": "HR",
        "role": "Chief People Officer",
        "clearance": "Confidential-HR",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "emp-004",
        "name": "David Ross",
        "email": "david.ross@northbridge-retail.com",
        "department": "HR",
        "role": "HR Generalist & Payroll Administrator",
        "clearance": "Confidential-HR",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "emp-005",
        "name": "Alex Thorne",
        "email": "alex.thorne@northbridge-retail.com",
        "department": "IT",
        "role": "Head of Cyber Security",
        "clearance": "Security-Admin",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "emp-006",
        "name": "Priya Sharma",
        "email": "priya.sharma@northbridge-retail.com",
        "department": "Legal",
        "role": "Corporate Counsel",
        "clearance": "Legal-Admin",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "emp-007",
        "name": "Robert Miller",
        "email": "robert.miller@northbridge-retail.com",
        "department": "Compliance",
        "role": "Compliance Officer",
        "clearance": "Auditor",
        "createdAt": datetime.now(timezone.utc)
    }
]

# 5. sandbox_incidents (1 starter incident)
INCIDENTS = [
    {
        "id": "inc-2026-089",
        "title": "Unrecognized SSH key added to main repo branch",
        "severity": "high",
        "status": "open",
        "affectedRepo": "ssurekumar01111-hue/Northbridge-Retail-Co.",
        "detectedBy": "agentmesh-it-security",
        "summary": "Commit #8f92a1 introduced an unauthorized deploy key without PR approval.",
        "assignedAgent": "it-security",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    }
]

# 6. agent_registry (12 entries total: 6 ACTIVE domain agents, 4 PENDING domain agents, 2 PLATFORM infrastructure identities)
REGISTRY_ENTRIES = [
    # Active Domain Agent 1
    {
        "id": "fraud-finance",
        "name": "Fraud & Finance Investigation Agent",
        "department": "Finance",
        "owner": "Finance Operations",
        "version": "1.0.0",
        "status": "active",
        "agentType": "domain",
        "description": "Reviews invoices against vendor historical baselines, flags payment anomalies, and manages approval workflows.",
        "capabilities": ["invoice-review", "vendor-lookup", "anomaly-detection"],
        "allowedTools": ["firestore:sandbox_invoices", "firestore:sandbox_vendors"],
        "allowedCollections": ["sandbox_invoices", "sandbox_vendors", "workflows", "memory", "audit_log"],
        "serviceAccountEmail": f"agentmesh-fraud-finance@{PROJECT_ID}.iam.gserviceaccount.com",
        "riskLevel": "medium",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    # Active Domain Agent 2
    {
        "id": "it-security",
        "name": "IT & Security Monitoring Agent",
        "department": "IT",
        "owner": "InfoSec Team",
        "version": "1.0.0",
        "status": "active",
        "agentType": "domain",
        "description": "Monitors GitHub code repos for unauthorized commits, secret leaks, and security issues.",
        "capabilities": ["repo-monitoring", "github-issue-triage", "secret-scanning"],
        "allowedTools": ["firestore:sandbox_incidents", "github:issues", "secretmanager:github-sandbox-pat"],
        "allowedCollections": ["sandbox_incidents", "workflows", "memory", "audit_log"],
        "serviceAccountEmail": f"agentmesh-it-security@{PROJECT_ID}.iam.gserviceaccount.com",
        "riskLevel": "high",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    # Active Domain Agent 3
    {
        "id": "compliance",
        "name": "Cross-Department Policy & Compliance Engine",
        "department": "Compliance",
        "owner": "Governance & Legal",
        "version": "1.0.0",
        "status": "active",
        "agentType": "domain",
        "description": "Evaluates cross-agent requests against organizational zero-trust data access policies.",
        "capabilities": ["policy-eval", "audit-review", "access-governance"],
        "allowedTools": ["firestore:policies", "firestore:audit_log"],
        "allowedCollections": ["policies", "audit_log", "sandbox_incidents", "workflows", "memory"],
        "serviceAccountEmail": f"agentmesh-compliance@{PROJECT_ID}.iam.gserviceaccount.com",
        "riskLevel": "high",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    # Active Domain Agent 4
    {
        "id": "expense-approval",
        "name": "Expense Report Approver",
        "department": "Finance",
        "owner": "Finance Operations",
        "version": "1.0.0",
        "status": "active",
        "agentType": "domain",
        "description": "Automated employee travel and operational expense validation against category policy limits.",
        "capabilities": ["expense-review", "policy-check", "lag-audit"],
        "allowedTools": ["firestore:sandbox_expenses", "firestore:workflows", "firestore:memory", "firestore:audit_log"],
        "allowedCollections": ["sandbox_expenses", "workflows", "memory", "audit_log"],
        "serviceAccountEmail": f"agentmesh-expense-approval@{PROJECT_ID}.iam.gserviceaccount.com",
        "riskLevel": "low",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    # Active Domain Agent 5
    {
        "id": "leave-assistant",
        "name": "Employee Leave & Vacation Assistant",
        "department": "HR",
        "owner": "HR Operations",
        "version": "1.0.0",
        "status": "active",
        "agentType": "domain",
        "description": "Processes PTO requests and checks departmental staffing coverage and policy compliance.",
        "capabilities": ["pto-booking", "policy-check", "pto-balance-eval"],
        "allowedTools": ["firestore:sandbox_leave_requests", "firestore:sandbox_employees", "firestore:workflows", "firestore:memory", "firestore:audit_log"],
        "allowedCollections": ["sandbox_leave_requests", "sandbox_employees", "workflows", "memory", "audit_log"],
        "serviceAccountEmail": f"agentmesh-hr-leave@{PROJECT_ID}.iam.gserviceaccount.com",
        "riskLevel": "low",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    # Active Domain Agent 6
    {
        "id": "contract-review",
        "name": "Legal Contract & NDA Reviewer",
        "department": "Legal",
        "owner": "Legal Department",
        "version": "1.0.0",
        "status": "active",
        "agentType": "domain",
        "description": "Checks vendor NDAs, MSAs, and sales contracts for standard clause compliance.",
        "capabilities": ["contract-parse", "clause-validation", "legal-policy-review"],
        "allowedTools": ["firestore:sandbox_contracts", "firestore:workflows", "firestore:memory", "firestore:audit_log"],
        "allowedCollections": ["sandbox_contracts", "workflows", "memory", "audit_log"],
        "serviceAccountEmail": f"agentmesh-legal-contract@{PROJECT_ID}.iam.gserviceaccount.com",
        "riskLevel": "medium",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    # Pending Domain Candidate Agents (4 Remaining)
    {
        "id": "recruitment-screener",
        "name": "Talent Acquisition Resume Screener",
        "department": "HR",
        "owner": "Talent Acquisition",
        "version": "0.1.0",
        "status": "pending",
        "agentType": "domain",
        "description": "Initial resume parsing and interview scheduling helper.",
        "capabilities": ["resume-parse", "candidate-match"],
        "allowedTools": [],
        "allowedCollections": ["sandbox_candidates"],
        "serviceAccountEmail": "",
        "riskLevel": "low",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "crm-assistant",
        "name": "Sales Opportunity & Lead Assistant",
        "department": "Sales",
        "owner": "Sales Operations",
        "version": "0.1.0",
        "status": "pending",
        "agentType": "domain",
        "description": "Enriches inbound enterprise leads and updates sales pipeline metrics.",
        "capabilities": ["lead-enrichment", "pipeline-update"],
        "allowedTools": [],
        "allowedCollections": ["sandbox_leads"],
        "serviceAccountEmail": "",
        "riskLevel": "low",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "customer-support-res",
        "name": "Customer Tier-1 Ticket Resolver",
        "department": "Support",
        "owner": "Customer Success",
        "version": "0.1.0",
        "status": "pending",
        "agentType": "domain",
        "agentType": "domain",
        "description": "Answers common order tracking inquiries and initiates replacement requests.",
        "capabilities": ["order-tracking", "ticket-resolution"],
        "allowedTools": [],
        "allowedCollections": ["sandbox_orders"],
        "serviceAccountEmail": "",
        "riskLevel": "low",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "inventory-optimizer",
        "name": "Warehouse Inventory Allocation Agent",
        "department": "Supply Chain",
        "owner": "Logistics",
        "version": "0.1.0",
        "status": "pending",
        "agentType": "domain",
        "description": "Monitors stock levels across regional retail hubs and triggers reorders.",
        "capabilities": ["stock-check", "reorder-trigger"],
        "allowedTools": [],
        "allowedCollections": ["sandbox_inventory"],
        "serviceAccountEmail": "",
        "riskLevel": "medium",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    # Platform Infrastructure Identities (2 Separate Entries)
    {
        "id": "gateway",
        "name": "Gateway Proxy",
        "department": "Infrastructure",
        "owner": "Platform Engineering",
        "version": "1.0.0",
        "status": "active",
        "agentType": "platform",
        "description": "Central zero-trust proxy enforcing authentication, identity, policy, armor, tool access, and audit logging.",
        "capabilities": ["gateway-routing", "policy-enforcement", "audit-logging"],
        "allowedTools": ["*"],
        "allowedCollections": ["*"],
        "serviceAccountEmail": f"agentmesh-gateway@{PROJECT_ID}.iam.gserviceaccount.com",
        "riskLevel": "high",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    },
    {
        "id": "dashboard",
        "name": "Dashboard UI",
        "department": "Operations",
        "owner": "Platform Engineering",
        "version": "1.0.0",
        "status": "active",
        "agentType": "platform",
        "description": "Control plane dashboard UI for monitoring fleet health, human-in-the-loop workflows, policies, and observability.",
        "capabilities": ["dashboard-ui", "workflow-management"],
        "allowedTools": ["firestore:*"],
        "allowedCollections": ["*"],
        "serviceAccountEmail": f"agentmesh-dashboard@{PROJECT_ID}.iam.gserviceaccount.com",
        "riskLevel": "low",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc)
    }
]

# 7. policies (App-layer mirror of Firestore infra rules)
# =============================================================================
# SPECIFIC DENIAL POLICY: "pol-deny-finance-hr"
# Description: Strictly denies Finance / Fraud-Finance agents from accessing
# HR employee records (sandbox_employees). Used for live zero-trust policy check.
# =============================================================================
POLICIES = [
    {
        "id": "pol-deny-finance-hr",
        "name": "Deny Finance Access to HR Data",
        "description": "Finance and Fraud agents are strictly forbidden from querying employee payroll/HR data (sandbox_employees).",
        "effect": "deny",
        "subjectDepartment": "Finance",
        "resource": "firestore:sandbox_employees",
        "reason": "Least privilege policy violation: Finance department identities may not inspect HR employee records.",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "pol-allow-finance-invoices",
        "name": "Allow Finance Access to Invoices",
        "description": "Finance agents may query and write invoice and vendor records.",
        "effect": "allow",
        "subjectDepartment": "Finance",
        "resource": "firestore:sandbox_invoices",
        "createdAt": datetime.now(timezone.utc)
    },
    {
        "id": "pol-allow-it-incidents",
        "name": "Allow IT Security Access to Incidents",
        "description": "IT Security agent may query and update security incidents.",
        "effect": "allow",
        "subjectDepartment": "IT",
        "resource": "firestore:sandbox_incidents",
        "createdAt": datetime.now(timezone.utc)
    }
]

# -----------------------------------------------------------------------------
# Execution Functions
# -----------------------------------------------------------------------------

def seed_collection(db, collection_name: str, documents: list):
    print(f"[*] Seeding collection '{collection_name}' with {len(documents)} documents...")
    batch = db.batch()
    for doc in documents:
        doc_id = doc["id"]
        doc_data = {k: v for k, v in doc.items() if k != "id"}
        ref = db.collection(collection_name).document(doc_id)
        batch.set(ref, doc_data)
    batch.commit()
    print(f"[+] Successfully seeded '{collection_name}'.")

def verify_readback(db):
    print("\n" + "=" * 60)
    print("FIRESTORE SEED READBACK VERIFICATION SUMMARY")
    print("=" * 60)

    collections = [
        "sandbox_vendors",
        "sandbox_invoices",
        "sandbox_expenses",
        "sandbox_leave_requests",
        "sandbox_contracts",
        "sandbox_employees",
        "sandbox_incidents",
        "agent_registry",
        "policies"
    ]

    counts = {}
    for col in collections:
        docs = list(db.collection(col).stream())
        counts[col] = len(docs)
        print(f"  • Collection '{col}': {len(docs)} documents")

    # Verify Planted Anomaly Invoice
    print("\n--- PLANTED ANOMALOUS INVOICE VERIFICATION ---")
    anom_ref = db.collection("sandbox_invoices").document("inv-2026-007").get()
    if anom_ref.exists:
        anom_data = anom_ref.to_dict()
        print(f"  [+] Found Invoice ID: inv-2026-007")
        print(f"      Vendor: {anom_data.get('vendorName')} ({anom_data.get('vendorId')})")
        print(f"      Amount: ${anom_data.get('amount'):,.2f}")
        print(f"      Status: {anom_data.get('status')}")
        print(f"      Is Anomalous: {anom_data.get('isAnomalous')}")
        print(f"      Reason: {anom_data.get('anomalyReason')}")
    else:
        print("  [-] ERROR: Planted anomalous invoice 'inv-2026-007' not found!")

    # Verify Planted Leave Request Violation
    print("\n--- PLANTED LEAVE REQUEST VIOLATION VERIFICATION ---")
    lvr_ref = db.collection("sandbox_leave_requests").document("lvr-2026-006").get()
    if lvr_ref.exists:
        lvr_data = lvr_ref.to_dict()
        print(f"  [+] Found Leave Request ID: lvr-2026-006")
        print(f"      Employee: {lvr_data.get('employeeId')} ({lvr_data.get('department')})")
        print(f"      Days Requested: {lvr_data.get('daysRequested')} vs Balance: {lvr_data.get('remainingBalance')}")
        print(f"      Dates: {lvr_data.get('startDate')} to {lvr_data.get('endDate')}")
    else:
        print("  [-] ERROR: Planted leave request 'lvr-2026-006' not found!")

    # Verify Planted Contract Violation
    print("\n--- PLANTED CONTRACT VIOLATION VERIFICATION ---")
    ctr_ref = db.collection("sandbox_contracts").document("ctr-2026-005").get()
    if ctr_ref.exists:
        ctr_data = ctr_ref.to_dict()
        print(f"  [+] Found Contract ID: ctr-2026-005")
        print(f"      Counterparty: {ctr_data.get('vendorOrCounterparty')}")
        print(f"      Governing Law: {ctr_data.get('governingLaw')}")
        print(f"      Liability Cap: ${ctr_data.get('liabilityCapAmount')}")
        print(f"      Auto-Renew Notice: {ctr_data.get('autoRenewNoticeDays')} days")
    else:
        print("  [-] ERROR: Planted contract 'ctr-2026-005' not found!")

    # Verify Specific Denial Policy
    print("\n--- SPECIFIC DENIAL POLICY VERIFICATION ---")
    pol_ref = db.collection("policies").document("pol-deny-finance-hr").get()
    if pol_ref.exists:
        pol_data = pol_ref.to_dict()
        print(f"  [+] Found Policy ID: pol-deny-finance-hr")
        print(f"      Name: {pol_data.get('name')}")
        print(f"      Effect: {pol_data.get('effect')}")
        print(f"      Subject Dept: {pol_data.get('subjectDepartment')}")
        print(f"      Resource: {pol_data.get('resource')}")
        print(f"      Reason: {pol_data.get('reason')}")
    else:
        print("  [-] ERROR: Denial policy 'pol-deny-finance-hr' not found!")

    print("=" * 60 + "\n")
    return counts

def main():
    print(f"[*] Initializing Firestore client for project '{PROJECT_ID}'...")
    db = get_firestore_client()

    seed_collection(db, "sandbox_vendors", VENDORS)
    seed_collection(db, "sandbox_invoices", INVOICES)
    seed_collection(db, "sandbox_expenses", EXPENSES)
    seed_collection(db, "sandbox_leave_requests", LEAVE_REQUESTS)
    seed_collection(db, "sandbox_contracts", CONTRACTS)
    seed_collection(db, "sandbox_employees", EMPLOYEES)
    seed_collection(db, "sandbox_incidents", INCIDENTS)
    seed_collection(db, "agent_registry", REGISTRY_ENTRIES)
    seed_collection(db, "policies", POLICIES)

    verify_readback(db)

if __name__ == "__main__":
    main()
