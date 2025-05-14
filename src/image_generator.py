import requests
import base64
import os
import uuid
import tempfile
from .config import AUTOMATIC1111_API_URL # Assuming you add this to config.py

# Ensure a temporary directory exists (optional, could use tempfile.mkstemp directly)
TEMP_IMAGE_DIR = os.path.join(os.path.dirname(__file__), '..', 'temp_images')
os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)

def generate_image(prompt: str) -> str | None:
    """
    Generates an image using the Automatic1111 API based on the prompt.

    Args:
        prompt: The text prompt for image generation.

    Returns:
        The file path to the temporarily saved image, or None if generation failed.
    """
    if not AUTOMATIC1111_API_URL:
        print("Error: AUTOMATIC1111_API_URL is not configured.")
        return None

    api_endpoint = f"{AUTOMATIC1111_API_URL.rstrip('/')}/sdapi/v1/txt2img"

    # --- Construct the full prompt ---
    quality_tags = "score_9, score_8_up, score_7_up, score_6_up, best quality,"
    print(f"DEBUG image_generator: Original prompt received: '{prompt}'") # DEBUG
    print(f"DEBUG image_generator: Quality tags defined: '{quality_tags}'") # DEBUG

    # Ensure there's a comma and space before adding tags
    processed_prompt = prompt.strip().rstrip(',')
    print(f"DEBUG image_generator: Processed prompt (stripped/rstripped): '{processed_prompt}'") # DEBUG
    full_prompt = f"{quality_tags}, {processed_prompt}"
    print(f"DEBUG image_generator: Constructed full_prompt: '{full_prompt}'") # DEBUG
    # --- End prompt construction ---

    # --- Payload for Automatic1111 ---
    payload = {
        "prompt": full_prompt,
        "steps": 20,
        "sampler_index": "LCM",
        "cfg_scale": 1.25,
        "width": 1152,
        "height": 1408,
        "negative_prompt": "ugly, deformed, blurry, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, young, underage,",
        "n_iter": 1,
        "seed": -1
    } # Correct closing brace
    # --- End Payload ---

    # --- Log the FINAL prompt being sent ---
    # Log directly from the payload dictionary to be certain
    print(f"Sending image generation request to {api_endpoint} with payload prompt: '{payload.get('prompt', 'PROMPT KEY MISSING')}'", flush=True)

    # --- ADD FULL PAYLOAD LOGGING ---
    print(f"DEBUG: Full payload being sent: {payload}", flush=True)
    # --- END ADD ---

    try:
        # Send the POST request to the Automatic1111 API
        # Increase timeout as image generation can take time
        response = requests.post(api_endpoint, json=payload, timeout=180) # Further increased timeout
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        r = response.json()

        # Check if the response contains image data
        if 'images' not in r or not r['images']:
            print("Error: No images found in Automatic1111 response.")
            print(f"Response JSON: {r}") # Log the response for debugging
            return None

        # Decode the base64 image data (assuming the first image is the one we want)
        image_data_base64 = r['images'][0]
        image_data_bytes = base64.b64decode(image_data_base64)

        # Save the image to a temporary file using tempfile for better management
        # Suffix ensures signal-cli recognizes it as an image (e.g., .png)
        # delete=False is important so the file isn't deleted when the handle is closed
        # We will delete it manually after sending using cleanup_image
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png", dir=TEMP_IMAGE_DIR)
        temp_file_path = temp_file.name # Get the path before closing
        temp_file.write(image_data_bytes)
        temp_file.close() # Close the file handle

        print(f"Image saved temporarily to: {temp_file_path}")
        return temp_file_path # Return the path to the saved file

    except requests.exceptions.Timeout:
        print(f"Error: Timeout connecting to Automatic1111 API at {api_endpoint}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Automatic1111 API: {e}")
        return None
    except KeyError as e:
        print(f"Error: Unexpected response format from Automatic1111 API. Missing key: {e}")
        # Check if response object exists before trying to access .text
        if 'response' in locals() and response is not None:
             print(f"Response JSON: {response.text}") # Log raw response text
        return None
    except Exception as e:
        print(f"An unexpected error occurred during image generation or saving: {e}")
        return None

def cleanup_image(file_path: str):
    """Deletes the temporary image file."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            print(f"Cleaned up temporary image: {file_path}")
        except Exception as e:
            print(f"Error cleaning up temporary image {file_path}: {e}")
    else:
        # Don't print error if file_path is None or empty
        if file_path:
            print(f"Skipping cleanup, file not found: {file_path}")

# --- Test Execution Block ---
if __name__ == '__main__':
    print("--- Running image_generator.py directly for testing ---")

    # --- Make sure config is loaded when run directly ---
    # This assumes config.py handles loading .env correctly
    # If not, you might need to explicitly load .env here too
    try:
        # Attempt to load config to ensure AUTOMATIC1111_API_URL is set
        from . import config
        print(f"AUTOMATIC1111_API_URL from config: {config.AUTOMATIC1111_API_URL}")
    except ImportError:
        print("Could not import config, ensure .env is loaded if needed.")
        # Optionally, load .env directly here for standalone testing
        # from dotenv import load_dotenv
        # load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / '.env')
        # AUTOMATIC1111_API_URL = os.getenv("AUTOMATIC1111_API_URL")
        # print(f"AUTOMATIC1111_API_URL from direct load: {AUTOMATIC1111_API_URL}")
    # --- End config load attempt ---


    test_prompt = "a cute cat wearing a wizard hat, digital art"
    print(f"Test Prompt: '{test_prompt}'")

    image_path = None # Initialize image_path
    try:
        image_path = generate_image(test_prompt)

        if image_path:
            print(f"SUCCESS: Image generated and saved to: {image_path}")
            # Optional: You can manually open the image path here to verify
            # import webbrowser
            # webbrowser.open(image_path)
        else:
            print("FAILURE: Image generation failed.")

    except Exception as e:
        print(f"An error occurred during the test: {e}")

    finally:
        # --- IMPORTANT: Clean up the generated image ---
        """if image_path:
            print("Attempting cleanup...")
            # Give a small delay in case the file system needs a moment
            import time
            time.sleep(1)
            cleanup_image(image_path)"""
        # --- End cleanup ---

    print("--- Test finished ---")
