# Overnight Autonomous Implementation — SWIFT MT/MX Financial Messaging Platform

You are acting as:

- Principal BFS / Capital Markets Solution Architect
- SWIFT MT / ISO 15022 Domain Engineer
- ISO 20022 / MX Engineer
- Senior Python/FastAPI Engineer
- Senior Next.js/TypeScript Engineer
- QA Automation Architect
- API Architect
- Security Engineer
- UX Engineer focused on manual testers
- Production-readiness reviewer

You are working on the existing AI-assisted financial messaging platform.

Your goal is to audit the entire repository, identify what is incomplete or unnecessarily complicated, create a clear implementation plan, self-review that plan, and then autonomously implement the highest-value pending capabilities overnight.

# CRITICAL AUTONOMOUS EXECUTION RULE

Do not ask me questions.

Do not wait for approval.

Do not stop after planning.

Do not ask me to choose between implementation approaches.

Do not ask me to manually test intermediate stages.

Make sensible engineering decisions yourself based on:

1. Existing repository architecture
2. Existing working functionality
3. Existing tests
4. Existing documentation
5. Official/authoritative standards artifacts available to the project
6. Security best practices
7. Simplicity of the final user experience

You are authorised to:

- Inspect the full repository
- Refactor code where necessary
- Create files
- Modify files
- Add compatible dependencies
- Create non-destructive migrations
- Improve APIs
- Improve UI
- Add tests
- Run tests
- Run Docker
- Run migrations
- Use configured LLM access
- Fix defects discovered during implementation
- Make architecture decisions

Do not destroy unrelated existing work.

Do not rewrite stable working functionality unnecessarily.

If a requirement cannot be completed because authoritative SWIFT/client documentation is missing:

- Do not fabricate a standard.
- Implement the extensible framework.
- Mark the capability clearly as unsupported/partial.
- Document the blocker.
- Continue implementing everything else.

---

# 1. FIRST — AUDIT BEFORE IMPLEMENTING

Before modifying application code, perform a complete repository audit.

Inspect:

- Existing MT implementation
- Existing MX implementation, if any
- Current message catalogue
- Tag Intelligence
- Element Intelligence
- Dynamic forms
- Message composers
- Parsers
- Validators
- Client profiles
- ISO 15022 specifications
- ISO 20022 XSD/specification handling
- OpenRouter/LLM abstraction
- AI cache
- Token/cost telemetry
- Excel import/export
- REST APIs
- Authentication
- RBAC
- Tenant model
- Encryption
- Maker-checker flow
- Downloads
- FIN envelope generation
- MX XML generation
- Samples
- Reports
- Docker
- Database migrations
- Tests
- Frontend navigation
- Existing UX complexity
- All TODO/FIXME/placeholder/demo-only code
- Existing implementation reports

Also run the application before implementation and inspect the current UX.

Identify:

- Broken flows
- Duplicate screens
- Confusing screens
- Demo-only controls
- Hard-coded sample data
- Fields that users cannot edit
- Message types that cannot actually generate a usable message
- APIs that cannot be consumed easily by automation frameworks
- Excel flows that are incomplete
- Incorrect MT/MX output structures
- Missing validation
- Missing examples
- Missing downloadable output
- Missing round-trip parsing
- Excessive clicks
- Features that require unnecessary LLM calls

---

# 2. CREATE A PLAN

Before implementation create:

`OVERNIGHT_PLATFORM_AUDIT_AND_IMPLEMENTATION_PLAN.md`

Include:

1. Current repository status
2. Current architecture
3. What is working
4. What is broken
5. What is partially implemented
6. What is demo-only
7. MT coverage
8. MX coverage
9. Excel/API coverage
10. UI/UX problems
11. Security gaps
12. Validation gaps
13. Download/output gaps
14. Test gaps
15. Recommended simplified target architecture
16. Exact implementation priorities
17. Files expected to change
18. Database changes
19. API changes
20. UI changes
21. Risks
22. Acceptance criteria

Then perform a self-review:

- Is the plan too ambitious?
- Does anything duplicate working functionality?
- Can any architecture be simplified?
- Does every proposed feature add measurable user value?
- Can a manual tester understand the resulting UI?
- Can an automation tester consume the same functionality by API?
- Are MT and MX being treated correctly and separately?

Correct the plan yourself.

Then continue directly into implementation.

---

# 3. PRIMARY PRODUCT GOAL

The application must become extremely simple to understand.

A new manual tester should be able to open the application and understand within seconds:

> Select message → provide business/tag data → validate → generate → download/use.

An automation tester should understand:

> Send structured/tag-level data → API validates → API returns complete financial message.

Do not make the platform look like a complicated SWIFT administration system.

The platform should feel like a simple:

# Financial Message Studio

The primary navigation should be minimal.

Prefer approximately:

- Create Message
- Bulk / Excel
- Message Intelligence
- Validate Message
- API / Automation
- Recent Messages

Advanced functionality can exist inside relevant screens instead of creating dozens of navigation items.

---

# 4. SIMPLE MANUAL-TESTER UX

This is extremely important.

Design for manual testers who may have little SWIFT knowledge.

## Create Message screen

Use a simple flow:

### Step 1 — Select format

```text
MT
MX / ISO 20022
```

### Step 2 — Select business area

Examples:

```text
Securities Settlement
Payments
Corporate Actions
Penalties
Investigations
```

Only show implemented business areas.

### Step 3 — Select message

Examples:

MT:

```text
MT541 — Receive Against Payment
MT543 — Deliver Against Payment
MT548 — Settlement Status
MT537 — Pending Transactions / Penalties
```

MX:

```text
sese.023 — Securities Settlement Instruction
sese.024 — Settlement Status
sese.025 — Settlement Confirmation
pacs.008 — FI-to-FI Customer Credit Transfer
```

Only show actually implemented messages as generatable.

### Step 4 — Input mode

Offer:

```text
Guided Business Mode
Expert Tag / Element Mode
Load Sample
```

Manual testers should default to:

`Guided Business Mode`

### Step 5 — Enter data

Display only fields relevant to the selected scenario.

Clearly separate:

- Mandatory
- Conditional
- Optional

Do not display 80 empty fields by default.

Optional fields should have:

`+ Add Optional Field`

Repeatable sequences should have:

`+ Add Another`

Every field should have a small information icon.

Clicking it should display:

- What it means
- Why it is needed
- Expected format
- Example
- Dependencies

No LLM call should be necessary for basic field explanations.

### Step 6 — Validate

Use a very simple result:

```text
Ready to Generate

or

3 issues need attention
```

Each issue should explain:

- Field
- Problem
- Expected value
- Suggested correction

### Step 7 — Generate

Display:

- Message type
- Validation result
- Generated message
- Copy
- Download
- Save
- Generate another

Do not require users to understand backend architecture.

---

# 5. MT MESSAGE OUTPUT — PROPER FIN STRUCTURE

For MT messages, generate a correct configured FIN message structure.

Support the proper FIN blocks where applicable:

```text
{1:...}
{2:...}
{3:...}
{4:
...
-}
{5:...}
```

Do not blindly create all blocks if a block/value is not applicable or must be supplied/generated by an external messaging interface.

Clearly classify fields as:

- USER_ENTERED
- PROFILE_CONFIGURED
- APPLICATION_GENERATED
- INTERFACE_GENERATED
- NETWORK_GENERATED

Never fabricate network-generated values.

At minimum, support:

## Block 1 — Basic Header

Configured sender logical terminal/application information.

## Block 2 — Application Header

Message direction/type/receiver and applicable message-level information.

## Block 3 — User Header

Configured supported fields such as MUR when appropriate.

## Block 4 — Text Block

The actual MT message generated by the deterministic MT composer.

## Block 5 — Trailer

Only configured/application-appropriate trailer values.

Do not invent MAC, checksum, authentication, ACK/NAK, session or network-generated trailer values.

Offer output modes:

```text
Block 4 Only
FIN Message
TXT
Canonical JSON
```

If the client later supplies an RJE contract, support it through a separate adapter.

Do not guess RJE structure.

---

# 6. MX / ISO 20022 MESSAGE OUTPUT

Do not represent MX messages as FIN Blocks 1–5.

MX must use the appropriate ISO 20022 structure.

Support:

```text
Business Application Header / AppHdr
+
Document
```

Conceptually:

```xml
<BusinessMessage>
    <AppHdr xmlns="urn:iso:std:iso:20022:tech:xsd:head.001...">
        ...
    </AppHdr>

    <Document xmlns="urn:iso:std:iso:20022:tech:xsd:sese.023...">
        ...
    </Document>
</BusinessMessage>
```

The exact transport/envelope wrapper must be profile-driven.

Never invent a wrapper that is not part of the configured profile.

Support:

- Correct XML namespace
- Correct message version
- Correct element order
- Nested elements
- Choice elements
- Repeated elements
- XML escaping
- Correct date/time formats
- Correct decimal formats
- Code validation
- Namespace-aware parsing
- Pretty XML output
- Compact XML output
- Canonical internal representation

Provide downloads:

```text
XML
Canonical JSON
Validation JSON
Validation HTML
Evidence ZIP
```

---

# 7. PRIORITISE A WORKING MX VERTICAL SLICE

Do not attempt hundreds of ISO 20022 messages overnight.

Implement one excellent working MX lifecycle first.

Priority:

```text
sese.023 — Securities Settlement Transaction Instruction
→ sese.024 — Securities Settlement Transaction Status Advice
→ sese.025 — Securities Settlement Transaction Confirmation
```

Then, if architecture/time permits:

```text
sese.020 — Cancellation Request
sese.027 — Cancellation Status
sese.030 — Settlement Conditions Modification Request
sese.031 — Modification Status
```

Then:

```text
semt.044 — Securities Transaction Penalties Report
```

Corporate actions can follow only if authoritative configured specifications are available.

Do not leave ten half-working MX messages instead of three fully working ones.

---

# 8. MESSAGE INTELLIGENCE

Rename/extend Tag Intelligence into:

# Message Intelligence

It should support:

## MT

- Tags
- Qualifiers
- Sequences

## MX

- XML elements
- XPath
- Parent/child relationship
- Cardinality
- Data type
- Code values

Users should be able to search:

```text
PSET
Settlement Amount
95P
SttlmDt
FinInstrmId
sese.023
```

For every supported field/element display:

- Business meaning
- Technical meaning
- Why it is used
- Mandatory/optional/conditional
- Format
- Example
- Dependencies
- Message types
- Client/profile restrictions
- Source/version

Also display at least one complete annotated sample message for every generatable message.

---

# 9. EXCEL → API → MESSAGE FLOW

This is one of the highest-priority requirements.

Automation testers must be able to maintain tag/element data in Excel and obtain generated SWIFT messages through API.

Build this as a first-class workflow.

# MT Excel format

Provide a downloadable template such as:

| ScenarioID | MessageType | Sequence | Tag | Qualifier | Option | Value |
|---|---|---|---|---|---|---|
| TC001 | MT541 | GENL | 20C | SEME | C | TESTREF001 |
| TC001 | MT541 | TRADDET | 98A | TRAD | A | 20260815 |
| TC001 | MT541 | TRADDET | 98A | SETT | A | 20260818 |

Support multiple rows for the same message.

Support repeated sequences through:

```text
SequenceOccurrence
```

Example:

| ScenarioID | Sequence | SequenceOccurrence | Tag | Qualifier | Value |
|---|---|---:|---|---|---|

# MX Excel format

Use element-level rows:

| ScenarioID | MessageType | XPath | Occurrence | Value |
|---|---|---|---:|---|
| MX001 | sese.023 | /Document/.../TxId | 1 | TEST001 |
| MX001 | sese.023 | /Document/.../SttlmDt | 1 | 2026-08-18 |

The Excel format should be generated from the message specification so automation testers do not manually invent paths.

---

# 10. EXCEL API

Provide an API specifically designed for automation frameworks.

Example:

```http
POST /api/v1/messages/generate-from-excel
Content-Type: multipart/form-data
```

Input:

```text
file=<xlsx>
profileId=<profile>
outputMode=FIN
```

Response should support one or more scenarios.

Example:

```json
{
  "requestId": "REQ001",
  "results": [
    {
      "scenarioId": "TC001",
      "messageType": "MT541",
      "format": "MT",
      "valid": true,
      "validation": {
        "errors": [],
        "warnings": []
      },
      "outputs": {
        "block4": "...",
        "fin": "...",
        "canonicalJson": {}
      }
    }
  ]
}
```

For MX:

```json
{
  "scenarioId": "MX001",
  "messageType": "sese.023",
  "format": "MX",
  "valid": true,
  "outputs": {
    "appHdr": "...",
    "document": "...",
    "xml": "...",
    "canonicalJson": {}
  }
}
```

Automation testers should be able to:

```text
Excel
→ API
→ Generated MT/MX
→ Downstream system
```

without using the UI.

---

# 11. JSON API FOR AUTOMATION

Excel is not the only automation input.

Also provide:

```http
POST /api/v1/messages/generate
```

Support:

```json
{
  "format": "MT",
  "messageType": "MT541",
  "profileId": "CLIENT_A",
  "fields": []
}
```

and:

```json
{
  "format": "MX",
  "messageType": "sese.023",
  "profileId": "CLIENT_A",
  "elements": []
}
```

Return:

- Generated message
- Validation results
- Message type
- Profile/version
- Checksum
- Correlation ID
- Output metadata

This endpoint must be easy to consume from:

- REST Assured
- Playwright
- Karate
- Postman
- Newman
- Python
- Java
- CI/CD pipelines

---

# 12. DO NOT FORCE AUTOMATION TESTERS THROUGH AUTH UI

Create an API authentication model appropriate for automation.

For development:

- Scoped development API token or explicit local automation mode

For enterprise architecture:

- API key/service account/OAuth client abstraction

Do not expose a permanent production credential in source code.

Separate:

```text
Interactive User Authentication
Automation / Service Authentication
```

Document both.

---

# 13. SIMPLE API PAGE

Add one simple UI page:

# API & Automation

It should show:

1. Download MT Excel Template
2. Download MX Excel Template
3. Upload Excel and Test
4. JSON API example
5. curl example
6. Java/REST Assured example
7. Response example

Do not create a complicated developer portal.

Swagger/OpenAPI should remain available for technical users.

---

# 14. VALIDATION

Every generated output must pass applicable deterministic validation.

MT:

```text
Canonical Validation
→ Message Structure
→ Tag/Qualifier Format
→ Business Rules
→ Client Profile
→ FIN Envelope Validation
```

MX:

```text
Canonical Validation
→ XML Well-Formedness
→ XSD Validation
→ Business Rules
→ Usage/Profile Rules
→ Client Profile
→ AppHdr/Document Consistency
```

Return validation results from the API.

Do not return only:

```text
valid=true
```

Return actionable errors.

Example:

```json
{
  "ruleId": "SETTLEMENT_DATE_REQUIRED",
  "field": "SettlementDate",
  "severity": "ERROR",
  "message": "Settlement date is required.",
  "suggestion": "Provide the intended settlement date."
}
```

---

# 15. LLM USAGE

Continue using the LLM efficiently.

Use AI only for:

- Natural-language interpretation
- Ambiguity detection
- Beginner explanation
- Complex business-intent understanding

Do not use AI for:

- MT rendering
- MX XML rendering
- Excel parsing
- Message validation
- XSD validation
- Tag lookup
- Element lookup
- Downloads
- API generation
- Downstream message construction

Use:

```text
Deterministic
→ Cache
→ LLM
```

where appropriate.

Continue showing:

- Live API / Cache / Deterministic
- Tokens
- Cost
- Latency
- Calls avoided
- Tokens avoided

---

# 16. SAMPLE DATA

For every generatable MT/MX message:

Provide:

- Minimal valid sample
- Typical sample
- Full optional-field sample where feasible

Samples must be:

- Synthetic
- Generated by production composers
- Validated
- Annotated
- Loadable into builder
- Downloadable

Do not hardcode manually maintained raw samples when the composer can generate them.

---

# 17. DOWNSTREAM USAGE

The platform's job is to produce a properly structured financial message.

Automation users will consume:

```text
Generated FIN MT
or
Generated MX XML
```

and send it to their downstream test system.

Therefore:

- Preserve exact output in API response
- Avoid adding UI formatting characters
- Preserve line breaks for FIN
- Preserve encoding for XML
- Include checksum/hash
- Include message metadata
- Provide a raw/plain output mode

Do not automatically send messages to a production endpoint.

A connector abstraction may remain, but generation APIs must not depend on downstream connectivity.

---

# 18. ARCHITECTURE SIMPLIFICATION

Audit the current architecture and remove unnecessary complexity where safe.

The ideal architecture should approximately be:

```text
                ┌─────────────────┐
                │      UI         │
                │ Manual Testers  │
                └────────┬────────┘
                         │
                         ▼
                  ┌─────────────┐
                  │  FastAPI    │
                  └──────┬──────┘
                         │
            ┌────────────┴─────────────┐
            │                          │
            ▼                          ▼
      Input Adapters              AI Assistant
      ├─ UI                      └─ Intent only
      ├─ JSON API
      └─ Excel API
            │
            ▼
      Canonical Message Model
            │
            ▼
      Message Specification
            │
     ┌──────┴────────┐
     ▼               ▼
 MT Composer      MX Composer
     │               │
     ▼               ▼
 MT Validator     MX Validator
     │               │
     └───────┬───────┘
             ▼
       Output Service
       ├─ FIN
       ├─ XML
       ├─ JSON
       └─ Reports
```

Do not introduce microservices.

Do not introduce Kafka.

Do not introduce Kubernetes.

Do not create unnecessary abstraction layers.

Keep the application understandable to another developer.

---

# 19. ERROR HANDLING

No silent failures.

UI errors should be simple:

```text
We couldn't generate the message.

2 fields need attention:
• Settlement Date is missing
• Place of Settlement is invalid
```

API errors should be structured.

Never expose:

- Stack traces
- SQL
- Secrets
- API keys
- Raw authentication data

---

# 20. WORKING PROTOTYPE PRIORITY

The goal for overnight execution is not theoretical completeness.

The goal is a working prototype that can be demonstrated tomorrow.

The final system must successfully demonstrate:

## Manual MT Flow

```text
Create Message
→ MT
→ MT541
→ Enter actual values
→ Validate
→ Generate
→ Display proper FIN output
→ Download
```

## Manual MX Flow

```text
Create Message
→ MX
→ sese.023
→ Enter actual values
→ Validate against configured XSD/rules
→ Generate AppHdr + Document XML
→ Download
```

## Automation MT Flow

```text
Excel tag data
→ POST API
→ MT541
→ proper FIN response
```

## Automation MX Flow

```text
Excel XPath/element data
→ POST API
→ sese.023 XML
→ AppHdr + Document response
```

## Message Intelligence

```text
Search PSET
→ See meaning
→ Why used
→ Format
→ Dependencies
→ Sample
```

and:

```text
Search MX element
→ See XPath
→ Business meaning
→ Cardinality
→ Sample XML
```

---

# 21. ACCEPTANCE CRITERIA

Do not declare completion until all critical items below are working.

## UI

1. Navigation is simple.
2. Manual tester understands Create Message immediately.
3. MT/MX selection is obvious.
4. Mandatory fields are obvious.
5. Optional fields are hidden until needed.
6. Repeating sections are easy to add.
7. Validation errors are understandable.
8. Generated output is easy to copy/download.

## MT

9. MT541 real-data generation works.
10. Proper configured FIN output works.
11. Block 4-only output works.
12. FIN download works.
13. No fake network values are generated.

## MX

14. sese.023 real-data generation works.
15. XML is namespace-correct.
16. XSD validation works.
17. AppHdr is supported.
18. Document is supported.
19. Combined configured MX output downloads correctly.
20. No fake FIN five-block MX output exists.

## Excel/API

21. MT Excel template works.
22. MX Excel template works.
23. Excel upload API works.
24. Multiple scenarios work.
25. Row-level validation works.
26. Generated FIN is returned from API.
27. Generated MX XML is returned from API.
28. JSON generation API works.
29. OpenAPI documentation works.
30. Sample curl works.
31. Sample Java/REST Assured usage works.

## Intelligence

32. PSET search works.
33. MX element search works.
34. Sample MT exists.
35. Sample MX exists.
36. Basic intelligence does not call LLM.

## Quality

37. Existing MT tests remain green.
38. Existing AI tests remain green.
39. New MX tests pass.
40. Excel/API tests pass.
41. Backend tests pass.
42. Frontend tests pass.
43. Playwright passes.
44. Lint passes.
45. Type checking passes.
46. Production build passes.
47. Migrations pass.
48. Docker build passes.
49. Runtime smoke passes.
50. Secret scans pass.

---

# 22. TESTS TO ADD

Add strong coverage for:

## MT

- FIN block generation
- Missing envelope data
- Block 4 output
- FIN line preservation
- Download
- JSON API
- Excel API

## MX

- Namespace
- XSD
- AppHdr
- Document
- Element ordering
- Repeating elements
- Choice elements
- Invalid XML
- Invalid code
- Missing mandatory element
- Round trip
- Excel API
- JSON API

## Excel

- Invalid headers
- Duplicate scenario
- Multiple scenarios
- Optional fields
- Repeating sequences
- Bad tag
- Bad XPath
- Missing value
- Unsupported message
- Partial success

## UI

Playwright:

```text
Manual MT541 generation
Manual sese.023 generation
PSET lookup
MX element lookup
Excel MT generation
Excel MX generation
Download MT
Download MX
```

---

# 23. OVERNIGHT EXECUTION ORDER

Use this priority order.

## Priority 1

Audit + plan.

## Priority 2

Simplify UI/navigation.

## Priority 3

Ensure MT541 full FIN generation is rock solid.

## Priority 4

Implement complete sese.023 vertical slice.

## Priority 5

Excel → API → FIN/XML generation.

## Priority 6

Message Intelligence for MT + MX.

## Priority 7

Downloads and examples.

## Priority 8

Tests and regression.

## Priority 9

If time remains:

```text
sese.024
sese.025
```

Do not sacrifice the first working MX flow to partially implement many messages.

---

# 24. VERIFY WITH REAL RUNNING APPLICATION

Do not finish based only on unit tests.

Run the complete application.

Use the browser.

Run:

```text
MT manual flow
MX manual flow
MT Excel/API flow
MX Excel/API flow
```

Inspect:

- Browser console
- Network tab
- Backend logs
- Generated outputs
- Downloads

Fix any issue encountered.

No click should silently fail.

No screen should lead to a dead end.

---

# 25. FINAL REPORT

Create:

`OVERNIGHT_PLATFORM_IMPLEMENTATION_REPORT.md`

Include:

1. Executive summary
2. Audit findings
3. Plan versus actual implementation
4. Architecture before
5. Architecture after
6. UI simplifications
7. MT functionality
8. MX functionality
9. FIN output
10. MX AppHdr/Document output
11. Excel API
12. JSON API
13. Message Intelligence
14. Downloads
15. AI usage
16. Cache usage
17. Files changed
18. Database changes
19. APIs added
20. Tests added
21. Exact test results
22. Browser/manual verification
23. Known limitations
24. Unsupported message types
25. Domain-rule gaps
26. Security review
27. Exact commands to run
28. Demo walkthrough
29. Recommended next phase

Be completely honest about unfinished work.

---

# 26. FINAL CLAUDE RESPONSE

When the overnight work is complete, return a concise summary containing:

- What you audited
- What you simplified
- MT functionality completed
- MX functionality completed
- Excel/API functionality completed
- FIN output status
- MX XML status
- Message Intelligence status
- Tests passed
- Browser flows verified
- Known limitations
- Path to `OVERNIGHT_PLATFORM_IMPLEMENTATION_REPORT.md`
- Exact commands to start the application

Do not ask me any follow-up questions.

Do not wait for me.

Do not stop after the plan.

Take engineering decisions yourself.

Prioritise simplicity and working functionality over unnecessary architecture.

Create a repository if it is not created. Do the necessary commits, pushes and PR's

The application should be runnable in any of the organisation or personal laptops just by pulling the code and running necessary commands. This is how simple our app should be.

The most important success criteria are:

> A manual tester can understand and generate a message without training.

and

> An automation tester can provide Excel/tag/element data through an API and receive a valid generated MT FIN or MX XML message ready to send to the downstream test system.

Begin now with a complete repository audit and written plan, self-review it, and then continue autonomously through implementation, verification, and final reporting.