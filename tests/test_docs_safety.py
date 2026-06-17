from pathlib import Path


def test_safety_docs_keep_paper_only_contract() -> None:
    text = "\n".join(
        [
            Path("README.md").read_text(encoding="utf-8"),
            Path("docs/SAFETY.md").read_text(encoding="utf-8"),
            Path("docs/OPERATING.md").read_text(encoding="utf-8"),
        ],
    ).lower()

    assert "paper-only" in text
    assert "not investment advice" in text
    assert "guaranteed=false" in text
    assert "live_order_enabled=false" in text
    assert "fixed-yield" in text


def test_docs_do_not_claim_guaranteed_returns() -> None:
    docs = [Path("README.md"), Path("docs/SAFETY.md"), Path("docs/OPERATING.md")]
    forbidden = ("guaranteed return", "fixed yield", "live by default")

    for path in docs:
        text = path.read_text(encoding="utf-8").lower()
        for phrase in forbidden:
            assert phrase not in text
