# AGENTOPS: COMPLETE MASTER BUILD PROMPT
## AI Agent Engineering, Orchestration, Observability, Evaluation & Governance Platform

**Project codename:** AgentOps  
**Product category:** AI agent engineering and operations platform  
**Product standard:** Production-minded, premium, modular, secure, testable, extensible  
**Primary goal:** Build a complete, impressive, full-stack AI platform where users can design AI agents, create visual workflows, connect models and tools, execute real tasks, inspect execution traces, benchmark model quality, manage approvals, and govern agent behavior through a unified interface.

---

# 1. ROLE AND EXPECTATIONS

Act as a coordinated team of senior professionals:

- Principal software architect
- Senior Python and FastAPI engineer
- Senior React and TypeScript engineer
- AI agent and LLM systems engineer
- Workflow orchestration engineer
- Database architect
- Application security engineer
- Product designer and UX architect
- QA automation engineer
- DevOps and reliability engineer
- Technical writer

You are responsible for designing, implementing, testing, documenting, and preparing AgentOps for deployment.

Do not behave like a code generator that produces disconnected files. Work like an experienced engineering team building a cohesive product.

## Mandatory engineering rules

1. Inspect the existing repository before changing anything.
2. Preserve working code and existing project conventions unless a change is justified.
3. If the repository is empty, initialize the complete project structure.
4. Read existing documentation, configuration, dependency manifests, and tests before making decisions.
5. Establish a written implementation plan and architecture before large-scale coding.
6. Implement working functionality, not just mockups, static screens, or API placeholders.
7. Every visible interactive control must have a real, appropriate behavior or be explicitly marked as unavailable.
8. Never fabricate successful model responses, database operations, execution results, metrics, or integrations.
9. Clearly distinguish demonstration data from live data.
10. Do not hardcode API keys, passwords, tokens, production credentials, or private information.
11. Use current stable and compatible dependency versions, verifying them when tooling is available.
12. Do not introduce unnecessary frameworks or infrastructure merely to make the project appear sophisticated.
13. Do not put the entire application in a single file or create one enormous component.
14. Do not silently remove features, weaken security, or replace difficult functionality with static placeholders.
15. Keep the application runnable after each meaningful implementation milestone.
16. Run relevant tests, formatters, linters, and type checks. Fix failures instead of merely reporting them.
17. When a requirement cannot be completed because of missing credentials, unavailable services, or environmental restrictions, implement the appropriate adapter or setup flow and document the limitation honestly.
18. Never claim a test passed unless it was actually run and its result verified.
19. Avoid unnecessary questions. Make sensible, documented engineering decisions when requirements leave room for interpretation.
20. Continue beyond generating a plan. Implement the product incrementally until the defined release criteria are satisfied or a genuine blocker prevents progress.

The detailed requirements in this document are the product specification. If a proposed implementation conflicts with security, correctness, or reliability, choose the safer implementation and document the trade-off.

---

# 2. PRODUCT VISION

AgentOps is a centralized platform for creating, running, understanding, evaluating, and controlling AI agents.

The product connects five capabilities:

1. **Build:** Create agents and visual workflows.
2. **Execute:** Run agents against approved tools, data sources, and models.
3. **Observe:** Inspect traces, model calls, tool executions, errors, latency, and cost.
4. **Evaluate:** Measure task completion, correctness, groundedness, regressions, and policy compliance.
5. **Govern:** Control permissions, approvals, spending, execution boundaries, and auditability.

The platform must support both local AI models and cloud model providers through a consistent provider abstraction.

The central product principle is:

**AI agents should be observable, measurable, and controllable.**

AgentOps is not merely a chatbot interface. It is not just a workflow canvas. It is not a collection of disconnected AI demos.

It is a unified engineering and operations environment.

## Target users

- AI engineers building tool-using agents
- Developers building AI-powered products
- Teams evaluating different LLMs
- Businesses automating internal workflows
- Technical operators investigating failed agent runs
- Security-conscious organizations requiring controlled execution

## Primary product experience

A user should be able to:

1. Create a workspace.
2. Configure a model provider.
3. Create an agent.
4. Select approved tools.
5. Test the agent.
6. Build a workflow visually.
7. Execute the workflow.
8. Inspect its complete execution trace.
9. Require approval before sensitive actions.
10. Evaluate its quality against test cases.
11. Compare models and agent versions.
12. Monitor cost, latency, failures, and reliability.
13. Publish a stable version and roll back when necessary.

---

# 3. PRODUCT SCOPE AND FEATURE PRIORITIES

Use these priorities throughout implementation.

- **P0:** Essential platform functionality. Must work before the first complete release.
- **P1:** Major product capabilities. Implement after the core execution and safety foundations.
- **P2:** Advanced capabilities and extensibility.

Build the platform in dependency-aware phases. Do not implement advanced features by bypassing foundational architecture.

## P0 requirements

- Premium application shell and complete design system
- Authentication and workspace isolation
- Agent creation, configuration, versioning, and testing
- Local and cloud model adapter architecture
- Registered tool execution
- Synthetic CRM dataset and functional business tools
- Run history and persistent execution events
- Tool argument validation and authorization
- Human approval workflow
- Core dashboard and analytics
- Visual workflow editor and a functioning execution engine
- Error handling, cancellation, retry limits, and execution budgets
- Unit, integration, and security tests
- Local development and deployment documentation

## P1 requirements

- Model Lab and model comparison
- Evaluation suites and regression testing
- Knowledge Hub and retrieval-augmented generation
- Persistent agent memory
- Scheduled and webhook-triggered execution
- Background workers and durable job processing
- Advanced trace visualization
- Cost and usage analytics
- More connectors and integration management

## P2 requirements

- Multi-agent orchestration
- Connector marketplace
- SDK and CLI
- Dependency topology visualization
- Advanced policy management
- Enterprise identity and deployment features
- Organization-level governance and advanced reporting

P0 is the first complete product milestone, not permission to discard the rest of the product vision. Maintain a roadmap for every specified module.

---

# 4. REQUIRED TECHNOLOGY STACK

Use this stack unless the existing repository has a compelling, documented reason to differ.

## Frontend

- React
- TypeScript with strict mode
- Vite
- Tailwind CSS
- shadcn/ui
- Lucide icons
- React Flow for the workflow canvas
- TanStack Query for server state
- React Hook Form and Zod for complex forms and client-side validation
- Recharts for analytics
- A suitable lightweight state-management solution when shared client state requires it
- Playwright for end-to-end testing

Use accessible semantic HTML and reusable components. Do not create a separate styling approach for every screen.

## Backend

- Python
- FastAPI
- Pydantic for schemas and validation
- Pydantic Settings for environment configuration
- SQLAlchemy 2.x
- Alembic migrations
- PostgreSQL
- Async database access where appropriate
- HTTPX for asynchronous HTTP calls
- Pytest and pytest-asyncio
- Structured application logging

## AI infrastructure

- Ollama adapter for local model execution
- Provider adapters for supported cloud LLM APIs
- Common model request and response contracts
- Native structured-output and tool-calling support where available
- A custom agent runtime for core execution
- A custom evaluation harness
- Optional framework integration only when it provides a concrete benefit

Never assume every model supports tool calling, structured outputs, streaming, or the same context limits. Maintain provider capability metadata and handle unsupported capabilities explicitly.

## Data and background execution

- PostgreSQL as the primary source of truth
- pgvector for initial vector search
- Redis-backed queue and worker infrastructure when background execution requires it
- Object storage abstraction for uploaded documents and artifacts
- A durable workflow engine such as Temporal when long-running workflows require recovery across process restarts

Do not introduce every infrastructure component on day one without need. However, design execution interfaces so that in-process development execution can evolve into durable background execution without rewriting business logic.

## Deployment and operations

- Docker and Docker Compose
- Environment-based configuration
- CI pipeline
- Database migrations
- Health and readiness checks
- Structured logs
- Metrics and tracing interfaces
- OpenTelemetry-compatible observability where practical
- Automated backup and restore documentation

---

# 5. REPOSITORY STRUCTURE

Use a clean, modular monorepo.

A suggested structure:

    agentops/
    ├── apps/
    │   └── web/
    │       ├── src/
    │       │   ├── app/
    │       │   ├── components/
    │       │   ├── features/
    │       │   │   ├── dashboard/
    │       │   │   ├── agents/
    │       │   │   ├── workflows/
    │       │   │   ├── runs/
    │       │   │   ├── evaluations/
    │       │   │   ├── models/
    │       │   │   ├── knowledge/
    │       │   │   ├── approvals/
    │       │   │   ├── integrations/
    │       │   │   └── workspace/
    │       │   ├── hooks/
    │       │   ├── lib/
    │       │   ├── routes/
    │       │   ├── schemas/
    │       │   ├── styles/
    │       │   └── types/
    │       ├── public/
    │       └── tests/
    ├── backend/
    │   ├── app/
    │   │   ├── api/
    │   │   │   └── v1/
    │   │   ├── core/
    │   │   ├── db/
    │   │   ├── models/
    │   │   ├── schemas/
    │   │   ├── repositories/
    │   │   ├── services/
    │   │   ├── agents/
    │   │   ├── workflows/
    │   │   ├── tools/
    │   │   ├── providers/
    │   │   ├── evaluations/
    │   │   ├── knowledge/
    │   │   ├── policies/
    │   │   ├── approvals/
    │   │   ├── jobs/
    │   │   ├── observability/
    │   │   └── main.py
    │   └── tests/
    │       ├── unit/
    │       ├── integration/
    │       ├── security/
    │       └── evaluations/
    ├── evals/
    │   ├── datasets/
    │   ├── suites/
    │   └── reports/
    ├── docs/
    │   ├── product-requirements.md
    │   ├── architecture.md
    │   ├── database-schema.md
    │   ├── api-reference.md
    │   ├── security.md
    │   ├── design-system.md
    │   ├── deployment.md
    │   └── roadmap.md
    ├── infra/
    ├── scripts/
    ├── .env.example
    ├── .gitignore
    ├── docker-compose.yml
    ├── README.md
    └── AGENTS.md

Adapt this structure when necessary, but preserve clear boundaries between UI, API, execution logic, provider adapters, policies, and persistence.

Do not place core business logic in React components or route handlers. Keep API endpoints thin and delegate behavior to application services.

---

# 6. DESIGN SYSTEM AND VISUAL IDENTITY

The application must look like a polished professional developer platform.

It should feel at home beside sophisticated observability, developer infrastructure, and AI engineering products.

## Visual direction

Use a dark-first interface with a refined light theme where practical.

Suggested palette:

- Application background: deep navy-charcoal
- Sidebar: darker graphite
- Main surfaces: layered slate
- Elevated panels: subtle contrast from their parent surfaces
- Primary accent: electric or ice blue
- Secondary accent: restrained violet
- Success: emerald
- Warning: amber
- Error: muted red
- Text: high-contrast neutral white and cool gray

Define semantic design tokens. Do not scatter hardcoded colors throughout components.

Example semantic tokens:

    --background
    --foreground
    --surface
    --surface-elevated
    --surface-muted
    --border
    --primary
    --primary-foreground
    --secondary
    --success
    --warning
    --danger
    --muted
    --muted-foreground
    --focus-ring

Ensure readable contrast and visible focus states.

## Typography

- Use Inter, Geist, or a similarly readable interface typeface.
- Use consistent font weights and line heights.
- Use tabular numerals for metrics.
- Use monospace typography for IDs, code, traces, JSON, and technical values.
- Keep headings restrained rather than oversized.
- Use clear visual hierarchy between page titles, section titles, descriptions, and labels.

## Layout

Desktop application:

- Persistent left sidebar
- Compact top navigation
- Breadcrumbs for nested workspaces
- Global search and command palette
- Contextual page actions
- Main content area with consistent max-width and spacing
- Right-side inspectors where appropriate
- Resizable panels for advanced developer screens

Support laptop and tablet layouts. On mobile, collapse the sidebar, preserve core run inspection, and prevent wide tables and canvases from breaking the viewport.

## Component requirements

Create reusable, documented components for:

- Buttons and icon buttons
- Inputs, textareas, selects, comboboxes
- Form labels, help text, and validation
- Cards and metric cards
- Tables and pagination
- Tabs and segmented controls
- Badges and status indicators
- Tooltips and popovers
- Modals and confirmation dialogs
- Dropdown menus
- Toast notifications
- Command palette
- Breadcrumbs
- Empty states
- Loading skeletons
- Error boundaries
- Code and JSON viewers
- Trace rows
- Execution status timelines
- Model selectors
- Provider configuration forms
- Approval cards
- Workflow nodes and connection handles
- Date and time filters

Use consistent radii, spacing, shadows, borders, and interaction states.

## Motion and interaction

Use motion to explain state changes, not as decoration.

Include:

- Subtle sidebar transitions
- Smooth drawers and dialogs
- Node connection feedback
- Run-status transitions
- Animated progress for genuinely active work
- Skeleton loading
- Chart hover details
- Toast entry and exit
- Clear focus and keyboard navigation
- Reduced-motion support

Do not use perpetual animations on every card. Do not delay user actions for decorative effects.

## Application states

Every page must account for:

- Initial loading
- Empty dataset
- Search with no results
- Successful data
- API failure
- Offline or disconnected provider
- Permission denied
- Expired session
- Validation error
- Long-running task
- Partial completion
- Cancelled execution

Never leave a screen blank because a request failed.

---

# 7. GLOBAL APPLICATION NAVIGATION

Implement these primary navigation areas:

1. Overview
2. Agents
3. Workflows
4. Runs & Traces
5. Evaluations
6. Model Lab
7. Knowledge & Memory
8. Tools & Integrations
9. Approvals
10. Analytics
11. Workspace & Administration

Include contextual subnavigation where useful.

## Global header

The global header should provide:

- Workspace switcher
- Environment selector when environments exist
- Breadcrumbs
- Global search
- Command palette
- Notification center
- Help and documentation links
- User profile menu

## Command palette

Support keyboard activation and searchable actions such as:

- Navigate to a page
- Create an agent
- Create a workflow
- Start an execution
- Open a run by ID
- Configure a model
- Open pending approvals
- Search agents, workflows, tools, and traces

Only expose actions the current user is authorized to perform.

---

# 8. MODULE A: EXECUTIVE DASHBOARD

Build a real, data-driven overview screen.

## Metric cards

Display:

- Total runs
- Successful runs
- Failed runs
- Success rate
- Active agents
- Active workflows
- Pending approvals
- Average latency
- P95 latency
- Model token usage
- Estimated model cost
- Policy violations

Metrics must be computed from actual persisted records. Clearly indicate whether the selected range has no data.

## Charts

Provide:

- Run volume over time
- Success and failure trends
- Latency distribution
- Model usage by provider and model
- Estimated spend over time
- Most-used agents
- Top failure categories
- Tool execution distribution

## Activity feed

Each activity entry should include:

- Event type
- Resource or agent name
- Status
- Timestamp
- Relevant run identifier
- Short human-readable summary

## Dashboard interactions

- Date range selection
- Workspace and environment filters
- Drill-down into filtered runs
- Refresh controls
- Loading and empty states
- Live updates through supported event streaming
- Configurable dashboard widgets when feasible

For a first-time workspace, provide an onboarding empty state and a clearly labeled option to load a synthetic demonstration dataset.

Do not generate fake live telemetry to make the dashboard look active.

---

# 9. MODULE B: AGENT STUDIO

Create a complete agent configuration experience.

## Agent creation

Allow users to define:

- Name
- Description
- Avatar or icon
- Intended use
- System instructions
- Model provider and model
- Model parameters
- Available tools
- Knowledge sources
- Memory settings
- Input schema
- Output schema
- Execution limits
- Permission profile
- Version notes

## Model parameters

Support applicable provider settings:

- Temperature
- Maximum output tokens
- Top-p when supported
- Timeout
- Structured output mode
- Streaming preference
- Retry policy
- Fallback model
- Provider-specific capabilities

Validate values according to provider limits. Do not expose unsupported settings as though they work.

## Agent playground

Provide:

- Chat-style request input
- Structured input editor
- Model and agent version selector
- Run and cancel controls
- Streaming output
- Tool execution events
- Final response
- Execution duration
- Token usage and cost when available
- Trace link
- Clear errors and retry options

The playground must use the real backend runtime. A demo mode must be explicitly labeled.

## Agent versioning

- Save immutable published versions.
- Maintain editable drafts.
- Record change summaries.
- Allow duplication.
- Show version history.
- Support rollback to a prior version.
- Record the exact version used by each run.
- Run evaluations against selected versions before promotion.

Never mutate a historical version that is referenced by an existing run.

## Agent templates

Include useful templates:

- CRM Research Assistant
- Structured Data Extractor
- Document Research Assistant
- Customer Support Triage
- Report Generator
- Tool-Calling Assistant
- Evaluation Assistant
- Sales Follow-Up Drafter

Templates should be functional configurations, not merely cards with names.

---

# 10. MODULE C: VISUAL WORKFLOW BUILDER

Build an interactive node-based workflow editor using React Flow.

## Canvas functionality

- Drag and drop nodes
- Connect compatible ports
- Zoom and pan
- Minimap
- Grid or alignment assistance
- Node selection
- Multi-selection
- Copy and paste where supported
- Delete and duplicate nodes
- Undo and redo
- Keyboard shortcuts
- Autosave with visible save status
- Workflow validation
- Version history
- Run workflow
- Debug execution
- Inspect node input and output

## Node types

Implement the following node contracts:

1. Start/Input
2. Agent/LLM
3. Tool
4. Condition
5. Router
6. Parallel branch
7. Merge
8. Transform
9. Human approval
10. Knowledge retrieval
11. Delay or schedule
12. Loop
13. End/Output

Each node must have a typed configuration schema, validated inputs, outputs, and error behavior.

Do not render node types that the execution engine cannot execute. A node can be marked experimental, but its status must be explicit.

## Workflow persistence

Store versioned workflow definitions as validated JSON.

Each definition should contain:

- Workflow ID and version
- Nodes with stable IDs
- Node type and configuration
- Edges
- Input and output schemas
- Workflow metadata
- Execution policies
- Version metadata

Validate:

- Duplicate node IDs
- Missing references
- Invalid connections
- Unsupported node types
- Invalid schemas
- Unreachable nodes where relevant
- Illegal cycles
- Loops without safe bounds
- Missing required inputs
- Unsafe execution configurations

## Execution engine

Create a backend workflow interpreter that:

- Loads an immutable workflow version
- Validates the graph before execution
- Maintains explicit execution state
- Resolves node inputs from defined variables and upstream outputs
- Executes nodes according to graph dependencies
- Handles conditional branches
- Supports bounded parallel execution
- Records node-level run events
- Supports timeouts and cancellation
- Applies retries only to eligible operations
- Persists checkpoints for durable execution when supported
- Pauses for approval
- Resumes from a valid checkpoint
- Produces a structured final output

Never execute arbitrary code from a workflow definition.

## Debugging

Allow users to:

- Run the entire workflow
- Run from a supported node with required inputs
- Inspect node configuration
- Inspect sanitized node inputs and outputs
- See failed-node details
- See elapsed time per node
- Replay a run in an isolated environment when safe

A replay must not automatically repeat external side effects.

---

# 11. MODULE D: AGENT RUNTIME AND TOOL REGISTRY

The runtime is a core platform subsystem.

## Runtime execution lifecycle

Implement a clearly defined lifecycle:

1. Accept request.
2. Authenticate caller.
3. Resolve workspace and resource.
4. Check authorization.
5. Validate request and configuration.
6. Create a persistent run record.
7. Load immutable agent or workflow version.
8. Initialize execution limits and trace context.
9. Invoke the selected model.
10. Validate any proposed tool call.
11. Resolve registered tool.
12. Validate tool arguments.
13. Enforce authorization and risk policies.
14. Pause for approval if required.
15. Execute permitted tool.
16. Persist sanitized result and trace event.
17. Continue within configured limits.
18. Produce final result or controlled failure.
19. Persist terminal status and metrics.
20. Emit completion event.

Every state transition must be validated by the backend.

## Tool registry

Every tool definition should include:

- Stable tool ID
- Name
- Description
- Version
- Input schema
- Output schema
- Risk classification
- Required permissions
- Timeout
- Retry policy
- Idempotency behavior
- Approval requirement
- Execution implementation
- Enabled/disabled status
- Audit metadata

## Initial built-in tools

Implement these against synthetic CRM data:

- `search_customers`
- `search_deals`
- `get_customer_summary`
- `get_deal_details`
- `calculate_metrics`
- `search_knowledge`
- `create_followup_draft`
- `generate_sales_report`
- `mark_deal_contacted`

Classify tools appropriately.

Read-only operations may execute after authorization and validation.

Draft creation can be permitted when it produces an isolated, reversible internal draft.

Actions that change business records must require approval by default unless a narrowly scoped policy explicitly permits the action.

Do not implement external message sending as a side effect of draft creation.

## Tool execution requirements

- Validate arguments with Pydantic or equivalent strict schemas.
- Reject unexpected fields unless the tool contract explicitly allows them.
- Resolve tools only from the server-side registry.
- Enforce workspace and resource permissions.
- Apply bounded timeouts.
- Apply retries only when safe.
- Use idempotency keys for operations that may be repeated.
- Record execution status and sanitized results.
- Normalize exceptions into controlled error categories.
- Enforce concurrency and rate limits.
- Never trust a model-generated tool name or argument.
- Never allow a model to bypass application permissions.

---

# 12. MODULE E: MODEL PROVIDERS AND MODEL LAB

Build a provider abstraction that supports multiple local and cloud model providers.

## Provider interface

Define a common interface for:

- Listing supported models when available
- Declaring capabilities
- Sending model requests
- Handling tool calls
- Handling structured outputs
- Streaming responses when supported
- Returning usage metadata
- Reporting errors
- Applying timeouts and cancellation
- Health checking
- Estimating cost when pricing data is available

Use typed internal models for requests, responses, tool calls, usage, and provider errors.

## Provider configuration

Store provider metadata and configuration securely.

Support:

- Local Ollama endpoint configuration
- Cloud provider selection
- API key entry and server-side storage
- Connection testing
- Model selection
- Capability discovery where available
- Default model selection
- Timeout configuration
- Fallback configuration
- Enable and disable controls

Never return stored secrets to the frontend after saving them. Show only a masked indicator.

Do not assume the local Ollama service is running. Detect connection failures and display a useful diagnostic.

## Model comparison

Allow users to select several models and execute the same benchmark cases.

Track:

- Task completion rate
- Output validity
- Tool-selection accuracy
- Tool argument validity
- Retrieval quality when applicable
- Groundedness when applicable
- Policy violations
- Latency
- P50 and P95 latency when enough observations exist
- Input and output tokens when reported
- Estimated cost
- Cost per successful task
- Provider failures
- Retry rate

Store model, prompt, tool schema, evaluation dataset, and configuration versions for reproducibility.

Do not claim a model is superior based on one sample. Display sample counts and uncertainty where appropriate.

## Smart model router

Support configurable routing policies based on:

- Task category
- Required capabilities
- Latency target
- Budget
- Provider availability
- Evaluation results
- Fallback order

Use explicit routing rules initially. More advanced learned routing can be added later.

A router must never bypass tool permissions, approval requirements, or execution budgets.

---

# 13. MODULE F: RUNS, TRACES AND DEBUGGING

Every agent and workflow execution must create an inspectable trace.

## Run history

Support filtering by:

- Run ID
- Agent
- Workflow
- Version
- Initiating user
- Workspace
- Status
- Model
- Tool
- Error category
- Date range
- Duration
- Estimated cost

Provide pagination and server-side filtering.

## Run details

Display:

- Run ID
- Execution status
- Start and end time
- Duration
- Initiating identity
- Agent or workflow version
- Model configuration
- Input summary
- Final output
- Step count
- Token usage
- Estimated cost
- Approval events
- Error information
- Cancellation information

## Trace hierarchy

Represent nested execution events:

- Workflow run
- Agent run
- Model call
- Tool call
- Retrieval call
- Approval pause
- Retry
- Branch execution
- Final output

## Trace timeline

Provide:

- Ordered events
- Nested spans
- Duration per step
- Status per step
- Sanitized inputs and outputs
- Model and tool metadata
- Retry details
- Error classification
- Links to relevant resource versions

## Replay

A replay must use a safe execution mode.

- Default to dry-run or isolated synthetic resources.
- Never automatically resend messages or repeat irreversible actions.
- Require fresh authorization for external writes.
- Record that a replay occurred.
- Link the replay to the original run.
- Allow the user to compare outputs.

## Live execution updates

Use Server-Sent Events where appropriate.

Persist events before or alongside broadcasting them. Clients must be able to reconnect and recover missed events using a cursor, sequence number, or equivalent mechanism.

Handle disconnects, cancellation, and terminal events explicitly.

---

# 14. MODULE G: EVALUATION AND REGRESSION TESTING

Build an evaluation subsystem for measuring agent quality.

## Evaluation suites

Each suite contains:

- Name and description
- Version
- Test cases
- Evaluation configuration
- Expected outputs or assertions
- Tool expectations where applicable
- Dataset provenance
- Scoring rules

## Evaluation cases

Support:

- Input request
- Context or fixture data
- Expected structured output
- Required facts
- Prohibited outcomes
- Expected tool calls
- Expected policy decisions
- Optional reference answer
- Tags and difficulty
- Deterministic assertions

## Evaluation methods

Implement:

- Exact match for deterministic outputs
- Schema validation
- Required-field checks
- Rule-based correctness checks
- Tool-selection and argument checks
- Groundedness checks for retrieval tasks
- Custom Python evaluators
- Optional model-based judging

Model-based judges must be clearly labeled and should not be the sole authority for security-sensitive assertions.

## Benchmark execution

- Execute the same cases against selected agent versions or models.
- Isolate fixture data.
- Avoid test contamination between runs.
- Record prompt, model, tool, and dataset versions.
- Record latency, usage, result, and error.
- Generate reproducible reports.
- Support regression comparisons.
- Allow configurable pass thresholds.

## Regression gates

Allow users to define release gates such as:

- Minimum task success rate
- Maximum policy violation rate
- Maximum schema failure rate
- Maximum acceptable latency
- Maximum cost per successful task

A release must not be marked successful if the evaluation did not run or required measurements are unavailable.

---

# 15. MODULE H: KNOWLEDGE HUB AND RAG

Implement retrieval-augmented generation as a distinct subsystem.

## Document ingestion

Support common formats:

- PDF
- TXT
- Markdown
- DOCX
- CSV

Use safe parsing libraries and enforce upload size and file-type limits.

Track:

- Source metadata
- File hash
- Uploading user
- Workspace
- Processing status
- Parsing errors
- Chunk count
- Embedding status
- Ingestion version
- Created and updated timestamps

## Chunking and embeddings

Allow configuration of:

- Chunk size
- Chunk overlap
- Embedding provider
- Embedding model
- Batch size
- Metadata extraction
- Re-indexing behavior

Store chunk text, metadata, source references, and embeddings.

Validate embedding dimensions and model compatibility.

## Retrieval

Support:

- Vector similarity search
- Metadata filtering
- Keyword search where implemented
- Hybrid retrieval where implemented
- Configurable top-K
- Optional reranking
- Source-level permissions
- Relevance thresholds
- Citation generation

Show retrieved passages, source documents, scores, and retrieval configuration in the debugging UI.

## RAG safety and quality

- Enforce access control at retrieval time.
- Treat document content as untrusted data.
- Do not interpret retrieved instructions as higher-priority system instructions.
- Keep citations linked to the correct source.
- Provide an explicit no-relevant-source behavior.
- Track retrieval failures.
- Include retrieval evaluation cases.
- Prevent unauthorized cross-workspace document retrieval.

---

# 16. MODULE I: AGENT MEMORY

Separate memory from knowledge retrieval.

## Memory types

Support:

- Session context
- Conversation history
- Explicit user preferences
- Structured entity memory
- Workspace-level shared memory where authorized

## Memory metadata

Each record should include:

- Workspace and applicable owner
- Memory type
- Content or structured payload
- Source or provenance
- Created timestamp
- Updated timestamp
- Optional expiry
- Visibility and access policy
- Status

## Memory behavior

- Allow explicit memory creation and update.
- Provide inspection and deletion controls.
- Apply expiry policies.
- Separate temporary context from persistent memory.
- Prevent automatic promotion of arbitrary user content into privileged instructions.
- Do not treat memory content as trusted system policy.
- Avoid storing secrets unnecessarily.
- Log memory access and changes where appropriate.

---

# 17. MODULE J: APPROVALS AND GOVERNANCE

Build a human-in-the-loop control system.

## Approval queue

Display:

- Pending action
- Requesting agent
- Initiating user
- Tool name
- Target resource
- Exact proposed arguments
- Risk classification
- Expected impact
- Creation time
- Expiry
- Associated run

## Actions

Authorized reviewers can:

- Approve
- Reject
- Request changes
- Inspect supporting context
- View previous decisions
- Open the originating trace

## Approval security

An approval must be bound to:

- Workspace
- Run
- Tool
- Exact canonical argument payload or its secure hash
- Target resource
- Approving identity
- Policy version
- Expiry
- Decision status

When executing the action, the backend must verify that the approved payload still matches the proposed action.

Revalidate current permissions and policy immediately before execution.

Reject expired, duplicate, revoked, or mismatched approvals.

## Governance controls

Implement:

- Tool allowlists
- Agent execution limits
- Maximum step count
- Maximum wall-clock duration
- Token and spend budgets
- Per-tool rate limits
- Workspace quotas
- Emergency execution pause
- Agent disable switch
- Audit log
- Policy violation alerts

Policy checks must occur on the server. Prompt instructions alone are not a security boundary.

---

# 18. MODULE K: TOOLS AND INTEGRATIONS

Create a connector architecture with consistent configuration and execution contracts.

## Integration directory

Each integration should display:

- Name
- Description
- Category
- Supported capabilities
- Connection status
- Required permissions
- Configuration requirements
- Health status
- Documentation
- Enable or disable control

## First integration set

Prioritize functional built-in integrations:

- Synthetic CRM
- Knowledge search
- Calculator and safe data transformations
- Report generation
- Local Ollama
- One supported cloud LLM provider

Then add external integrations as separate, testable adapters:

- GitHub
- Slack
- Email
- Calendar
- Generic REST API
- Additional CRM providers

Do not represent an integration as connected until its credentials and health checks have succeeded.

## Connector security

- Use least-privilege credentials.
- Store credentials server-side.
- Restrict outbound network access where practical.
- Validate URLs and block unsafe internal-network access in generic HTTP connectors.
- Prevent SSRF and redirect-based bypasses.
- Apply request timeouts and response size limits.
- Redact credentials from logs and traces.
- Enforce workspace ownership.
- Provide revocation and connection testing.

---

# 19. MODULE L: SCHEDULING AND AUTOMATION

Support:

- Manual triggers
- Scheduled triggers
- Signed webhook triggers
- API-triggered runs
- Event-driven execution
- Retry policies
- Failure notifications
- Dead-letter handling
- Pause and resume
- Schedule enable/disable
- Timezone-aware schedules
- Execution concurrency limits
- Idempotency
- Run history
- Safe backfill and replay

Long-running work must not depend on a single HTTP request staying open.

Use durable job processing where necessary. Persist execution state and recover correctly after worker restarts.

Validate webhook signatures, reject unauthorized events, and apply replay protection where appropriate.

---

# 20. MODULE M: MULTI-AGENT ORCHESTRATION

Implement this after single-agent and workflow execution are reliable.

Support:

- Coordinator agent
- Specialist agents
- Explicit task contracts
- Structured handoffs
- Controlled shared state
- Parallel independent tasks
- Result aggregation
- Failure propagation
- Per-agent tool permissions
- Maximum delegation depth
- Maximum steps
- Maximum total duration
- Maximum total spend
- Cycle detection
- Hierarchical traces

Do not allow agents to recursively spawn unlimited agents.

Each delegated task must have a clear objective, bounded inputs, defined output schema, and explicit permissions.

A specialist must not inherit unrestricted permissions simply because the coordinator possesses them.

---

# 21. MODULE N: WORKSPACES, USERS AND ACCESS CONTROL

Implement secure identity and authorization.

## Roles

Provide an initial role model:

- Owner
- Administrator
- Developer
- Operator
- Reviewer
- Viewer

Define explicit permissions for:

- Workspace administration
- Member management
- Agent creation and publishing
- Workflow editing
- Execution
- Approval
- Provider configuration
- Secret management
- Evaluation
- Audit access

## Workspace isolation

Every workspace-owned record must be scoped appropriately.

- Authenticate all protected requests.
- Resolve workspace membership on the server.
- Enforce resource-level authorization.
- Do not trust workspace IDs supplied by clients without authorization checks.
- Add tenant-scoped queries and database constraints where appropriate.
- Test cross-workspace access attempts.
- Restrict background jobs to their intended tenant context.
- Prevent information leakage through errors, traces, search, or exports.

## Authentication

Use secure sessions or a suitable managed identity provider.

For cookie-based sessions:

- Use appropriate Secure, HttpOnly, and SameSite settings.
- Implement CSRF protection where applicable.
- Rotate session identifiers appropriately.
- Enforce session expiration.
- Rate-limit authentication endpoints.

Do not invent an authentication implementation that merely trusts a user ID from request headers.

---

# 22. MODULE O: ANALYTICS AND USAGE

Build analytics based on persisted execution data.

Include:

- Runs by time range
- Success and failure trends
- Latency percentiles
- Model usage
- Token consumption
- Estimated spend
- Cost per successful task
- Agent usage rankings
- Tool execution statistics
- Error categories
- Approval turnaround time
- Evaluation score trends
- Provider availability
- Workspace usage limits

Define how every metric is calculated.

Distinguish reported provider costs from estimated costs. If pricing is unavailable, display unavailable or estimated rather than inventing a precise number.

Avoid counting duplicate events or retried operations incorrectly.

---

# 23. MODULE P: DEVELOPER PLATFORM

Provide:

- REST API
- Versioned API routes
- OpenAPI documentation
- API key management
- Scoped API keys
- Expiration and revocation
- Webhook configuration
- Usage limits
- Request IDs
- Structured error responses
- Developer documentation
- Configuration export and import
- CLI as a later milestone
- Python and TypeScript SDKs as later milestones

Never return secret values after creation. Display them once where appropriate and store only a secure representation if plaintext is not needed again.

---

# 24. DATABASE DESIGN

Use PostgreSQL with UUID primary keys where appropriate, UTC timestamps, migrations, explicit relationships, and carefully chosen indexes.

Every tenant-owned entity must have an appropriate workspace boundary.

Create these entities or their justified equivalents.

## Identity and workspace

### `users`

- id
- email
- display_name
- identity_provider_id
- status
- created_at
- updated_at

### `workspaces`

- id
- name
- slug
- owner_id
- settings_json
- created_at
- updated_at

### `workspace_members`

- id
- workspace_id
- user_id
- role
- status
- created_at

Enforce uniqueness for workspace/user membership.

## Agents

### `agents`

- id
- workspace_id
- name
- description
- status
- current_published_version_id
- created_by
- created_at
- updated_at

### `agent_versions`

- id
- workspace_id
- agent_id
- version_number
- configuration_json
- configuration_hash
- change_summary
- created_by
- created_at

Published versions must be immutable.

## Models and providers

### `model_providers`

- id
- workspace_id
- provider_type
- display_name
- configuration_metadata
- secret_reference
- status
- last_health_check_at
- created_at
- updated_at

### `model_configs`

- id
- workspace_id
- provider_id
- model_name
- capability_metadata
- default_parameters_json
- enabled
- created_at
- updated_at

Do not store plaintext credentials in ordinary JSON fields.

## Tools

### `tool_definitions`

- id
- workspace_id, nullable only for explicitly global built-ins
- name
- version
- description
- input_schema_json
- output_schema_json
- risk_level
- permission_metadata
- requires_approval
- enabled
- created_at
- updated_at

### `agent_tools`

- id
- workspace_id
- agent_version_id
- tool_definition_id
- configuration_json

## Workflows

### `workflow_definitions`

- id
- workspace_id
- name
- description
- status
- current_published_version_id
- created_by
- created_at
- updated_at

### `workflow_versions`

- id
- workspace_id
- workflow_id
- version_number
- graph_json
- graph_hash
- change_summary
- created_by
- created_at

## Execution

### `agent_runs`

- id
- workspace_id
- agent_id
- agent_version_id
- initiated_by
- status
- input_json, subject to redaction policy
- output_json, subject to redaction policy
- model_config_id
- started_at
- completed_at
- duration_ms
- token_usage_json
- estimated_cost
- error_code
- error_summary
- replay_of_run_id
- created_at

### `workflow_runs`

- id
- workspace_id
- workflow_id
- workflow_version_id
- initiated_by
- status
- input_json
- output_json
- started_at
- completed_at
- duration_ms
- error_code
- error_summary
- created_at

### `run_events`

- id
- workspace_id
- run_id
- sequence_number
- event_type
- event_status
- sanitized_payload_json
- occurred_at

Use stable ordering and indexes for run/event queries.

### `trace_spans`

- id
- workspace_id
- run_id
- parent_span_id
- span_type
- name
- status
- started_at
- ended_at
- duration_ms
- sanitized_attributes_json

## Approvals and audit

### `approval_requests`

- id
- workspace_id
- run_id
- tool_definition_id
- canonical_arguments_hash
- sanitized_arguments_json
- requested_by
- reviewed_by
- decision
- policy_version
- expires_at
- created_at
- decided_at

### `audit_events`

- id
- workspace_id
- actor_id
- action
- resource_type
- resource_id
- outcome
- sanitized_metadata_json
- created_at

Audit events should be append-only through normal application operations.

## Evaluation

### `evaluation_suites`

- id
- workspace_id
- name
- description
- version
- configuration_json
- created_by
- created_at

### `evaluation_cases`

- id
- workspace_id
- suite_id
- case_key
- input_json
- expected_json
- assertions_json
- tags_json
- created_at

### `evaluation_results`

- id
- workspace_id
- suite_id
- evaluation_case_id
- agent_version_id
- model_config_id
- status
- score_json
- duration_ms
- token_usage_json
- estimated_cost
- error_summary
- created_at

## Knowledge and memory

### `knowledge_sources`

- id
- workspace_id
- name
- source_type
- configuration_json
- status
- created_at
- updated_at

### `documents`

- id
- workspace_id
- knowledge_source_id
- title
- file_hash
- storage_reference
- mime_type
- processing_status
- ingestion_version
- created_at
- updated_at

### `document_chunks`

- id
- workspace_id
- document_id
- chunk_index
- content
- metadata_json
- embedding
- created_at

### `memory_records`

- id
- workspace_id
- owner_user_id, nullable according to memory scope
- memory_type
- content_json
- provenance_json
- expires_at
- created_at
- updated_at

## Automation and integration

### `schedules`

- id
- workspace_id
- workflow_id
- workflow_version_id
- schedule_expression
- timezone
- enabled
- next_run_at
- created_at
- updated_at

### `webhook_endpoints`

- id
- workspace_id
- workflow_id
- secret_reference
- enabled
- created_at

### `background_jobs`

- id
- workspace_id
- job_type
- resource_id
- status
- attempt_count
- scheduled_at
- started_at
- completed_at
- error_summary
- created_at

Add appropriate foreign keys, uniqueness constraints, indexes, and delete behavior.

Use migrations for every schema change. Never rely on production schema auto-creation at application startup.

---

# 25. API DESIGN

Use a consistent versioned prefix:

`/api/v1`

Implement REST endpoints with typed request and response schemas.

## System and authentication

- `GET /health`
- `GET /ready`
- `GET /api/v1/me`
- `GET /api/v1/workspaces`
- `POST /api/v1/workspaces`
- `GET /api/v1/workspaces/{workspace_id}`
- `PATCH /api/v1/workspaces/{workspace_id}`
- `GET /api/v1/workspaces/{workspace_id}/members`
- `POST /api/v1/workspaces/{workspace_id}/members`

Identity-provider-specific authentication routes should follow the selected authentication strategy.

## Dashboard

- `GET /api/v1/dashboard/summary`
- `GET /api/v1/dashboard/activity`
- `GET /api/v1/dashboard/usage`
- `GET /api/v1/dashboard/health`

Support date and resource filters.

## Agents

- `GET /api/v1/agents`
- `POST /api/v1/agents`
- `GET /api/v1/agents/{agent_id}`
- `PATCH /api/v1/agents/{agent_id}`
- `DELETE /api/v1/agents/{agent_id}`
- `GET /api/v1/agents/{agent_id}/versions`
- `POST /api/v1/agents/{agent_id}/versions`
- `POST /api/v1/agents/{agent_id}/publish`
- `POST /api/v1/agents/{agent_id}/rollback`
- `POST /api/v1/agents/{agent_id}/test`

## Models

- `GET /api/v1/models/providers`
- `POST /api/v1/models/providers`
- `GET /api/v1/models/providers/{provider_id}`
- `PATCH /api/v1/models/providers/{provider_id}`
- `POST /api/v1/models/providers/{provider_id}/test`
- `GET /api/v1/models`
- `POST /api/v1/models/compare`

Never expose secret values in responses.

## Tools

- `GET /api/v1/tools`
- `POST /api/v1/tools`
- `GET /api/v1/tools/{tool_id}`
- `PATCH /api/v1/tools/{tool_id}`
- `POST /api/v1/tools/{tool_id}/test`

Tool creation must not permit arbitrary code injection into the runtime.

## Workflows

- `GET /api/v1/workflows`
- `POST /api/v1/workflows`
- `GET /api/v1/workflows/{workflow_id}`
- `PATCH /api/v1/workflows/{workflow_id}`
- `GET /api/v1/workflows/{workflow_id}/versions`
- `POST /api/v1/workflows/{workflow_id}/validate`
- `POST /api/v1/workflows/{workflow_id}/publish`
- `POST /api/v1/workflows/{workflow_id}/run`

## Runs and traces

- `POST /api/v1/runs`
- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/events`
- `GET /api/v1/runs/{run_id}/trace`
- `POST /api/v1/runs/{run_id}/cancel`
- `POST /api/v1/runs/{run_id}/replay`

The replay endpoint must enforce safe replay rules and fresh authorization.

## Approvals

- `GET /api/v1/approvals`
- `GET /api/v1/approvals/{approval_id}`
- `POST /api/v1/approvals/{approval_id}/decision`

## Evaluations

- `GET /api/v1/evaluations/suites`
- `POST /api/v1/evaluations/suites`
- `GET /api/v1/evaluations/suites/{suite_id}`
- `POST /api/v1/evaluations/suites/{suite_id}/run`
- `GET /api/v1/evaluations/results`
- `GET /api/v1/evaluations/results/{result_id}`

## Knowledge

- `GET /api/v1/knowledge/sources`
- `POST /api/v1/knowledge/sources`
- `GET /api/v1/knowledge/documents`
- `POST /api/v1/knowledge/documents`
- `GET /api/v1/knowledge/documents/{document_id}`
- `POST /api/v1/knowledge/documents/{document_id}/reindex`
- `POST /api/v1/knowledge/search`

## Automation

- `GET /api/v1/schedules`
- `POST /api/v1/schedules`
- `PATCH /api/v1/schedules/{schedule_id}`
- `POST /api/v1/schedules/{schedule_id}/pause`
- `POST /api/v1/schedules/{schedule_id}/resume`

## API conventions

- Validate all request payloads.
- Return predictable error schemas.
- Use correct HTTP status codes.
- Include request IDs.
- Implement pagination for list endpoints.
- Apply authorization to every protected resource.
- Avoid returning internal stack traces.
- Use idempotency keys where duplicate requests could create side effects.
- Add rate limits to expensive or sensitive endpoints.
- Document each endpoint and its permissions.
- Keep business logic out of route handlers.

---

# 26. SECURITY REQUIREMENTS

Security is a foundational requirement, not a final polish task.

## Prompt injection

- Treat user input, retrieved documents, tool results, web content, and external data as untrusted.
- Never rely on prompt instructions as the only protection.
- Enforce tool authorization outside the model.
- Separate trusted policy configuration from untrusted content.
- Limit the data available to each agent.
- Require confirmation for sensitive actions.
- Test indirect prompt injection through retrieved documents and tool results.

## Secret management

- Load credentials from environment variables or a dedicated secret manager.
- Never commit secrets.
- Never expose secrets to browser code.
- Redact secrets from logs, traces, exceptions, and model prompts.
- Rotate and revoke credentials when necessary.
- Keep `.env.example` free of real credentials.

## Database and tenant security

- Enforce tenant boundaries in backend services and queries.
- Add database constraints where appropriate.
- Consider PostgreSQL row-level security as an additional layer.
- Use parameterized queries.
- Prevent cross-tenant access through direct IDs, search, exports, background jobs, and trace links.
- Test unauthorized access attempts.

## Execution security

- No arbitrary model-generated SQL.
- No unrestricted shell execution.
- No unrestricted Python execution.
- No unvalidated dynamic imports.
- No unlimited loops or recursive agent creation.
- No unlimited retries.
- No unbounded execution duration.
- No unbounded token or spend consumption.
- No execution of unregistered tools.

## SSRF and external requests

For generic HTTP connectors:

- Restrict allowed protocols.
- Block loopback, link-local, private, and sensitive internal destinations unless explicitly authorized by a tightly controlled deployment policy.
- Validate resolved IP addresses.
- Revalidate redirect targets.
- Prevent DNS rebinding bypasses.
- Apply response size and timeout limits.
- Avoid exposing internal service responses.

## Upload security

- Enforce file size limits.
- Validate file type and content.
- Avoid trusting file extensions alone.
- Use safe parsers.
- Prevent path traversal.
- Store uploaded files outside executable application directories.
- Restrict document retrieval by workspace permissions.

## Audit and incident response

Record security-relevant events, including:

- Authentication failures
- Permission denials
- Provider configuration changes
- Secret rotation events where available
- Tool execution attempts
- Approval decisions
- Policy violations
- Agent publication
- Workspace role changes
- Emergency pause activation

Do not log sensitive payloads unnecessarily.

---

# 27. ERROR HANDLING AND RELIABILITY

Define a consistent error taxonomy.

Examples:

- `VALIDATION_ERROR`
- `AUTHENTICATION_REQUIRED`
- `PERMISSION_DENIED`
- `RESOURCE_NOT_FOUND`
- `PROVIDER_UNAVAILABLE`
- `PROVIDER_TIMEOUT`
- `RATE_LIMITED`
- `INVALID_TOOL_ARGUMENTS`
- `TOOL_EXECUTION_FAILED`
- `APPROVAL_REQUIRED`
- `APPROVAL_EXPIRED`
- `POLICY_VIOLATION`
- `EXECUTION_LIMIT_EXCEEDED`
- `RUN_CANCELLED`
- `WORKFLOW_VALIDATION_FAILED`
- `INTERNAL_ERROR`

For every error, define:

- Safe user-facing message
- Internal diagnostic details
- Whether retry is permitted
- Whether the failure is terminal
- Whether the event should trigger an alert

Use exponential backoff with jitter for eligible transient failures.

Never retry a non-idempotent external action automatically without a safe idempotency mechanism.

Persist terminal run states. Ensure cancellation and worker failures do not leave runs permanently marked as running without a recovery policy.

---

# 28. TESTING STRATEGY

Build tests throughout implementation, not after the application is finished.

## Unit tests

Cover:

- Schema validation
- Agent configuration validation
- Tool argument validation
- Permission evaluation
- Risk classification
- Approval matching
- Workflow graph validation
- Routing policy
- Budget enforcement
- Error normalization
- Evaluation scoring
- Cost estimation

## Integration tests

Cover:

- Database persistence
- Database migrations
- API authorization
- Agent execution
- Tool execution
- Approval and resume flow
- Model provider adapters using mocks or controlled test servers
- Event streaming
- Workflow execution
- Knowledge ingestion and retrieval
- Worker retries and recovery

## Security tests

Cover:

- Cross-workspace data access
- Unauthorized tool invocation
- Forged approval requests
- Approval payload tampering
- Expired approvals
- Secret leakage
- Prompt injection
- Unsafe tool arguments
- SSRF protections
- File upload validation
- Rate limiting
- Idempotency
- Privilege escalation

## Evaluation tests

Create at least 30 meaningful synthetic benchmark cases over time, including:

- Straightforward success cases
- Missing-data cases
- Ambiguous requests
- Invalid arguments
- Tool failures
- Provider timeouts
- Prompt injection
- Permission denials
- Approval-required actions
- Retrieval failures
- Structured-output errors
- Budget exhaustion

Use deterministic assertions wherever possible.

## Frontend tests

Use component tests and Playwright end-to-end tests for critical journeys:

1. Create a workspace.
2. Configure a model.
3. Create an agent.
4. Run the agent.
5. Inspect its trace.
6. Create a workflow.
7. Validate and run the workflow.
8. Approve a proposed action.
9. Reject an unauthorized action.
10. Run an evaluation suite.
11. Compare models.
12. Recover from a failed provider request.

Use test fixtures and mocked providers where appropriate. Never make ordinary CI depend on a paid live provider.

---

# 29. SEED DATA AND DEMONSTRATION MODE

Create a clearly labeled synthetic demonstration workspace.

Include:

- Synthetic customers
- Synthetic companies
- Synthetic deals
- Contact history
- Follow-up statuses
- Example documents
- Example agents
- Example workflows
- Example evaluation suites

Use fictional names and contact information.

Create an explicit seed command or setup procedure. Do not silently inject demo records into real user workspaces.

Demonstration mode may use simulated model results only when the interface clearly states that simulation is active.

Never mix fabricated execution records into real analytics without labeling them.

---

# 30. REQUIRED DEMONSTRATION AGENT

Build a complete example called **Sales Operations Assistant**.

## Scenario

A user requests:

"Find deals worth more than ₹50,000 that have not been contacted in the last 14 days. Research the customers, prepare personalized follow-up drafts, and show me the proposed actions before anything is sent."

## Required behavior

1. Parse the request into structured criteria.
2. Search authorized synthetic CRM records.
3. Apply date and deal-value filters correctly.
4. Retrieve relevant customer information.
5. Prepare personalized drafts grounded in available data.
6. Avoid inventing customer facts.
7. Validate every tool argument.
8. Record all model and tool activity.
9. Present proposed changes for review.
10. Require approval before protected write actions.
11. Execute only authorized and approved actions.
12. Report successful, failed, and skipped actions separately.
13. Produce a trace showing every step.
14. Allow the user to inspect duration, usage, and estimated cost where available.

If customer information is unavailable, return a clear message:

"The requested information is not available in the provided data."

Do not fabricate data to make the agent appear successful.

## Demo requirements

The demo must show:

- Agent configuration
- Tool selection
- Actual runtime execution
- Tool results
- Approval request
- Approval decision
- Execution trace
- Final result
- Evaluation results
- Model comparison

This is the primary end-to-end proof that the product works.

---

# 31. DOCUMENTATION REQUIREMENTS

Maintain these documents as the implementation evolves.

## `README.md`

Include:

- Product overview
- Feature list
- Screenshots when available
- Architecture summary
- Requirements
- Installation
- Environment setup
- Database setup
- Seed data setup
- Starting the frontend and backend
- Running tests
- Troubleshooting
- Deployment overview

## `AGENTS.md`

Include:

- Repository structure
- Coding conventions
- Architecture boundaries
- Test commands
- Security rules
- Dependency management
- Definition of done
- Instructions for future coding agents

## `docs/architecture.md`

Document:

- Major components
- Data flow
- Execution lifecycle
- Provider abstraction
- Workflow execution
- Persistence
- Event streaming
- Background processing
- Security boundaries

## `docs/database-schema.md`

Document:

- Entities
- Relationships
- Tenant boundaries
- Indexes
- Migrations
- Retention rules

## `docs/api-reference.md`

Document routes, schemas, permissions, error codes, pagination, and examples.

## `docs/security.md`

Document threat model, authorization, tool safety, secret handling, approval semantics, and operational controls.

## `docs/design-system.md`

Document colors, typography, spacing, components, layouts, motion, accessibility, and responsive behavior.

## `docs/roadmap.md`

Track features as:

- Planned
- In progress
- Implemented
- Tested
- Blocked

Do not mark a feature complete merely because its UI exists.

---

# 32. IMPLEMENTATION PLAN

Work in dependency-aware phases.

## Phase 0: Repository inspection and planning

- Inspect repository and existing code.
- Identify current environment and tooling.
- Verify dependencies and runtime versions.
- Document architecture decisions.
- Create or update `AGENTS.md`.
- Create a prioritized implementation checklist.
- Identify risks and external credentials required.

Deliverable: a practical implementation plan grounded in the actual repository.

## Phase 1: Project foundation

- Establish frontend and backend structure.
- Configure linting and formatting.
- Configure environment settings.
- Set up database connection and migrations.
- Add health and readiness endpoints.
- Implement authentication and workspace boundaries.
- Establish the design system and application shell.
- Add CI checks.

Deliverable: the application starts reliably and has a secure foundational structure.

## Phase 2: Agents and model providers

- Implement provider interfaces.
- Integrate Ollama.
- Add one cloud provider adapter.
- Implement provider health checks.
- Build agent configuration and versioning.
- Implement the tool registry.
- Add the synthetic CRM dataset.
- Build agent execution and persistence.

Deliverable: a real agent can use a registered tool and return a persisted result.

## Phase 3: Runtime safety and observability

- Implement permissions and risk policies.
- Implement approvals.
- Add step and time limits.
- Add retries and cancellation.
- Persist trace events.
- Build run history and trace details.
- Add safe error handling.
- Test tenant isolation and protected actions.

Deliverable: executions are inspectable, bounded, and controlled.

## Phase 4: Workflow builder

- Implement the visual canvas.
- Define the versioned workflow schema.
- Implement validation.
- Implement the backend workflow interpreter.
- Add agent, tool, condition, transform, and approval nodes.
- Add execution progress and node-level traces.
- Add save, publish, and version management.
- Test cancellation, branching, and failure behavior.

Deliverable: users can build and execute a real multi-step workflow.

## Phase 5: Dashboard and Model Lab

- Connect dashboard metrics to persisted data.
- Implement model comparison.
- Implement cost and latency reporting.
- Add provider health indicators.
- Add execution filtering and drill-down.
- Implement fallback and routing policies.

Deliverable: users can understand actual platform behavior and compare model performance.

## Phase 6: Evaluations and knowledge

- Implement evaluation suites and cases.
- Implement deterministic evaluators.
- Add regression reports.
- Add document ingestion.
- Add embeddings and vector retrieval.
- Add citations and retrieval debugging.
- Add evaluation datasets for groundedness and injection resistance.

Deliverable: users can measure agent quality and build grounded knowledge workflows.

## Phase 7: Automation and advanced features

- Add durable background execution.
- Add scheduling and webhook triggers.
- Add notifications.
- Add memory management.
- Add advanced analytics.
- Add multi-agent orchestration after the preceding features are reliable.

Deliverable: a broader automation platform built on established foundations.

## Phase 8: Release hardening

- Run full test suites.
- Fix security and reliability defects.
- Verify clean setup from documentation.
- Verify database migration and backup procedures.
- Check frontend responsiveness and accessibility.
- Remove unused code and debug artifacts.
- Verify all displayed metrics.
- Prepare deployment configuration.
- Document known limitations.
- Produce a release checklist.

Deliverable: a reproducible, testable release candidate.

Do not claim every phase is complete simply because the roadmap has been generated.

---

# 33. DEFINITION OF DONE

A feature is complete only when all relevant conditions are satisfied.

- Its UI is implemented.
- Its backend behavior is implemented.
- Its data persistence works.
- Its authorization rules are enforced.
- Its validation and error states are handled.
- Its loading, empty, and success states are designed.
- Its tests are written and run.
- Its documentation is updated.
- It does not expose secrets or cross-tenant data.
- It works with the actual integration or clearly labeled simulation mode.
- It does not silently fabricate success.

## Release acceptance checklist

The first complete release must demonstrate all of the following:

1. A user can create a workspace.
2. The user can configure a local or cloud model provider.
3. The user can create, save, and version an agent.
4. The agent can execute registered tools against synthetic CRM data.
5. Runs and trace events persist in PostgreSQL.
6. The dashboard reports actual persisted execution metrics.
7. Tool arguments are validated server-side.
8. Unauthorized actions are rejected.
9. Sensitive actions require a valid approval.
10. Modified or expired approval payloads cannot be executed.
11. The workflow canvas creates valid persisted workflow definitions.
12. The workflow engine executes supported node types.
13. Failed runs display actionable diagnostic information.
14. Cancellation and execution limits work.
15. Model comparisons use consistent test cases.
16. Evaluation results are persisted and reproducible.
17. The UI handles missing providers and empty data gracefully.
18. Cross-workspace access tests pass.
19. The application can be started using documented setup instructions.
20. Tests and build checks have been executed and their results reported honestly.

---

# 34. PERFORMANCE, ACCESSIBILITY AND OPERATIONS

## Performance

- Paginate large datasets.
- Add indexes based on actual query patterns.
- Avoid unnecessary frontend re-renders.
- Lazy-load heavy workflow and trace views where appropriate.
- Use bounded concurrency for parallel execution.
- Enforce upload and request limits.
- Avoid holding database transactions open during lengthy model calls.
- Keep model calls outside long-lived database transactions.
- Cache only where correctness and authorization remain clear.

## Accessibility

- Support keyboard navigation.
- Provide visible focus indicators.
- Use semantic controls and labels.
- Ensure accessible contrast.
- Provide accessible status text.
- Do not communicate status through color alone.
- Respect reduced-motion preferences.
- Make dialogs and menus accessible.
- Give charts textual summaries or accessible data alternatives.

## Operations

- Separate liveness from readiness.
- Report database and required dependency health.
- Avoid exposing secrets or infrastructure details through public health endpoints.
- Use structured logs with request and run IDs.
- Monitor failed jobs and stuck executions.
- Document migrations and recovery procedures.
- Establish data retention and backup policies.
- Ensure graceful shutdown of workers.
- Record dependency versions and application release information.

---

# 35. NON-GOALS AND ANTI-PATTERNS

Do not:

- Build a generic chatbot and call it an agent platform.
- Use static charts as the permanent analytics implementation.
- Add buttons that do nothing.
- Store all application state in browser memory.
- Store API keys in frontend code.
- Execute arbitrary model-generated code.
- Trust the model to enforce permissions.
- Treat approval as a simple boolean detached from the exact action.
- Build multi-agent orchestration before reliable single-agent execution.
- Add a vector database without a defined retrieval use case.
- Add distributed infrastructure without an architectural reason.
- Retry every failure indiscriminately.
- Re-run external side effects during replay.
- Fabricate token counts, costs, ratings, or success rates.
- Claim provider support without a working adapter.
- Create migrations that destroy existing user data unnecessarily.
- Suppress errors to make the demo appear smooth.
- Mark unimplemented features as complete.
- Put sensitive information into logs or evaluation datasets.
- Sacrifice accessibility for visual effects.

---

# 36. FINAL INSTRUCTIONS TO THE CODING AGENT

Begin by inspecting the actual repository.

Then:

1. Summarize what already exists.
2. Identify gaps against this specification.
3. Create or update the implementation checklist.
4. Establish the architecture and data model.
5. Identify environmental prerequisites.
6. Implement the first complete vertical slice.
7. Run its tests and verify the actual behavior.
8. Continue phase by phase.
9. Update documentation as the implementation changes.
10. Keep the project runnable throughout the process.

For each milestone, report:

- Features implemented
- Important files created or changed
- Architectural decisions
- Database changes
- Tests executed and their actual outcomes
- Commands needed to run the application
- Environment variables or external services required
- Known limitations
- Remaining tasks

When a feature depends on an unavailable external provider, implement a clean provider interface and a useful setup experience. Do not fabricate successful external behavior.

When a feature is too large for one implementation pass, split it into smaller complete units and continue. Do not stop after generating a plan unless a genuine blocker requires user input.

When existing code conflicts with this specification, inspect the impact before modifying it. Preserve valuable working behavior and document significant changes.

Keep all UI, API, database, runtime, evaluation, and security layers consistent with one another.

The final result should be a coherent, polished AI agent engineering platform with real execution, persistent traces, useful evaluations, secure tool access, reliable workflows, and a premium interface.

**The objective is not to maximize the number of screens. The objective is to maximize the number of genuinely working capabilities while maintaining a consistent product experience.**

Build AgentOps as a platform that an engineer could understand, test, extend, demonstrate, and responsibly deploy.
