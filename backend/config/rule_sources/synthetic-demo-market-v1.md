# Synthetic Demo Market Practice — Securities Settlement

SYNTHETIC MATERIAL. Written for this repository to demonstrate how a market-practice
overlay is derived from evidence and reviewed. It is not a market practice, is not
published by any market infrastructure, and is not derived from CBPR+, HVPS+, SEPA,
MyStandards or any custodian guideline.

## 1 Scope

This document describes conventions that the synthetic demonstration market
`DEMO_MARKET_V1` applies to securities settlement transaction instructions. It restricts
how the message is used; it never changes what the message contains.

## 2 Settlement transaction condition

Instructions sent in this market carry a settlement transaction condition of NOMC, PART
or CLEN. No other condition code is accepted.

## 3 Credit and debit indicator

Where an instruction carries a settlement amount, the credit or debit indicator must be
present so that the direction of the cash movement is explicit.

## 4 What this document does not establish

Nothing here establishes that the underlying message definition is complete, correct or
current. It records conventions only, and only for the synthetic market it names.
