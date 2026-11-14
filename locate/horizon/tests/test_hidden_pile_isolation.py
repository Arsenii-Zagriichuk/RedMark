"""Hidden piles stay hidden (AGENTS.md rule 6): only the scoring scripts point
at the hidden-pile folder, so no tuning code can read it."""

import re
from pathlib import Path

from contracts.paths import REPO_ROOT

# The scripts allowed to name the hidden pile: the one that fetches it and the
# one that scores the matcher on it.
SCORING_SCRIPTS = {"locate/horizon/hidden_pile.py", "locate/horizon/hidden_test.py"}
# The folder's name in any spelling a path can take, or the constant that holds it.
POINTS_AT_HIDDEN_PILE = re.compile(r"navcam/hidden|[\"']hidden[\"']|HIDDEN_PILE")
SKIPPED_DIRS = {".git", ".venv", "node_modules", "worktrees", "__pycache__"}


def hidden_pile_readers(root: Path) -> set[str]:
    """Every Python file under root, other than tests, that points at the hidden pile."""
    readers = set()
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if SKIPPED_DIRS & set(relative.parts) or "tests" in relative.parts:
            continue
        if POINTS_AT_HIDDEN_PILE.search(path.read_text(errors="ignore")):
            readers.add(relative.as_posix())
    return readers


def test_a_tuning_script_naming_the_hidden_pile_is_caught(tmp_path):
    (tmp_path / "locate/horizon").mkdir(parents=True)
    (tmp_path / "locate/horizon/tune.py").write_text('frames = root / "navcam" / "hidden"\n')
    (tmp_path / "locate/horizon/fix.py").write_text('frames = root / "navcam"\n')

    assert hidden_pile_readers(tmp_path) == {"locate/horizon/tune.py"}


def test_only_the_scoring_scripts_point_at_the_hidden_pile():
    assert hidden_pile_readers(REPO_ROOT) == SCORING_SCRIPTS
