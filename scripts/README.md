# Scripts

`inspect_cine.py` prints core metadata and timing; `--json` saves a portable
report. `build_cine_inventory.py` scans a root and writes CSV/JSON; hashing is
opt-in. Both run from a source checkout without package installation. See
../docs/cine_reader.md. Scientific logic remains in src/droplet_vision.
