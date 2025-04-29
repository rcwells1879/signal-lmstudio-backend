import os
from dotenv import load_dotenv
from pathlib import Path # Import pathlib

# Construct the path to the project root directory (one level up from src)
# __file__ is the path to config.py
project_root = Path(__file__).resolve().parent.parent
dotenv_path = project_root / '.env'

# Load the .env file from the explicit path
print(f"Attempting to load .env file from: {dotenv_path}")
# Add override=True
found_dotenv = load_dotenv(dotenv_path=dotenv_path, override=True)
if not found_dotenv:
    print("Warning: .env file not found or failed to load.")
else:
    print(".env file loaded successfully.")


# Configuration settings
API_URL = os.getenv("API_URL", "http://127.0.0.1:1234")
MODEL_IDENTIFIER = os.getenv("MODEL_IDENTIFIER", "cydonia-24b-v2.1")

# Add other configurations as needed
SIGNAL_CLI_PATH = os.getenv("SIGNAL_CLI_PATH", "signal-cli")
YOUR_SIGNAL_NUMBER = os.getenv("YOUR_SIGNAL_NUMBER")

# Add a check for debugging
if YOUR_SIGNAL_NUMBER is None:
    print("Error: YOUR_SIGNAL_NUMBER is None after attempting to load .env. Check .env file content and location.")
else:
    print(f"Successfully loaded YOUR_SIGNAL_NUMBER: {YOUR_SIGNAL_NUMBER}")