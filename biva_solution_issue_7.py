#!/usr/bin/env python3
import argparse

__version__ = "1.0.0"

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bretzel",
        description="Bretzel command line interface."
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show the version and exit."
    )
    args = parser.parse_args()
    if args.version:
        print(f"bretzel version {__version__}")
        return

    # Placeholder for other commands
    parser.print_help()

if __name__ == "__main__":
    main()
