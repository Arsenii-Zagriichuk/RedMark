# tools/

Owner: Person 1 (app, service shell and submission).

Repo tooling: the contract checker behind the smoke test, the contract code generator, and the CI guardrails (P1-15): `owners.py` (the folder owners, the one-owner check and the owner-guard hook) and `check_file_sizes.py` (the 5 MB limit).

`target_pictures.py` (P1-09) downloads the Target preview's Curiosity raw images into `app/public/targets/` and writes `app/src/target/curiosity-pictures.json` and `app/data-manifest.yaml`. Rerun it when `sites/gale.yaml`'s science targets change.

Branch protection for main lives in `.github/branch-protection.json`. A repo admin applies it once:

```bash
gh api -X PUT repos/Arsenii-Zagriichuk/RedMark/branches/main/protection --input .github/branch-protection.json
```
