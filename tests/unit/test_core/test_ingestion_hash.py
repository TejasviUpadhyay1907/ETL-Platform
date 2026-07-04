"""
Unit tests for HashGenerator and compute_sha256.

Tests verify:
- SHA-256 hash produced correctly for known content
- Same file produces same hash (deterministic)
- Different content produces different hash
- Large files handled without memory error
- Missing file raises FileReadException
"""

import hashlib
from pathlib import Path

import pytest

from app.core.exceptions import FileReadException
from app.ingestion.hash_generator import HashGenerator, compute_sha256


class TestComputeSha256:

    def test_known_content(self, tmp_path: Path):
        """Hash of known bytes must match hand-computed value."""
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()
        f = tmp_path / "test.txt"
        f.write_bytes(content)
        assert compute_sha256(f) == expected

    def test_empty_file(self, tmp_path: Path):
        """Empty file has the SHA-256 of empty bytes."""
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_sha256(f) == expected

    def test_deterministic(self, tmp_path: Path):
        """Same file → same hash on repeated calls."""
        f = tmp_path / "data.csv"
        f.write_bytes(b"order_id,total\nORD-001,100.00\n")
        h1 = compute_sha256(f)
        h2 = compute_sha256(f)
        assert h1 == h2

    def test_different_content_different_hash(self, tmp_path: Path):
        """Files with different content must produce different hashes."""
        f1 = tmp_path / "a.csv"
        f2 = tmp_path / "b.csv"
        f1.write_bytes(b"content_a")
        f2.write_bytes(b"content_b")
        assert compute_sha256(f1) != compute_sha256(f2)

    def test_hash_length_is_64_chars(self, tmp_path: Path):
        """SHA-256 hex digest is always 64 characters."""
        f = tmp_path / "x.csv"
        f.write_bytes(b"test")
        assert len(compute_sha256(f)) == 64

    def test_hash_is_lowercase_hex(self, tmp_path: Path):
        """Digest contains only lowercase hex characters."""
        f = tmp_path / "x.csv"
        f.write_bytes(b"test data")
        digest = compute_sha256(f)
        assert all(c in "0123456789abcdef" for c in digest)

    def test_missing_file_raises(self, tmp_path: Path):
        """Non-existent file raises FileReadException."""
        from app.core.exceptions import FileReadException
        with pytest.raises(FileReadException):
            compute_sha256(tmp_path / "nonexistent.csv")

    def test_large_file(self, tmp_path: Path):
        """1 MB file is hashed without memory error."""
        f = tmp_path / "large.csv"
        f.write_bytes(b"x" * 1_048_576)  # 1 MB
        digest = compute_sha256(f)
        assert len(digest) == 64


class TestHashGenerator:

    def test_generate_returns_string(self, tmp_path: Path):
        f = tmp_path / "test.csv"
        f.write_bytes(b"id,name\n1,Alice\n")
        gen = HashGenerator()
        result = gen.generate(f)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_files_are_identical_true(self, tmp_path: Path):
        content = b"same content"
        f1 = tmp_path / "a.csv"
        f2 = tmp_path / "b.csv"
        f1.write_bytes(content)
        f2.write_bytes(content)
        gen = HashGenerator()
        assert gen.files_are_identical(f1, f2) is True

    def test_files_are_identical_false(self, tmp_path: Path):
        f1 = tmp_path / "a.csv"
        f2 = tmp_path / "b.csv"
        f1.write_bytes(b"content_a")
        f2.write_bytes(b"content_b")
        gen = HashGenerator()
        assert gen.files_are_identical(f1, f2) is False
