"""The local financial-message knowledge base (Phase 6).

Authorised standards documents and schemas dropped into an operator-local directory are
discovered, identified from their content, segmented, indexed for lexical and (where policy
allows) semantic retrieval, and — where deterministic structure can be compiled — turned
into local Structure Packs that the ordinary studio engine generates from.

The package is *retrieval, index and cache state*. It is never validation authority:
Structure Packs define structure, reviewed Rule Packs define semantic validation, the
composer builds FIN/XML, and none of them import anything from here.

Runtime generation reads the knowledge database only; source files are opened by the sync
command alone.
"""

KNOWLEDGE_SCHEMA_VERSION = 3
CHUNKER_VERSION = "knowledge-chunker/1"
EMBEDDING_SCHEMA_VERSION = "embedding/1"
PACK_COMPILER_VERSION = "knowledge-pack-compiler/6"
