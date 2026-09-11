from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load(name: str) -> str:
    """Load a prompt template by filename (without .txt extension).

    Keeping prompts as versioned .txt files rather than inline strings makes
    them diffable, swappable for evaluation, and editable without touching code.
    """
    path = _PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")
