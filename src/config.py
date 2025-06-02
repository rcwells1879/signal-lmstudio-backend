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
FORGE_API_URL = os.getenv("FORGE_API_URL", "http://127.0.0.1:7860") # New

# --- Image Generation Settings ---
DEFAULT_NEGATIVE_PROMPT = os.getenv("DEFAULT_NEGATIVE_PROMPT", "")
DEFAULT_IMAGE_WIDTH = int(os.getenv("DEFAULT_IMAGE_WIDTH", "1440"))
DEFAULT_IMAGE_HEIGHT = int(os.getenv("DEFAULT_IMAGE_HEIGHT", "1280"))
DEFAULT_CFG_SCALE = float(os.getenv("DEFAULT_CFG_SCALE", "1.4"))
DEFAULT_SAMPLING_STEPS = int(os.getenv("DEFAULT_SAMPLING_STEPS", "20"))
DEFAULT_SAMPLER_NAME = os.getenv("DEFAULT_SAMPLER_NAME", "Euler a")
DEFAULT_SCHEDULER = os.getenv("DEFAULT_SCHEDULER", "LCM")
DEFAULT_SEED = int(os.getenv("DEFAULT_SEED", "-1")) # -1 for random

# Hires Fix Settings (example, based on your payload)
DEFAULT_HIRES_FIX_ENABLED = os.getenv("DEFAULT_HIRES_FIX_ENABLED", "False").lower() == 'true'
DEFAULT_HIRES_DENOISING_STRENGTH = float(os.getenv("DEFAULT_HIRES_DENOISING_STRENGTH", "0.7"))
DEFAULT_HIRES_UPSCALER = os.getenv("DEFAULT_HIRES_UPSCALER", "Latent")
DEFAULT_HIRES_UPSCALE_BY = float(os.getenv("DEFAULT_HIRES_UPSCALE_BY", "2.0")) # Assuming index 12 (value 2) is upscale factor
DEFAULT_HIRES_STEPS = int(os.getenv("DEFAULT_HIRES_STEPS", "0")) # Assuming index 14 (value 0) is hires steps

# Add other configurations as needed
SIGNAL_CLI_PATH = os.getenv("SIGNAL_CLI_PATH", "signal-cli")
YOUR_SIGNAL_NUMBER = os.getenv("YOUR_SIGNAL_NUMBER")

# --- Add JSON_RPC_PORT and SIGNAL_DAEMON_ADDRESS ---
JSON_RPC_PORT = int(os.getenv("JSON_RPC_PORT", "7583")) # Default to 7583 if not in .env
SIGNAL_DAEMON_HOST = os.getenv("SIGNAL_DAEMON_HOST", "127.0.0.1")
SIGNAL_DAEMON_ADDRESS = f"{SIGNAL_DAEMON_HOST}:{JSON_RPC_PORT}"
# --- End Add ---

# Add a check for debugging
if YOUR_SIGNAL_NUMBER is None:
    print("Error: YOUR_SIGNAL_NUMBER is None after attempting to load .env. Check .env file content and location.")
else:
    print(f"Successfully loaded YOUR_SIGNAL_NUMBER: {YOUR_SIGNAL_NUMBER}")

print(f"Signal Daemon Address configured to: {SIGNAL_DAEMON_ADDRESS}") # For verification