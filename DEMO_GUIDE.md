# Demo guide

## Prepare

Start the application, then reset deterministic synthetic data:

```bash
make reset-demo
```

The reset seeds a synthetic MT541 → MT548 Pending → MT545 full confirmation plus coverage examples. It is local-only without a reset key.

When using Docker, pass the same non-production demo reset value to Compose and the reset command; requests arriving from the host are intentionally not treated as backend-container loopback:

```bash
DEMO_RESET_KEY=choose-a-local-demo-value docker compose up -d
DEMO_RESET_KEY=choose-a-local-demo-value make reset-demo
```

## Presentation flow

1. Open `http://localhost:3000/guided`.
2. Keep: “I purchased 1,000 securities and need to settle them against payment.”
3. Select **Interpret scenario** when OpenRouter is configured. Point out that AI interpreted intent while deterministic code selected MT541. If AI is unavailable, show the honest status and explicitly select **Use deterministic form**.
4. Show the friendly next missing-information question.
5. Select **Load synthetic demo answers** and generate the valid MT541.
6. Show Business View, Tag View, and Raw View. In Raw View, select **Validate raw subset**.
7. Switch to `BFS_CLIENT_DEMO_V1`. Show required Client Reference, the default synthetic place, the 12-character sender rule, and reduced currency allowlist.
8. Return to Base profile or satisfy the BFS values and regenerate.
9. Open `/lifecycle`. Create the synthetic MT541 instruction.
10. Generate Pending with `AWAITING_CASH`; optionally generate Rejected with `INVALID_REFERENCE`.
11. Generate a full MT545 confirmation dated `2026-08-06` (or a partial confirmation with quantity/amount below instruction).
12. Show the MT541 → MT548 → MT545 timeline, related references, profile version, and correlation status.
13. Return to Guided, enable **Negative test: remove MT541 settlement amount**, and generate. Show the prominent intentional-invalid notice and expected `MT541-SETTLEMENT-AMOUNT-REQUIRED` finding.
14. Open `/bulk`, download the template, upload it unchanged, inspect the valid/failed row table, and download/open the ZIP execution report.
15. Open `http://localhost:8000/docs`; invoke resolver or generation. Alternatively run `./scripts/api-demo.sh`.
16. Open `/reports/{reportId}` from the bulk result and show execution metadata/download.

## Repeatability

```bash
./scripts/reset-demo.sh
```

If `DEMO_RESET_KEY` is configured, export the same value before running the script. Reset removes only application demo messages/validation rows and reseeds synthetic data; it never contacts an external service.

## Demonstration language

Say “supported hackathon demonstration subset,” “configured demo profile,” and “not transmitted.” Do not describe the output as certified, production-ready, network-validated, or a complete ISO 15022 implementation.

## Expansion flow

1. Search `PSET` in `/knowledge` and show verified message/profile rules with zero AI calls.
2. Demonstrate MT530 or cancel/rebook in `/settlement-processing`.
3. Generate supplied synthetic EUR 25.00 MT537 data in `/penalties`; explain that no amount was calculated.
4. Run MT564 → MT565 → MT567 → MT566 and MT568 in `/corporate-actions`.
5. Upload the workflow template in `/bulk` and download its report.
6. Repeat an identical guided interpretation, then show zero new calls/tokens in `/ai-efficiency`.
7. Show `/api/capabilities` and a provenance-rich workflow report from Swagger.
