# conditions/

Owner: Person 4 (route and simulation).

Conditions files `<sol>.json` for the replayed sol.

## Reproduce Sol 4600

Set `REDMARK_DATA` to a shared folder outside git, then run:

```bash
uv run python -m conditions.fetch_pds
uv run python -m conditions.gen_conditions
uv run pytest conditions/test_pds_conditions.py tests/test_p4_02_conditions.py
```

The manifest pins the original sol-4600 PDS products, labels and REMS format
definition by direct URL, byte size and SHA-256. Downloads are about 86 MB.
`fetch_pds` verifies existing files rather than silently replacing them.

RAD uses detector E (tissue-equivalent plastic), excluding nonzero-QC records.
Its observation-duration-weighted mean dose rate is converted from microgray
per hour to microgray per **24 Earth hours**, not integrated over data gaps or
interpreted as equivalent dose in sieverts. The units follow the RAD RDR SIS,
section 4.2.1.6:
https://pds-ppi.igpp.ucla.edu/data/MSL-M-RAD-3-RDR-V1.0/DOCUMENT/RAD_RDR_SIS.HTM

REMS uses the MODRDR6 ambient temperature (Kelvin converted to Celsius) and
pressure (Pa). Each step represents the mean of valid paired samples in that
LMST hour, not an instantaneous sample. Temperature must have reliable,
in-operational-range flags, and pressure must have the no-shadow flag.
Missing sentinels and nonfinite values are excluded.

Sun direction and sunset use Mars24 at Gale. Dust is explicitly estimated.
Without the products, the bundled fixtures still work and output remains
labelled `provenance.script: "stub"`. Missing RAD/REMS or any missing emitted
REMS hour also preserves that marker. The real products stay outside git;
the committed result records the producing script, commit and raw-file hashes.
