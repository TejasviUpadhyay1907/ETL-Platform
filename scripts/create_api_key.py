"""
API key generator.

Creates a new API key, hashes it for database storage, and prints both
the plain-text key (show once) and the hash to store.

In a full implementation (Milestone 8), this would INSERT the hash into
an api_keys table. For now it demonstrates the hashing utility.

Usage:
    python scripts/create_api_key.py
    python scripts/create_api_key.py --name "My Service"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a new API key")
    parser.add_argument("--name", default="default", help="Name/label for this key")
    args = parser.parse_args()

    from app.utils.hash_utils import generate_api_key, hash_api_key
    from app.core.config import get_config

    config = get_config()
    plain_key = generate_api_key(prefix="etl")
    hashed_key = hash_api_key(plain_key, config.api_key_salt)

    print("\n" + "=" * 60)
    print("API KEY GENERATED")
    print("=" * 60)
    print(f"Name    : {args.name}")
    print(f"Key     : {plain_key}")
    print(f"Hash    : {hashed_key}")
    print("=" * 60)
    print("IMPORTANT: Store the plain key securely — it will not be shown again.")
    print("Store the hash in the database api_keys table (Milestone 8).\n")


if __name__ == "__main__":
    main()
