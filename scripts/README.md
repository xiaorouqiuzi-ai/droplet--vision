# Scripts

`inspect_cine.py` prints core metadata and timing; `--json` saves a portable
report. `build_cine_inventory.py` scans a root and writes CSV/JSON; hashing is
opt-in. Both run from a source checkout without package installation. See
../docs/cine_reader.md. Scientific logic remains in src/droplet_vision.

`launch_viewer.py [--cine PATH] [--taxonomy JSON]` starts the optional PySide6
Viewer from a source checkout in VisionLab. See ../docs/cine_viewer.md.

`build_annotation_queue.py` builds or resumes reproducible sampling queues;
see [sampling and queue usage](../docs/frame_sampling_queue.md).

`check_docs_links.py` checks README/docs local link targets and Markdown anchors
offline using only the standard library. Run `python scripts/check_docs_links.py`
from the checkout; external URLs are not fetched.
