# Changelog

## v1.0.4 - 2026-06-26

- Rewrite setup and options text around beginner tasks instead of Bermuda internals.
- Format wizard results as readable lines instead of raw Python-style dictionaries.
- Add clearer next-step guidance to audit, calibration, scanner balancing, and walk-test results.

## v1.0.3 - 2026-06-25

- Add runtime `translations/en.json` so Home Assistant displays setup and options flow labels for custom installations.

## v1.0.2 - 2026-06-25

- Fix config-flow loading by removing a bad `ServiceResponse` import from `homeassistant.const`.
- Lazy-load runtime Bermuda manager code from options steps so Add Integration can always register the handler.

## v1.0.1 - 2026-06-25

- Fix the HACS release archive layout so files install directly into `custom_components/bermuda_tuner`.
- Store initial AI setup choices without the newer config-flow `options=` argument.
- Add a conversation-agent selector fallback for older Home Assistant selector builds.

## v1.0.0 - 2026-06-21

- Add setup and coverage audits from redacted Bermuda observations.
- Add one-metre reference power and measured-distance attenuation calibration.
- Add scanner balancing and walk-test ambiguity analysis.
- Add plain-English setting explanations.
- Add validated preview, snapshot, apply, and rollback actions.
- Add optional provider-neutral Home Assistant Conversation explanations.
- Add redacted diagnostics, HACS packaging, tests, and original artwork.
