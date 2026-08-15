# MT530 Guide

The configured MT530 subset is a Transaction Processing Command for verified processing-data
commands only. The five configured rows cover the current source-bounded priority-command golden
path and associated references. It is not a universal amendment message.

The deterministic amendment decision engine classifies changes as processing-data modification,
non-matching information modification, cancellation/cancel-and-rebook, unsupported, or needing
clarification/client approval. Security identifier, quantity, settlement amount/date, and core
event changes are never silently routed through MT530; absent an approved rule they require
cancel-and-rebook or are rejected. Authorised market/client packs are required before expanding
the permitted command catalogue.
