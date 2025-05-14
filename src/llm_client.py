import requests
import json
# --- Import config to potentially use MODEL_IDENTIFIER as fallback ---
from . import config as app_config
# --- End Import ---

class LLMClient:
    # --- Remove model_identifier from constructor arguments ---
    def __init__(self, api_url, max_history=50):
        # Ensure the base URL doesn't end with a slash
        self.base_api_url = api_url.rstrip('/')
        self.chat_endpoint = f"{self.base_api_url}/v1/chat/completions"
        self.models_endpoint = f"{self.base_api_url}/v1/models" # Added models endpoint
        # --- model_identifier will be detected ---
        self.model_identifier = None
        try:
            # --- Ensure max_history is an integer ---
            self.max_history = int(max_history)
        except (ValueError, TypeError):
            print(f"Warning: Invalid max_history value '{max_history}'. Using default 50.")
            self.max_history = 50 # Fallback to default int
        # --- End ensure integer ---
        self.conversations = {}
        print(f"LLMClient initialized. Base API URL: {self.base_api_url}")
        # --- Detect model identifier ---
        self._detect_model_identifier()
        # --- End detect ---
        print(f"Max history length set to: {self.max_history}") # Confirm value

    def _detect_model_identifier(self):
        """Attempts to detect the model identifier from the /v1/models endpoint."""
        print(f"Attempting to detect model identifier from: {self.models_endpoint}")
        try:
            response = requests.get(self.models_endpoint, timeout=10)
            response.raise_for_status()
            models_data = response.json()

            if models_data.get("data") and len(models_data["data"]) > 0:
                # Assume the first model listed is the one currently loaded
                self.model_identifier = models_data["data"][0].get("id")
                if self.model_identifier:
                    print(f"Successfully detected model identifier: {self.model_identifier}")
                else:
                    raise ValueError("Model ID not found in the first model data.")
            else:
                raise ValueError("No model data found in the response.")

        except requests.exceptions.RequestException as e:
            print(f"Error querying models endpoint: {e}")
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            print(f"Error parsing models response: {e}")
            print(f"Raw response text: {response.text if 'response' in locals() else 'N/A'}")

        # --- Fallback logic ---
        if not self.model_identifier:
            print("Failed to auto-detect model identifier.")
            fallback_model = app_config.MODEL_IDENTIFIER # Use from config.py
            if fallback_model:
                print(f"Falling back to MODEL_IDENTIFIER from config: {fallback_model}")
                self.model_identifier = fallback_model
            else:
                # If detection fails and no fallback, raise an error or handle appropriately
                print("Error: Could not determine model identifier. LLMClient may not function.")
                # Optionally raise an exception:
                # raise RuntimeError("Could not determine model identifier.")
        # --- End Fallback ---


    def send_request(self, prompt, user_id=None):
        """
        Send a request to the LLM with conversation history if available

        Args:
            prompt (str): The user's message
            user_id (str): Identifier for the conversation (Signal UUID or number)

        Returns:
            str: The model's response
        """
        # --- Check if model identifier was determined ---
        if not self.model_identifier:
             raise RuntimeError("LLMClient cannot send request: Model identifier is not set.")
        # --- End check ---

        # Initialize or retrieve conversation history
        if user_id not in self.conversations:
            self.conversations[user_id] = []
            # --- REMOVE SYSTEM MESSAGE ADDITION ---
            # print(f"New conversation detected for {user_id}. Adding system message.")
            # system_prompt = "Keep your responses concise and to the point, ideally in 3-4 sentences unless more detail is specifically requested."
            # self.add_system_message(user_id, system_prompt)
            # --- END REMOVAL ---

        # Prepare messages with history
        messages = self.conversations[user_id].copy()
        # Add the new user message
        messages.append({"role": "user", "content": prompt})

        payload = {
            # --- Use the detected or fallback model identifier ---
            "model": self.model_identifier,
            # --- End change ---
            "messages": messages,
            "max_tokens": 300, # Keep max_tokens as a safeguard
            "temperature": 0.8
        }

        headers = {
            "Content-Type": "application/json"
        }

        try:
            print(f"Sending request to: {self.chat_endpoint}")
            print(f"Payload: {json.dumps(payload, indent=2)}")

            response = requests.post(self.chat_endpoint, headers=headers, json=payload)
            response.raise_for_status()

            response_data = response.json()
            print(f"Raw Response Data: {json.dumps(response_data, indent=2)}")

            if response_data.get('choices') and len(response_data['choices']) > 0:
                message = response_data['choices'][0].get('message')
                if message and message.get('content'):
                    assistant_response = message['content'].strip()

                    # Update conversation history
                    self.conversations[user_id].append({"role": "user", "content": prompt})
                    self.conversations[user_id].append({"role": "assistant", "content": assistant_response})

                    # --- Add History Size Logging ---
                    current_history_len = len(self.conversations[user_id])
                    # --- End Logging ---

                    # Trim history if it gets too long
                    if current_history_len > self.max_history:
                        # Remove oldest messages but keep the first system message if present
                        has_system = False
                        if self.conversations[user_id] and self.conversations[user_id][0]["role"] == "system":
                            has_system = True

                        if has_system:
                            system_msg = self.conversations[user_id][0]
                            # Keep max_history-1 messages + 1 system message = max_history total
                            self.conversations[user_id] = self.conversations[user_id][-(self.max_history-1):]
                            self.conversations[user_id].insert(0, system_msg)
                        else:
                            # Keep only the last max_history messages
                            self.conversations[user_id] = self.conversations[user_id][-self.max_history:]

                        # --- Add History Size Logging ---
                        # --- End Logging ---

                    return assistant_response
                else:
                    raise Exception("Error: Response format unexpected. 'message' or 'content' missing.")
            else:
                raise Exception("Error: Response format unexpected. 'choices' array missing or empty.")

        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error sending request to LLM: {e}")
        except Exception as e:
            raise Exception(f"Error processing LLM response: {e}")
    
    def reset_conversation(self, user_id):
        """Reset the conversation history for a specific user"""
        if user_id in self.conversations:
            self.conversations[user_id] = []
            return True
        return False
    
    def add_system_message(self, user_id, system_message):
        """Add a system message at the beginning of a user's conversation"""
        if user_id not in self.conversations:
            self.conversations[user_id] = []

        # Remove any existing system messages
        self.conversations[user_id] = [msg for msg in self.conversations[user_id]
                                      if msg["role"] != "system"]

        # Add the new system message at the beginning
        self.conversations[user_id].insert(0, {"role": "system", "content": system_message})
        return True