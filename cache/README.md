# cache/

Owner: shared.

The demo cache: `demo/<producer>/<step>.json`, one saved response per step of the 3-minute demo, due H16. Each producer writes only its own subfolder; the service's recorder (P1-02) writes them too. Every JSON file here must match a contract.

Images the cached responses name, for the offline demo to bundle: the horizon demo fixes' overlays are in `demo/horizon/overlays/`, under the file name of each fix result's `overlay` (written by `locate/horizon/demo_fixes.py`).
