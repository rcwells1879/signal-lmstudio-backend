import requests
import base64
import os
import tempfile
import random
import string
import time
import orjson

from .config import (
    FORGE_API_URL,
    DEFAULT_NEGATIVE_PROMPT,
    DEFAULT_IMAGE_WIDTH,
    DEFAULT_IMAGE_HEIGHT,
    DEFAULT_CFG_SCALE,
    DEFAULT_SAMPLING_STEPS,
    DEFAULT_SAMPLER_NAME,
    DEFAULT_SCHEDULER,
    DEFAULT_SEED,
    DEFAULT_HIRES_FIX_ENABLED,
    DEFAULT_HIRES_DENOISING_STRENGTH,
    DEFAULT_HIRES_UPSCALER,
    DEFAULT_HIRES_UPSCALE_BY,
    DEFAULT_HIRES_STEPS
)

TEMP_IMAGE_DIR = os.path.join(os.path.dirname(__file__), '..', 'temp_images')
os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)

def generate_random_string(length=15):
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))

def generate_image(prompt: str) -> str | None:
    if not FORGE_API_URL:
        print("Error: FORGE_API_URL is not configured.")
        return None

    task_id_payload = f"task({generate_random_string()})"
    session_hash_payload = generate_random_string()

    # Register task with /internal/progress
    internal_progress_endpoint = f"{FORGE_API_URL.rstrip('/')}/internal/progress"
    progress_request_payload = {
        "id_task": task_id_payload,
        "id_live_preview": -1,
        "live_preview": False
    }
    
    try:
        response_progress_init = requests.post(internal_progress_endpoint, json=progress_request_payload, timeout=10)
        response_progress_init.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error calling initial /internal/progress: {e}")
        return None

    # Construct prompt with quality tags
    quality_tags = "best quality, dynamic lighting"
    user_or_llm_prompt = prompt.strip()
    current_prompt = f"{quality_tags.rstrip(', ')}, {user_or_llm_prompt.lstrip(', ')}" if user_or_llm_prompt else quality_tags
    
    # Payload array for Stable Diffusion Forge WebUI (fn_index: 256)
    # Order and types must match exactly what the UI expects
    data_payload_list = [
        task_id_payload,
        current_prompt,
        DEFAULT_NEGATIVE_PROMPT,
        [],
        1,  # Batch count
        1,  # Batch size
        1.3,
        3.5,
        DEFAULT_IMAGE_WIDTH,
        DEFAULT_IMAGE_HEIGHT,
        DEFAULT_HIRES_FIX_ENABLED,
        DEFAULT_HIRES_DENOISING_STRENGTH,
        DEFAULT_HIRES_UPSCALE_BY,
        DEFAULT_HIRES_UPSCALER,
        DEFAULT_HIRES_STEPS,
        0,  # Hires target width
        0,  # Hires target height
        "Use same checkpoint",
        ["Use same choices"],
        "Use same sampler",
        "Use same scheduler",
        "",  # Script name
        "",  # Script arguments
        DEFAULT_CFG_SCALE,
        3.5,
        None,
        "None",  # Sampler override
        DEFAULT_SAMPLING_STEPS,
        DEFAULT_SAMPLER_NAME,
        DEFAULT_SCHEDULER,
        False,  # Restore faces
        "",     # Tiling
        0.8,    # Denoising strength
        DEFAULT_SEED,
        False,  # Variation seed enabled
        -1,     # Variation seed
        0,      # Variation seed strength
        0,      # Resize seed from H/W
        0,      # Sigma churn
        
        # ControlNet parameters
        None, None, None, False, 7, 1, "Constant", 0, "Constant", 0, 1,
        
        # ADetailer parameters
        "enable", "MEAN", "AD", 1, False, 1.01, 1.02, 0.99, 0.95, 0, 1, False,
        0.5, 2, 1, False, 3, 0, 0, 1, False, 3, 2, 0, 0.35, True, "bicubic", "bicubic",
        False, 0, "anisotropic", 0, "reinhard", 100, 0, "subtract", 0, 0, "gaussian",
        "add", 0, 100, 127, 0, "hard_clamp", 5, 0, "None", "None",
        
        # Additional parameters
        False, "MultiDiffusion", 768, 768, 64, 4, False, 1, False, False, False, False,
        "positive", "comma", 0, False, False, "start", "", False,
        "Seed", "", "", "Nothing", "", "", "Nothing", "", "",
        True, False, False, False, False, False, False, 0, False
    ]

    # Submit job to queue
    queue_join_endpoint = f"{FORGE_API_URL.rstrip('/')}/queue/join"
    queue_join_payload = {
        "data": data_payload_list,
        "event_data": None,
        "fn_index": 256,
        "trigger_id": 16,
        "session_hash": session_hash_payload
    }

    try:
        response_join = requests.post(queue_join_endpoint, json=queue_join_payload, timeout=30)
        response_join.raise_for_status()
        
        # Connect to SSE stream for results
        queue_data_endpoint = f"{FORGE_API_URL.rstrip('/')}/queue/data"
        queue_data_params = {"session_hash": session_hash_payload}
        
        time.sleep(1)
        image_path_from_sse = None

        try:
            response_sse = requests.get(queue_data_endpoint, params=queue_data_params, timeout=180, stream=True)
            response_sse.raise_for_status()

            for line in response_sse.iter_lines(decode_unicode=True):
                if not line or not line.startswith('data: '):
                    continue
                    
                event_data_str = line[len('data: '):]
                try:
                    event_data = orjson.loads(event_data_str)
                    msg_type = event_data.get("msg")

                    if msg_type == "process_completed":
                        output_data = event_data.get("output", {}).get("data")
                        if output_data and isinstance(output_data, list) and output_data:
                            image_results_container = output_data[0]
                            if isinstance(image_results_container, list) and image_results_container:
                                first_image_data_item = image_results_container[0]

                                image_url_to_download = None
                                if isinstance(first_image_data_item, dict):
                                    image_dict = first_image_data_item.get('image')
                                    if image_dict and isinstance(image_dict, dict):
                                        image_url_to_download = image_dict.get('url')

                                # Handle direct base64 fallback
                                elif isinstance(first_image_data_item, str) and first_image_data_item.startswith('data:image/png;base64,'):
                                    img_b64_str = first_image_data_item.split(',', 1)[1]
                                    try:
                                        image_data_bytes = base64.b64decode(img_b64_str)
                                        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png", dir=TEMP_IMAGE_DIR)
                                        temp_file.write(image_data_bytes)
                                        temp_file.close()
                                        response_sse.close()
                                        image_path_from_sse = temp_file.name
                                        break
                                    except Exception as e:
                                        print(f"Error decoding base64: {e}")

                                # Download image from URL
                                if image_url_to_download and isinstance(image_url_to_download, str) and image_url_to_download.startswith('http'):
                                    try:
                                        if image_url_to_download.startswith('/file='):
                                            absolute_image_url = f"{FORGE_API_URL.rstrip('/')}{image_url_to_download}"
                                        else:
                                            absolute_image_url = image_url_to_download

                                        image_response = requests.get(absolute_image_url, timeout=30)
                                        image_response.raise_for_status()
                                        
                                        image_data_bytes = image_response.content
                                        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png", dir=TEMP_IMAGE_DIR)
                                        temp_file.write(image_data_bytes)
                                        temp_file.close()
                                        response_sse.close()
                                        image_path_from_sse = temp_file.name
                                        break
                                    except Exception as e:
                                        print(f"Error downloading image: {e}")

                        if image_path_from_sse:
                            break
                            
                except Exception as e:
                    print(f"Error parsing SSE event: {e}")
                    continue

            if image_path_from_sse:
                return image_path_from_sse

        except requests.exceptions.RequestException as e:
            print(f"Error during SSE connection: {e}")

    except requests.exceptions.RequestException as e:
        print(f"Error during API call: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None
    
    print("Image generation failed")
    return None

def cleanup_image(file_path: str):
    """Deletes the temporary image file."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Error cleaning up image {file_path}: {e}")

if __name__ == '__main__':
    if not FORGE_API_URL:
        print("FORGE_API_URL not configured")
    else:
        test_prompt = "a beautiful landscape"
        image_path = generate_image(test_prompt)
        if image_path:
            print(f"Image generated: {image_path}")
        else:
            print("Image generation failed")
