"""Run:  python check_gemini.py   — tests network, key, model and image requests, and says what is wrong."""
import sys
from gemini_check import run_cli

if __name__ == "__main__":
    sys.exit(run_cli())
