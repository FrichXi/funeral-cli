# Framework Artifacts

This directory stores local framework-building artifacts that sit between the raw article corpus and the runtime judge.

Expected files:

- `judgment_atoms.generated.jsonl`: raw LangExtract output from `scripts/extract_framework.py`
- `judgment_atoms.generated.html`: review UI generated from the JSONL file
- curated principle packs or overrides you may want to pass via `--framework-pack`

Current runtime default:

- the CLI uses the bundled seed pack at `funeralai/framework/framework_pack.seed.json`
- generated files in this directory are for review and iteration, not loaded automatically
