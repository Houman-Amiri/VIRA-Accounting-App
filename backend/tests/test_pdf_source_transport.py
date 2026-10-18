"""Archive transport must not silently drop the explicitly licensed .github file."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("workflow,artifact", [
    ("pdf-source-kit.yml", "private-native-source-kit-not-recipient-publication"),
    ("pdf-modified-source-kit.yml", "private-complete-modified-sources-no-dlls"),
    ("pdf-license-proof.yml", "private-native-license-review-and-source"),
])
def test_validated_source_envelope_transports_hidden_licensed_workflow(workflow, artifact):
    text = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
    upload = next(block for block in text.split("- uses: actions/upload-artifact@v4")
                  if f"name: {artifact}" in block)
    assert "include-hidden-files: true" in upload
    assert "if-no-files-found: error" in upload
    assert "retention-days: 90" in upload
    # Opt-in applies only to this scoped source review artifact, not a repository upload.
    assert "path: .\n" not in upload and "path: ./\n" not in upload
