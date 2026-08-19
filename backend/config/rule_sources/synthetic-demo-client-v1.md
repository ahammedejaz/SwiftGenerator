# Synthetic Demo Client Guideline — Securities Settlement

SYNTHETIC MATERIAL. Written for this repository to demonstrate a client overlay narrowing
a market overlay. It is not a client guideline and is not derived from any real
institution's documentation.

## 1 Scope

This document describes the additional conventions that the synthetic client
`DEMO_MARKET_CLIENT_V1` applies on top of the synthetic market `DEMO_MARKET_V1`. It only
narrows; it never permits anything the market or the message structure does not.

## 2 Settlement transaction condition

Instructions sent by this client carry the settlement transaction condition NOMC. The
other conditions the market permits are not used.

## 3 Common identification

Every instruction sent by this client carries a common identification, so that the
instruction can be matched against the client's own records.

## 4 What this document does not establish

Nothing here establishes completeness. It records this client's conventions, and only for
the synthetic profile it names.
