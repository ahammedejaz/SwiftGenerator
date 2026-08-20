"""AI-assisted authoring (Phase 6): identify, prepare, sample, test data, enrichment.

The model does exactly four things here: understand a business request, choose a message
from the discovered catalogue, prepare canonical values for fields the Structure Pack
declares, and phrase human explanations with citations. It never renders FIN or XML, never
decides validity, never adds a field, code, sequence or element the structure lacks, and
never changes the message type or release it was given.

Every operation computes a deterministic seed first. The seed is what a scripted provider
returns in CI, what the platform falls back to when no model is configured, and the starting
point a live model refines inside a closed JSON schema.
"""

PROMPT_VERSION = "ai-authoring-prompt/1"
OUTPUT_SCHEMA_VERSION = "ai-authoring-schema/1"
