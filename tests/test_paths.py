from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aoh.pack import PackError
from aoh.paths import safe_join, safe_segment


# --- safe_segment ---


def test_safe_segment_accepts_simple_lowercase() -> None:
    assert safe_segment("binding", "kubeops-sresquad") == "kubeops-sresquad"


def test_safe_segment_accepts_single_char() -> None:
    assert safe_segment("group", "a") == "a"


def test_safe_segment_accepts_digits() -> None:
    assert safe_segment("group", "prod123") == "prod123"


def test_safe_segment_rejects_empty() -> None:
    try:
        safe_segment("binding", "")
    except PackError:
        pass
    else:
        raise AssertionError("safe_segment should reject empty string")


def test_safe_segment_rejects_uppercase() -> None:
    try:
        safe_segment("group", "Prod")
    except PackError:
        pass
    else:
        raise AssertionError("safe_segment should reject uppercase")


def test_safe_segment_rejects_path_separator() -> None:
    try:
        safe_segment("binding", "a/b")
    except PackError:
        pass
    else:
        raise AssertionError("safe_segment should reject embedded separator")


def test_safe_segment_rejects_dotdot() -> None:
    try:
        safe_segment("binding", "..")
    except PackError:
        pass
    else:
        raise AssertionError("safe_segment should reject '..'")


def test_safe_segment_rejects_leading_hyphen() -> None:
    try:
        safe_segment("binding", "-abc")
    except PackError:
        pass
    else:
        raise AssertionError("safe_segment should reject leading hyphen")


def test_safe_segment_rejects_trailing_hyphen() -> None:
    try:
        safe_segment("binding", "abc-")
    except PackError:
        pass
    else:
        raise AssertionError("safe_segment should reject trailing hyphen")


def test_safe_segment_rejects_absolute_looking_value() -> None:
    try:
        safe_segment("binding", "/etc/passwd")
    except PackError:
        pass
    else:
        raise AssertionError("safe_segment should reject absolute-looking value")


def test_safe_segment_rejects_too_long() -> None:
    try:
        safe_segment("binding", "a" * 64)
    except PackError:
        pass
    else:
        raise AssertionError("safe_segment should reject values over 63 chars")


def test_safe_segment_accepts_max_length_63() -> None:
    value = "a" * 63
    assert safe_segment("binding", value) == value


def test_safe_segment_error_message_includes_kind() -> None:
    try:
        safe_segment("group", "Bad Name")
    except PackError as exc:
        assert "group" in str(exc)
    else:
        raise AssertionError("safe_segment should raise PackError")


# --- safe_join ---


def test_safe_join_simple(tmp_path: Path) -> None:
    result = safe_join(tmp_path, "abc", "def")
    assert result == (tmp_path / "abc" / "def").resolve()


def test_safe_join_single_segment(tmp_path: Path) -> None:
    result = safe_join(tmp_path, "abc")
    assert result == (tmp_path / "abc").resolve()


def test_safe_join_no_segments_returns_root(tmp_path: Path) -> None:
    result = safe_join(tmp_path)
    assert result == tmp_path.resolve()


def test_safe_join_rejects_absolute_segment(tmp_path: Path) -> None:
    try:
        safe_join(tmp_path, "/etc/passwd")
    except PackError:
        pass
    else:
        raise AssertionError("safe_join should reject an absolute segment")


def test_safe_join_rejects_embedded_separator(tmp_path: Path) -> None:
    try:
        safe_join(tmp_path, "a/b")
    except PackError:
        pass
    else:
        raise AssertionError("safe_join should reject a segment containing '/'")


def test_safe_join_rejects_dotdot_segment(tmp_path: Path) -> None:
    try:
        safe_join(tmp_path, "..")
    except PackError:
        pass
    else:
        raise AssertionError("safe_join should reject '..' segment")


def test_safe_join_rejects_dotdot_escape_combo(tmp_path: Path) -> None:
    try:
        safe_join(tmp_path, "..", "etc")
    except PackError:
        pass
    else:
        raise AssertionError("safe_join should reject a '..' escape combo")


def test_safe_join_rejects_empty_segment(tmp_path: Path) -> None:
    try:
        safe_join(tmp_path, "")
    except PackError:
        pass
    else:
        raise AssertionError("safe_join should reject an empty segment")


def test_safe_join_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-target"
    outside.mkdir(exist_ok=True)
    root = tmp_path / "root"
    root.mkdir()
    escape_link = root / "escape"
    escape_link.symlink_to(outside)

    try:
        safe_join(root, "escape", "file.txt")
    except PackError:
        pass
    else:
        raise AssertionError("safe_join should reject a path escaping root via symlink")
