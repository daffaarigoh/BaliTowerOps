<div align="center">
  <h3>📦 BaliTowerOps — Autonomous Multi-Agent Procurement & Enterprise Intelligence Platform</h3>
  <p>
    <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python Version" />
    <img src="https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/LangGraph-AI%20Orchestrator-7C3AED?style=for-the-badge&logo=openai&logoColor=white" alt="LangGraph" />
    <img src="https://img.shields.io/badge/DuckDB-Enterprise%20OLAP-FFF000?style=for-the-badge&logo=duckdb&logoColor=black" alt="DuckDB" />
    <img src="https://img.shields.io/badge/Typst-Blazing%20PDF-239DAD?style=for-the-badge&logo=typst&logoColor=white" alt="Typst" />
    <img src="https://img.shields.io/badge/SSE-Realtime%20Stream-FF4500?style=for-the-badge" alt="SSE" />
  </p>
</div>

---

<div align="center">
  <a href="http://localhost:8050/static/executive-recap.html" title="Klik untuk membuka pemutar video interaktif">
    <img src="docs/showcase.gif" width="100%" alt="BaliTowerOps Executive Video Showcase (Animated Recap)" style="border-radius: 12px; border: 1.5px solid #004B93; box-shadow: 0 10px 30px rgba(10, 77, 156, 0.12);" />
  </a>
</div>

---

## 📝 Executive Overview

**BaliTowerOps** is an enterprise-grade autonomous multi-agent operating system engineered. Built upon **FastAPI**, **LangGraph**, **DuckDB**, and **Typst Engine**, the platform automates and orchestrates mission-critical operations across three core corporate divisions and enterprise administration:

1. **📦 Schema A — Inventory & Logistics Hubs (`usera`)**:
   Autonomous regional stock monitoring across 7 logistics hubs, algorithmic reorder calculations (*Reorder Point & Safety Stock*), multi-agent Purchase Requisition (PR) compilation, single-consolidated Purchase Order (PO) issuance, and single-click regional Goods Receipt.
2. **👥 Schema B — Human Resources & Field Operations (`userb`)**:
   Field technician/rigger leave request lifecycle, automated corporate PDF generation, pending leave audit workflows (`WF-847DA5`), interactive manager email authorization, and real-time annual leave quota balance mutation.
3. **💼 Schema C — Finance & Commercial Leasing (`userc`)**:
   Master Lease Agreement (MLA) contract onboarding for telecom operators (Telkomsel, Indosat Ooredoo Hutchison, XL Axiata, Smartfren), contractual billing schedules, financial authorization, and automated revenue invoice PDF compilation with 11% Indonesian VAT (*PPN*).
4. **👑 Enterprise Administration & Workflow Orchestration (`admin`)**:
   Natural language-to-JSON dynamic workflow compilation, cross-tenant database governance, real-time audit tracing, and system health monitoring.

---

## 🌐 Master Enterprise Architecture (Macro View)

The following master diagram illustrates how natural language prompts and web interactions flow through the central AI Gateway and Semantic Router, routing dynamically to the appropriate corporate division engine while sharing core OLAP storage, typesetting, and notification services:

```mermaid
flowchart TD
    %% USER & CLIENT INGRESS
    Client([Corporate User / Admin]) -->|Natural Language Prompt / Web Dashboard| Gateway["Enterprise AI Gateway & Two-Tier Router<br/>(agents/router.py & agent_routes.py)"]

    %% TWO-TIER ROUTING
    Gateway -->|Tier 1: Registered Admin Workflow| Tier1["Tier 1: Deterministic Workflow Engine<br/>(agents/json_executor.py)"]
    Gateway -->|Tier 2: Ad-Hoc / Direct Prompt| Tier2["Tier 2: Autonomous AI Core (Qwen-38)<br/>(agents/autonomous_agent.py)"]
    Gateway -->|'mau ajukan workflow' / Blocked Tool| WfReq["Interactive Chat Proposal Form<br/>(POST /api/workflows/request)"]

    %% TIER 1 DIVISION DISPATCH
    Tier1 -->|Schema A| EngineA["Logistics & Procurement<br/>(WF-A01 ➔ WF-A05)"]
    Tier1 -->|Schema B| EngineB["Workforce & Field Operations<br/>(WF-B01 ➔ WF-B04)"]
    Tier1 -->|Schema C| EngineC["Finance & Tower Leasing<br/>(WF-C01 ➔ WF-C04)"]

    %% TIER 2 TOOL CLASSIFICATION
    Tier2 -->|Direct / Safe Tools: tool_query_database| SafeExec["Instant Query Execution<br/>(Read-Only DuckDB & View PO)"]
    Tier2 -->|Guarded Tools: Email/PO/Threshold| Guardrail{"Role: ADMIN?"}
    Guardrail -->|Non-Admin| GuardBlocked["Tier-2 Guardrail: Block & Propose<br/>'Ajukan Alur Kerja ke Administrator'"]
    Guardrail -->|Admin| AdminExec["Authorized Admin Tool Execution"]
    GuardBlocked -.->|Propose Workflow| WfReq

    %% WORKFLOW REQUEST LIFECYCLE
    WfReq --> ReqDB[("DuckDB: workflow_requests<br/>Admin Request Queue")]
    ReqDB --> AdminPortal["Admin Portal (admin.html)<br/>Review, Validate & Compile"]
    AdminPortal --> Compiler["Workflow Compiler (workflow_compiler.py)<br/>Compiled JSON Graph ➔ DuckDB: workflows"]
    Compiler -.->|Enriches Registered Workflows| Tier1

    %% SHARED INFRASTRUCTURE
    EngineA & EngineB & EngineC & SafeExec & AdminExec --> SharedDB[("DuckDB OLAP Engine (RLS)")]
    EngineA & EngineB & EngineC & AdminExec --> DocGen["DocGen Typst Engine (PDFs)"]
    EngineA & EngineB & EngineC & AdminExec --> Dispatcher["SMTP Notification Engine"]

    %% FEEDBACK LOOP
    SharedDB & DocGen & Dispatcher -.->|Real-Time SSE Stream| Client

    %% STYLING
    style Client fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#fff
    style Gateway fill:#1e293b,stroke:#818cf8,stroke-width:2px,color:#fff
    style Tier1 fill:#0284c7,stroke:#0369a1,stroke-width:2px,color:#fff
    style Tier2 fill:#312e81,stroke:#6366f1,stroke-width:2px,color:#fff
    style WfReq fill:#0f766e,stroke:#14b8a6,stroke-width:2px,color:#fff
    style GuardBlocked fill:#7f1d1d,stroke:#ef4444,stroke-width:2px,color:#fff
    style SharedDB fill:#e2e8f0,stroke:#334155,stroke-width:2px,color:#0f172a
    style DocGen fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#0f172a
    style Dispatcher fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#0f172a
```

---

## 🔄 Detailed Division Workflows (Micro Level)

### 📦 Pipeline A: Autonomous Inventory Replenishment & Goods Receipt (`usera`)

This workflow governs physical logistics across 7 regional hubs (`WH-JKT-01`, `WH-BDG-01`, `WH-SBY-01`, `WH-SMG-01`, `WH-MDN-01`, `WH-MKS-01`, `WH-DPS-01`).

```mermaid
flowchart TD
    %% PHASE 1: DETECTION & PLANNING
    subgraph A_Phase1 ["1. Regional Stock Inspection & Multi-Agent Planning"]
        A1[("DuckDB: stock_balances<br/>(7 Regional Logistics Hubs)")] -->|Stock <= Reorder Point| A2("Trigger: Copilot Chat / Auto Scheduler")
        A2 --> A3["Planner Agent (Qwen-38)<br/>Calculate EOQ & Safety Stock, Match Best Suppliers"]
        A3 --> A4["Auditor Agent (Qwen-38)<br/>Audit Spending Caps & Budget Compliance"]
        A4 --> A5{"DocGen Typst PR"}
        A5 --> A6["Official PR Document Draft<br/>(Status: PENDING)"]
    end

    %% PHASE 2: MANAGERIAL APPROVAL
    subgraph A_Phase2 ["2. Human-In-The-Loop (HITL) Authorization"]
        A6 --> A7["SMTP Email Dispatcher<br/>(Interactive Email with Quick Approve/Reject Buttons)"]
        A6 -.->|SSE Real-Time Sync| A8["Web Dashboard: PR Tab<br/>(Badge: PENDING)"]
        A7 & A8 --> A9{"Manager Authorization"}
        A9 -->|Reject| A10["PR REJECTED<br/>Budget Allocation Released & Stock Preserved"]
    end

    %% PHASE 3: CONSOLIDATED PO ISSUANCE
    subgraph A_Phase3 ["3. Consolidated Purchase Order (PO) Issuance"]
        A9 -->|Approve| A11["PR APPROVED"]
        A11 --> A12["Consolidated PO Issued<br/>(Status: ORDERED)"]
        A12 --> A13["DocGen Typst PO<br/>(11% VAT + Indonesian Words + Specifications)"]
        A12 --> A14["Web Dashboard: PO Tab<br/>(1 Consolidated PO Row + 'Terima Barang' Button)"]
    end

    %% PHASE 4: GOODS RECEIPT & STOCK UPDATE
    subgraph A_Phase4 ["4. Physical Delivery & Single-Click Goods Receipt"]
        A14 -->|Shipment Arrives at Regional Warehouse| A15["Click 'Terima Barang' / Copilot Prompt"]
        A15 --> A16["PO Status Updated: DELIVERED<br/>(Actual Arrival Date Timestamped)"]
        A16 --> A17[("DuckDB: stock_balances<br/>(Target Warehouse Balance Incremented)")]
        A17 --> A18["Stock Health Restored:<br/>CRITICAL / LOW_STOCK ➔ NORMAL 🟢"]
    end

    style A_Phase1 fill:#f8fafc,stroke:#0284c7,stroke-width:1.5px
    style A_Phase2 fill:#fefce8,stroke:#ca8a04,stroke-width:1.5px
    style A_Phase3 fill:#f0fdf4,stroke:#16a34a,stroke-width:1.5px
    style A_Phase4 fill:#fdf4ff,stroke:#9333ea,stroke-width:1.5px
    style A1 fill:#e0f2fe,stroke:#0284c7
    style A6 fill:#fef08a,stroke:#ca8a04
    style A12 fill:#bbf7d0,stroke:#16a34a
    style A17 fill:#f5d0fe,stroke:#9333ea
```

---

### 👥 Pipeline B: Field Workforce Leave Management & Quota Deduction (`userb`)

This workflow governs field technicians and tower riggers across regional operations, ensuring leave requests undergo managerial verification before annual quotas are deducted.

```mermaid
flowchart TD
    %% PHASE 1: LEAVE SUBMISSION & FORM DRAFTING
    subgraph B_Phase1 ["1. Leave Submission & Corporate Form Drafting"]
        B1([Field Technician / Tower Rigger]) -->|Submit Leave Application| B2("Trigger: Copilot Chat / HR Web Portal")
        B2 --> B3["Validate Against Balance<br/>(DuckDB: employees.leave_balance)"]
        B3 --> B4[("DuckDB: leave_requests<br/>(Record Status: PENDING_APPROVAL)")]
        B4 --> B5["DocGen Typst Engine<br/>(Compile Official Corporate Leave Form PDF)"]
        B5 --> B6["Official Leave Form PDF Archived<br/>(storage/leave_requests/LV-2026-XXX.pdf)"]
    end

    %% PHASE 2: MANAGERIAL AUTHORIZATION & AUDIT
    subgraph B_Phase2 ["2. Human-In-The-Loop (HITL) HR Authorization & Audit"]
        B6 --> B7["Interactive HR Email Dispatcher<br/>(Manager Email with One-Click Approve/Reject URLs)"]
        B4 -.->|Real-Time SSE Sync| B8["HR Web Dashboard<br/>(Badge: PENDING_APPROVAL)"]
        B4 -.->|Audit Workflow WF-847DA5| B9["hr.query_pending_leaves Tool<br/>(Recap Pending Queue in Chat & Email)"]
        B7 & B8 & B9 --> B10{"HR Lead / Supervisor Decision"}
        B10 -->|Reject| B11["Leave REJECTED<br/>(Quota Intact, Reason Logged & Employee Notified)"]
    end

    %% PHASE 3: FORMAL APPROVAL & DIGITAL ENDORSEMENT
    subgraph B_Phase3 ["3. Formal Approval & Digital Endorsement"]
        B10 -->|Approve| B12["Leave APPROVED"]
        B12 --> B13["DocGen Typst Endorsement<br/>(Apply Official Digital Stamp to PDF Archive)"]
        B12 --> B14["Web Dashboard Notification<br/>(Badge: APPROVED 🟢)"]
    end

    %% PHASE 4: QUOTA DEDUCTION & ROSTER MUTATION
    subgraph B_Phase4 ["4. Quota Deduction & Workforce Scheduling Mutation"]
        B12 --> B15[("DuckDB: employees<br/>(Deduct Days: leave_balance = balance - days)")]
        B15 --> B16["Shift Coverage Reassigned<br/>(Substitute Technician Assigned to Tower Site)"]
        B16 --> B17["Final Confirmation Delivered<br/>(Sent to Employee & HR Compliance Audit Log)"]
    end

    style B_Phase1 fill:#f8fafc,stroke:#059669,stroke-width:1.5px
    style B_Phase2 fill:#fefce8,stroke:#ca8a04,stroke-width:1.5px
    style B_Phase3 fill:#f0fdf4,stroke:#16a34a,stroke-width:1.5px
    style B_Phase4 fill:#fdf4ff,stroke:#9333ea,stroke-width:1.5px
    style B4 fill:#fef08a,stroke:#ca8a04
    style B12 fill:#bbf7d0,stroke:#16a34a
    style B15 fill:#f5d0fe,stroke:#9333ea
```

---

### 💼 Pipeline C: Telecom Operator Onboarding & Tower Lease Invoicing (`userc`)

This workflow governs commercial leasing for telecommunication operators (Telkomsel, Indosat Ooredoo Hutchison, XL Axiata, Smartfren) utilizing PT Bali Towerindo Sentra Tbk infrastructure.

```mermaid
flowchart TD
    %% PHASE 1: REGISTRATION & CONTRACT DRAFTING
    subgraph C_Phase1 ["1. Operator Onboarding & MLA Contract Drafting"]
        C1([Account Manager / Commercial User]) -->|Register Operator & Site Lease| C2("Trigger: Copilot Chat / Commercial Portal")
        C2 --> C3["Register Client Profile<br/>(DuckDB: telecom_clients: Telkomsel, IOH, XL, Smartfren)"]
        C3 --> C4[("DuckDB: mla_contracts<br/>(Draft Contract Status: PENDING_APPROVAL)")]
        C4 --> C5["Financial Assessment Engine<br/>(Base Lease Rate + Utility Surcharge + 11% Indonesian VAT)"]
        C5 --> C6["Draft MLA Summary & Financial Projections Compiled"]
    end

    %% PHASE 2: FINANCIAL HITL AUTHORIZATION
    subgraph C_Phase2 ["2. Human-In-The-Loop (HITL) Financial Authorization"]
        C6 --> C7["Interactive Finance Email Dispatcher<br/>(CFO Preview with Cryptographic Approve/Reject Buttons)"]
        C4 -.->|Real-Time SSE Sync| C8["Finance Web Dashboard<br/>(Badge: PENDING_APPROVAL)"]
        C7 & C8 --> C9{"Finance Director / CFO Decision"}
        C9 -->|Reject| C10["Contract REJECTED<br/>(Tower Colocation Reservation Released)"]
    end

    %% PHASE 3: CONTRACT ACTIVATION & SITE HANDOVER
    subgraph C_Phase3 ["3. Contract Activation & Tower Colocation Handover"]
        C9 -->|Approve| C11["Contract APPROVED & ACTIVATED"]
        C11 --> C12[("DuckDB: mla_contracts<br/>(Status: ACTIVE, Effective Dates Locked)")]
        C12 --> C13["Tower Asset Colocation Reserved<br/>(Antenna Slot & Power Capacity Allocated on Site)"]
        C12 --> C14["Web Dashboard Notification<br/>(Badge: ACTIVE 🟢)"]
    end

    %% PHASE 4: TAX INVOICE COMPILATION & REVENUE RECOGNITION
    subgraph C_Phase4 ["4. Tax Invoice Compilation & Revenue Recognition"]
        C11 --> C15[("DuckDB: revenue_invoices<br/>(Invoice Generated: INV-2026-XXX)")]
        C15 --> C16["DocGen Typst Engine<br/>(Compile Formal Tax Invoice PDF with Letterhead & 11% VAT)"]
        C16 --> C17["Electronic Dispatch to Operator AP<br/>(Accounts Receivable Booked in Financial Ledger)"]
    end

    style C_Phase1 fill:#f8fafc,stroke:#d97706,stroke-width:1.5px
    style C_Phase2 fill:#fefce8,stroke:#ca8a04,stroke-width:1.5px
    style C_Phase3 fill:#f0fdf4,stroke:#16a34a,stroke-width:1.5px
    style C_Phase4 fill:#eff6ff,stroke:#2563eb,stroke-width:1.5px
    style C4 fill:#fef08a,stroke:#ca8a04
    style C11 fill:#bbf7d0,stroke:#16a34a
    style C15 fill:#bfdbfe,stroke:#2563eb
```

---

### 👑 Admin Pipeline: Natural Language Dynamic Workflow Orchestrator (`admin`)

Administrators can design, update, and deploy automated multi-step workflows using plain natural language without writing code.

```mermaid
flowchart LR
    Admin([Enterprise Admin]) -->|Writes Natural Language Instruction| LLM["LLM Graph Compiler<br/>(Qwen-38)"]
    LLM -->|Compiles to Structured JSON| Graph["Execution Graph JSON<br/>(Tool Steps, Tasks, Conditions)"]
    Graph -->|Stored in DuckDB| DB[("workflows Table")]
    DB -->|Triggered by User Intent| Engine["JSONExecutionEngine<br/>(agents/json_executor.py)"]
    Engine -->|Dynamic Sequential Execution| Tools["Tool Registry<br/>(Inventory, HR, Finance, DocGen, Dispatch)"]
    Tools -->|Real-time SSE Stream| Dashboard["Live Corporate Dashboard"]

    style LLM fill:#e0e7ff,stroke:#6366f1,stroke-width:1.5px
    style Graph fill:#fef3c7,stroke:#d97706,stroke-width:1.5px
    style Engine fill:#dcfce7,stroke:#16a34a,stroke-width:1.5px
```

---

## 🏛️ Multi-Tenant RBAC & Domain Governance Matrix

| Persona | Role | Division / Tenant | Database Scope | Key Operational Capabilities |
| :--- | :---: | :---: | :--- | :--- |
| **`usera`** | `USER` | `INVENTORY` (Tenant A) | `stock_balances`, `inventory_items`, `purchase_orders`, `purchase_requests`, `warehouses` | • Audit stock across 7 regional hubs<br/>• Generate PRs for low/critical items<br/>• One-click Goods Receipt (`[✓ Terima Barang]`)<br/>• Register new material SKUs |
| **`userb`** | `USER` | `HR` (Tenant B) | `employees`, `leave_requests` | • Submit rigger/technician leave requests<br/>• Execute pending leave audit (`WF-847DA5`)<br/>• Trigger HR authorization emails<br/>• Deduct approved days from annual quota |
| **`userc`** | `USER` | `FINANCE` (Tenant C) | `telecom_clients`, `mla_contracts`, `revenue_invoices`, `power_utility_expenses` | • Register telecom clients (Telkomsel, XL, IOH)<br/>• Draft tower lease contracts (MLA)<br/>• Dispatch finance authorization emails<br/>• Generate official billing invoices (11% VAT) |
| **`admin`** | `ADMIN` | `ALL` (Super Admin) | Unrestricted access across all master and tenant tables | • Natural Language Workflow Orchestrator<br/>• Cross-division AI Copilot governance<br/>• Database schema migrations & seeding<br/>• System audit logs & security monitoring |

---

## 💻 Technology Stack

| Architectural Layer | Technology Stack | Technical Specifications & Role |
| :--- | :--- | :--- |
| **Core API & Gateway** | **Python 3.10+**, **FastAPI**, **Pydantic v2** | High-performance asynchronous REST API, JWT authentication, and dependency-injected RBAC security. |
| **Multi-Agent Orchestrator** | **LangGraph**, **Qwen-38** | Multi-agent state machine coordinating mathematical planners, compliance auditors, and semantic routers. |
| **Analytical OLAP Engine** | **DuckDB Embedded** | High-speed in-process columnar SQL database with automatic transactional CSV persistence. |
| **Document Typesetting** | **Typst Compiler (Python Typst 0.11+)** | High-fidelity vector PDF typesetting engine (<50ms compilation) supporting multi-page layouts and corporate typography. |
| **Notification Engine** | **Python smtplib** / **aiosmtplib** | Corporate HTML email dispatcher with cryptographic action URLs for one-click manager authorization. |
| **User Interface** | **Semantic HTML5**, **Vanilla CSS**, **JavaScript**, **SSE** | Responsive dark/light corporate operations dashboard with zero external CSS framework bloat and live event streaming. |

---

## 🚀 Getting Started & Operational Guide

### 1. Prerequisites
- Python 3.10 or higher
- Git
- Local workstation (Windows, macOS) or Linux Server (Ubuntu 22.04+)

### 2. Installation
```bash
# 1. Clone the repository
git clone https://github.com/daffaarigoh/BaliTowerOps.git
cd BaliTowerOps

# 2. Set up virtual environment
python -m venv .venv
# On Linux / macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt
```

### 3. Database Initialization & Seeding
Initialize the DuckDB master tables and seed realistic operational data for PT Bali Towerindo Sentra Tbk:
```bash
python database/seed_data.py
```

### 4. Running the Application Server
Start the FastAPI server on port `8050`:
```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8050 --reload
```

- **Operations Dashboard**: [http://localhost:8050](http://localhost:8050)
- **Interactive Swagger Docs**: [http://localhost:8050/docs](http://localhost:8050/docs)
- **Admin Workflow Studio**: [http://localhost:8050/admin](http://localhost:8050/admin)

### 5. Default Corporate Credentials
| Username | Password | Role | Division / Access Scope |
| :--- | :--- | :--- | :--- |
| `admin` | `admin123` | `ADMIN` | Super Admin (Cross-Tenant Access & Workflow Orchestrator) |
| `usera` | `user123` | `USER` | Logistics & Inventory Hubs (Schema A) |
| `userb` | `user123` | `USER` | Human Resources & Field Operations (Schema B) |
| `userc` | `user123` | `USER` | Finance & Commercial Leasing (Schema C) |

---

## 🧪 Automated Testing Suite

The repository includes a comprehensive test suite validating all multi-agent workflows, PDF document compilers, and API endpoints:

```bash
# Run all unit and integration tests
python -m unittest discover -s tests -p "test_*.py"

# Run Typst Purchase Order (PO) compiler tests
python tests/test_po_pdf_generation.py

# Run end-to-end API pipeline integration test
python tests/test_api_and_pipeline.py
```

---

## 📂 Repository Directory Structure

```text
BaliTowerOps/
├── agents/                  # Multi-agent LangGraph logic (Planner, Auditor, Router, JSON Executor)
├── api/                     # FastAPI endpoint routers (Balitower, Approvals, Agents, Auth, Documents)
├── core/                    # System configuration, environment loader, Pydantic schemas, JWT security
├── data/                    # Persistent Bali Tower CSV datasets (Inventory, HR, Finance)
├── database/                # DuckDB initialization, master schemas, migration & seeding scripts
├── docgen/                  # Typst compilation engine & official corporate document templates
│   └── templates/           # Typst source templates (purchase_requisition, purchase_order, leave, invoice)
├── storage/                 # Generated PDF documents, local database files, and file archives
├── tests/                   # Automated unit, integration, and E2E test suite
└── web/                     # Frontend dashboard web assets
    ├── static/              # Visual assets, dashboard JavaScript modules, and CSS design system
    │   ├── css/             # Dashboard and admin stylesheets
    │   └── js/              # Client-side state managers, chat controller, and table renderers
    └── templates/           # Jinja2 / HTML index page templates
```

---
