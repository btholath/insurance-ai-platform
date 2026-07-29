# AI Insurance Risk & Fraud Intelligence Platform

## Business Requirements Document (BRD)

**Version:** 1.0

---

## 1. Executive Summary

The objective is to build a locally deployable AI-powered Insurance
Intelligence Platform capable of assisting underwriters, fraud
investigators, customer service representatives, compliance officers,
and management by using Large Language Models together with
traditional business rules.

The system will:

- Detect fraud
- Summarize claims
- Profile customers
- Predict renewal probability
- Generate CRM communications
- Generate dashboards
- Provide explainable AI decisions
- Support human review

The entire application will run locally inside:

- Windows 11
- WSL Ubuntu
- PostgreSQL
- Django
- Redis
- Ollama (LLMs)
- Python

**No cloud services are required.**

---

## 2. Business Goals

- Reduce claim review time
- Reduce fraud losses
- Improve underwriting consistency
- Improve customer communications
- Provide explainable AI
- Provide reusable prompt templates
- Support future Agentic AI

---

## 3. Primary Users

- Fraud Analyst
- Claims Adjuster
- Customer Service
- Underwriter
- Compliance Officer
- Risk Manager
- Product Manager
- Executive Leadership
- System Administrator

---

## 4. Business Problems

Current problems include:

- Manual claim review
- Inconsistent risk assessment
- Poor fraud detection
- Time-consuming customer communications
- Little AI assistance
- Limited explainability
- No centralized prompt library

---

## 5. Scope

### Included
- Claims
- Policies
- Customers
- Renewals
- Risk
- Fraud
- CRM
- Prompt Management
- LLM
- Dashboards
- Analytics
- Audit logs
- Role security
- Workflow

### Excluded
- Payment processing
- Accounting
- ERP
- Production deployment
- External APIs

---

## 6. Functional Requirements

### Module 1 — Customer Management
Maintain:
- Customer
- Demographics
- Contact
- Policy history
- Behavior history
- Feedback
- Documents
- Communication history

### Module 2 — Policy Management
Support:
- Life
- Auto
- Property
- Health

Store:
- Premium
- Coverage
- Renewal
- Claim counts
- Risk
- Cross-sell score

### Module 3 — Claims Management
Capture:
- FNOL
- Documents
- Status
- Approval
- Denial
- Settlement
- Adjuster Notes
- Timeline
- Attachments

### Module 4 — Risk Scoring
Calculate:
- Customer Risk Score
- Policy Risk Score
- Claim Risk Score
- Renewal Probability
- Retention Score
- Behavior Score
- Cross-Sell Score

### Module 5 — Fraud Detection
Generate:
- Fraud Score
- Fraud Indicators
- Watchlists
- Fraud Alerts
- Fraud Summary
- Escalation
- Investigation Queue

### Module 6 — Behavior Analysis
Analyze:
- Customer feedback
- Email sentiment
- Call notes
- Claim history
- Renewal history
- Complaint history

Generate:
- Loyal
- Neutral
- Churn Risk
- High Risk
- VIP

### Module 7 — Prompt Library
Maintain reusable prompts for:
- Risk Summary
- Fraud Summary
- FNOL
- Emails
- CRM Notes
- Renewal
- Cross-Sell
- Executive Summary
- Policy Recommendation
- Dashboard Summary

### Module 8 — LLM Services
Support:
- Ollama
- Llama 3
- Mistral
- DeepSeek
- Phi
- Gemma
- OpenAI-compatible APIs
- Claude API (future)

### Module 9 — CRM Automation
Generate:
- Emails
- SMS
- CRM Notes
- Follow-up Tasks
- Campaign Suggestions
- Customer Summaries

### Module 10 — Dashboards
- Risk Dashboard
- Fraud Dashboard
- Claims Dashboard
- Policy Dashboard
- Executive Dashboard
- Customer Dashboard
- Renewal Dashboard

### Module 11 — Reporting
Formats:
- PDF
- Excel
- CSV
- PowerPoint
- Word

Content:
- Charts
- Trend Analysis

### Module 12 — Administration
- Users
- Roles
- Permissions
- Feature Flags
- Prompt Templates
- Models
- Settings
- Audit Logs

---

## 7. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Response Time | < 2 seconds |
| AI Response | < 10 seconds |
| Concurrent Users | 50+ |
| Database | 100GB+ |
| Availability | Local |
| Security | Role-Based Access, Encryption, Audit Logging |

---

## 8. Technical Architecture

### Frontend
- Django Templates
- Bootstrap
- HTMX
- Chart.js
- DataTables

> **Prototyping only:** Streamlit is used in Phase 0 for a disposable
> local spike (CSV + Ollama, no auth/roles/persistence) to validate
> prompt quality before building the real Prompt Library module. It is
> not part of the production frontend — Django's role-based access,
> multi-page CRUD, and admin/audit tooling (required by Modules 3, 7,
> and 12) are why the production frontend stays Django Templates +
> HTMX rather than Streamlit.

### Backend
- Python 3.13
- Django
- Django REST Framework
- Celery
- Redis
- PostgreSQL

### AI Layer
- LangChain
- LlamaIndex
- Ollama
- Prompt Templates
- Vector Search — FAISS or pgvector

### Monitoring
- Prometheus
- Grafana
- Logging: Structlog

### Deployment
- Docker
- Docker Compose
- Ubuntu WSL
- GitHub

---

## 9. Suggested Project Structure

```
insurance-ai-platform/
├── backend/
├── frontend/
├── apps/
│   ├── customers/
│   ├── policies/
│   ├── claims/
│   ├── fraud/
│   ├── risk/
│   ├── behavior/
│   ├── crm/
│   ├── reports/
│   ├── analytics/
│   ├── llm/
│   ├── prompts/
│   └── agents/
├── shared/
├── postgres/
├── docker/
├── docs/
├── tests/
├── scripts/
└── .github/
```

---

## 10. PostgreSQL Schema — Core Tables

- Customer
- Policy
- Claim
- ClaimHistory
- RiskScore
- FraudScore
- BehaviorScore
- Feedback
- Prompt
- PromptExecution
- Watchlist
- CRMActivity
- Campaign
- Renewal
- AuditLog
- User
- Role
- Permission

---

## 11. AI Features

### Claim Summary
Generate:
- Executive Summary
- Customer Summary
- Fraud Summary
- Risk Summary

### Fraud Detection
Detect:
- Inconsistencies
- Missing documents
- Suspicious behavior
- High claim frequency
- Outlier claims

### Prompt Templates
Examples:
- Generate Claim Summary
- Generate Fraud Summary
- Generate FNOL
- Generate CRM Notes
- Generate Dashboard Summary
- Generate Executive Report

---

## 12. Multi-Agent Architecture (Future Phase)

| Agent | Responsibility |
|---|---|
| **Product Agent** | Reads BRD, produces user stories |
| **Architect Agent** | Creates ADRs, architecture, database design, API design |
| **Backend Agent** | Creates Python/Django REST APIs |
| **Database Agent** | Optimizes schema, indexes, migrations |
| **Testing Agent** | Generates unit tests, integration tests, pytest suites |
| **Security Agent** | Reviews OWASP compliance, secrets, dependencies, auth/authz |
| **DevOps Agent** | Docker, Compose, GitHub Actions, deployment |
| **Documentation Agent** | Swagger, OpenAPI, Markdown, architecture docs |
| **Review Agent** | Code review — performance, security, maintainability |

---

## 13. Development Roadmap

### Phase 0 — Streamlit Spike (throwaway, not spec-driven)
- Quick local prototype: `pandas` loads the client CSV dataset directly,
  `streamlit` provides a single-page UI to pick a client and generate
  one of the prompt-library outputs (fraud summary, risk summary,
  renewal reminder, etc.) against a local Ollama model
- Goal: validate that the chosen Ollama model produces usable output
  for the actual prompt types from the prompt library, and get a feel
  for local LLM response time/quality, **before** committing to the
  Module 7/8 spec for the real Django implementation
- Explicitly disposable — vibe-coded, not run through
  `/speckit.specify`; whatever is learned here informs the real spec,
  but this code is not intended to become part of the platform itself
- No new dependencies beyond `streamlit`, `pandas`, `requests`/`ollama`
  — all free, all local

### Phase 1 — Foundation
- Project setup
- Django
- Postgres
- Redis
- Authentication
- Docker

### Phase 2 — Core Domain
- Customer
- Policy
- Claims
- CRUD

### Phase 3 — Risk Engine
- Business Rules

### Phase 4 — AI Integration
- LLM Integration (Ollama)
- Prompt Engine

### Phase 5 — Fraud & Behavior
- Fraud Detection
- Behavior Analysis
- Watchlists

### Phase 6 — Insights
- Dashboards
- Charts
- Reports

### Phase 7 — Multi-Agent System
- LangGraph
- CrewAI
- AutoGen
- OpenAI Agents SDK

### Phase 8 — Production Readiness
- Security
- Testing
- CI/CD
- Performance
- Monitoring

---

## 14. Recommended Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.13 |
| Framework | Django 5.x |
| API | Django REST Framework |
| Database | PostgreSQL 16+ |
| Cache | Redis |
| ORM | Django ORM |
| Background Jobs | Celery |
| AI Models | Ollama (Llama 3, DeepSeek, Mistral, Gemma, Phi) |
| Vector Search | pgvector (preferred) or FAISS |
| AI Orchestration | LangChain → LangGraph (later) |
| Authentication | Django Auth + JWT |
| Reporting | Pandas, OpenPyXL, python-docx, ReportLab |
| Charts | Chart.js |
| Testing | Pytest, Factory Boy, Coverage |
| Containerization | Docker & Docker Compose |
| Development | WSL Ubuntu + GitHub |

---

## 15. Recommendation

Rather than building a collection of AI prompt demos, treat this as a
**reference enterprise insurance platform**. Design it as a modular
Django application with clean domain boundaries, REST APIs, a prompt
execution engine, audit logging, explainable AI outputs, and a path
toward multi-agent orchestration.

This is intended as a portfolio-quality project demonstrating software
architecture, AI integration, backend engineering, and domain
knowledge — relevant for Lead Developer and AI Architect roles.

---

## Related documents

- `README-runbook.md` *(planned)* — phase-by-phase build, test, and
  validation sequence for WSL/Ubuntu, once implementation begins.
- `README-architecture.md` *(planned)* — detailed technical
  architecture, schema diagrams, and service boundaries once Phase 1
  is scoped.
- Spec-Driven Development artifacts (`.specify/`) — per-module specs,
  plans, and task breakdowns generated via GitHub Spec Kit, one cycle
  per roadmap phase above.