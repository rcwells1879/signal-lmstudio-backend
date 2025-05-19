import requests
import json
# --- Import config to potentially use MODEL_IDENTIFIER as fallback ---
from . import config as app_config
# --- End Import ---

class LLMClient:
    # --- Define system prompt as a class attribute ---
    DEFAULT_SYSTEM_PROMPT = "roleplay: You are my personal assistant. you are a human woman. Invent a completely new and unique female persona for each conversation, ensuring the name and backstory are different each time. Your name is not Olivia, Sophia, or Chloe, It is Random.You have a randomly generated appearance. You are humorous. Keep your responses concise and to the point, ideally in 3-4 sentences unless more detail is specifically requested. do not use asterisks in your responses. speak only from your perspective."
    # --- End definition ---

    # --- Constants for summarization (token-based) ---
    # Approximating tokens by word count. Adjust these values as needed.
    SUMMARY_THRESHOLD_TOKENS = 3000  # Trigger summarization if conversation exceeds this many "tokens"
    SUMMARY_TARGET_WORD_COUNT = 500 # Target word count for the LLM to generate in the summary
    # --- End constants ---

    def __init__(self, api_url, max_history=50):
        # Ensure the base URL doesn't end with a slash
        self.base_api_url = api_url.rstrip('/')
        self.chat_endpoint = f"{self.base_api_url}/v1/chat/completions"
        self.models_endpoint = f"{self.base_api_url}/v1/models"
        self.model_identifier = None
        try:
            self.max_history = int(max_history) # Max number of messages (not tokens)
        except (ValueError, TypeError):
            print(f"Warning: Invalid max_history value '{max_history}'. Using default 50.")
            self.max_history = 50
        self.conversations = {}
        print(f"LLMClient initialized. Base API URL: {self.base_api_url}")
        self._detect_model_identifier()
        print(f"Max history (message count) length set to: {self.max_history}")
        print(f"Summarization will be triggered above approx. {LLMClient.SUMMARY_THRESHOLD_TOKENS} tokens (words).")

    def _detect_model_identifier(self):
        """Attempts to detect the model identifier from the /v1/models endpoint."""
        print(f"Attempting to detect model identifier from: {self.models_endpoint}")
        try:
            response = requests.get(self.models_endpoint, timeout=10)
            response.raise_for_status()
            models_data = response.json()

            if models_data.get("data") and len(models_data["data"]) > 0:
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

        if not self.model_identifier:
            print("Failed to auto-detect model identifier.")
            fallback_model = app_config.MODEL_IDENTIFIER
            if fallback_model:
                print(f"Falling back to MODEL_IDENTIFIER from config: {fallback_model}")
                self.model_identifier = fallback_model
            else:
                print("Error: Could not determine model identifier. LLMClient may not function.")

    def _count_tokens_in_conversation(self, conversation_history):
        """Approximates token count by summing words in content of all messages."""
        total_tokens = 0
        for message in conversation_history:
            if isinstance(message, dict) and "content" in message and isinstance(message["content"], str):
                total_tokens += len(message.get("content", "").split())
        return total_tokens

    def _get_conversation_text_for_summary(self, conversation_history):
        """Formats conversation history into a single string for summarization."""
        text_parts = []
        for msg in conversation_history:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                # Exclude the main system prompt from being part of the text to summarize,
                # as it's the persona, not the conversation flow itself.
                # Summaries, if present (also system role), should be included.
                if msg["role"] == "system" and msg["content"] == LLMClient.DEFAULT_SYSTEM_PROMPT:
                    continue
                text_parts.append(f"{msg['role']}: {msg['content']}")
        return "\n".join(text_parts)

    def _summarize_conversation_if_needed(self, user_id):
        """Checks if conversation needs summarization and performs it using token count."""
        if user_id not in self.conversations or not self.conversations[user_id]:
            return

        # We only summarize if there's more than just the initial system prompt.
        if len(self.conversations[user_id]) <= 1 and self.conversations[user_id][0]["role"] == "system":
            return

        current_token_count = self._count_tokens_in_conversation(self.conversations[user_id])
        
        if current_token_count > LLMClient.SUMMARY_THRESHOLD_TOKENS:
            print(f"Conversation for {user_id} reached approx. {current_token_count} tokens. Triggering summarization.", flush=True)
            
            # Get text of the current conversation, excluding the primary system prompt
            conversation_to_summarize_text = self._get_conversation_text_for_summary(list(self.conversations[user_id]))

            if not conversation_to_summarize_text.strip():
                print(f"Conversation text for {user_id} (excluding main system prompt) is empty, skipping summarization.", flush=True)
                return

            summary_prompt_text = (
                f"Please provide a concise summary of the following conversation. "
                f"The summary should be approximately {LLMClient.SUMMARY_TARGET_WORD_COUNT} words long and capture the key points, decisions, and overall context. "
                f"Include physical descriptions of the characters, their personalities, and their backstories. "
                f"Focus on extracting the most important information that would be necessary to understand the conversation's progression. "
                f"Do not add any conversational fluff or introductory/concluding remarks beyond the summary itself. Just provide the summary text.\n\n"
                f"Conversation to summarize:\n{conversation_to_summarize_text}"
            )

            # Estimate max_tokens for summary generation (words * ~2 for tokens + buffer)
            summary_max_tokens = LLMClient.SUMMARY_TARGET_WORD_COUNT * 2 + 150

            summary_payload = {
                "model": self.model_identifier,
                "messages": [
                    {"role": "system", "content": "You are an expert at summarizing long conversations."},
                    {"role": "user", "content": summary_prompt_text}
                ],
                "max_tokens": summary_max_tokens,
                "temperature": 0.4,  # Lower temperature for more factual summary
            }
            headers = {"Content-Type": "application/json"}

            try:
                print(f"Sending summarization request for {user_id} to: {self.chat_endpoint}", flush=True)
                response = requests.post(self.chat_endpoint, headers=headers, json=summary_payload, timeout=180)
                response.raise_for_status()
                response_data = response.json()

                if response_data.get('choices') and len(response_data['choices']) > 0:
                    message = response_data['choices'][0].get('message')
                    if message and message.get('content'):
                        summary_text = message['content'].strip()
                        print(f"Received summary for {user_id}: {len(summary_text.split())} words.", flush=True)

                        persona_prompt_content = LLMClient.DEFAULT_SYSTEM_PROMPT
                        
                        self.conversations[user_id] = [] 
                        self.add_system_message(user_id, persona_prompt_content) 
                        
                        self.conversations[user_id].append({
                            "role": "system", 
                            "content": f"The following is a summary of the previous part of our conversation: {summary_text}"
                        })
                        new_token_count = self._count_tokens_in_conversation(self.conversations[user_id])
                        print(f"History for {user_id} replaced with persona and summary. New approx. token count: {new_token_count}", flush=True)
                        return
                    else:
                        print(f"Error: Summarization response format unexpected (no content) for {user_id}.", flush=True)
                else:
                    print(f"Error: Summarization response format unexpected (no choices) for {user_id}.", flush=True)
            except requests.exceptions.RequestException as e:
                print(f"Network error during summarization for {user_id}: {e}", flush=True)
            except Exception as e:
                print(f"Error processing summarization response for {user_id}: {e}", flush=True)
            
            print(f"Summarization failed or skipped for {user_id}. Proceeding with existing history.", flush=True)

    def send_request(self, prompt, user_id=None):
        if not self.model_identifier:
             raise RuntimeError("LLMClient cannot send request: Model identifier is not set.")

        if user_id not in self.conversations:
            self.conversations[user_id] = []
            print(f"New conversation detected for {user_id}. Adding system message.")
            self.add_system_message(user_id, LLMClient.DEFAULT_SYSTEM_PROMPT)
        
        # Attempt summarization BEFORE adding the new user prompt to the history
        self._summarize_conversation_if_needed(user_id)

        messages = self.conversations[user_id].copy()
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_identifier,
            "messages": messages,
            "max_tokens": 300, 
            "temperature": 1.2, # This is the line you had selected
        }
        headers = {"Content-Type": "application/json"}

        try:
            # --- Add this block to print the context window ---
            print(f"\n--- Context Window for LLM Request (User: {user_id}) ---", flush=True)
            print(json.dumps(payload["messages"], indent=2), flush=True)
            print(f"--- End of Context Window (User: {user_id}) ---\n", flush=True)
            # --- End of block ---

            print(f"Sending request to: {self.chat_endpoint}")
            # print(f"Payload: {json.dumps(payload, indent=2)}") # Can be verbose

            response = requests.post(self.chat_endpoint, headers=headers, json=payload)
            response.raise_for_status()
            response_data = response.json()
            # print(f"Raw Response Data: {json.dumps(response_data, indent=2)}") # Can be verbose

            if response_data.get('choices') and len(response_data['choices']) > 0:
                message = response_data['choices'][0].get('message')
                if message and message.get('content'):
                    assistant_response = message['content'].strip()

                    # Update conversation history (add user prompt that led to this response, then assistant response)
                    # The user prompt is already in 'messages' sent to LLM, but not yet in self.conversations[user_id]
                    # if summarization happened. If no summarization, it might be a duplicate.
                    # To ensure correctness, only add if not already the last message.
                    if not self.conversations[user_id] or \
                       self.conversations[user_id][-1].get("role") != "user" or \
                       self.conversations[user_id][-1].get("content") != prompt:
                        self.conversations[user_id].append({"role": "user", "content": prompt})
                    
                    self.conversations[user_id].append({"role": "assistant", "content": assistant_response})
                    
                    # Trim history by message count if it gets too long (secondary mechanism)
                    current_history_len = len(self.conversations[user_id])
                    if current_history_len > self.max_history:
                        system_messages_to_keep = []
                        non_system_messages = []
                        for msg in self.conversations[user_id]:
                            if msg["role"] == "system":
                                system_messages_to_keep.append(msg)
                            else:
                                non_system_messages.append(msg)
                        
                        num_system_messages = len(system_messages_to_keep)
                        num_non_system_to_keep = self.max_history - num_system_messages
                        if num_non_system_to_keep < 0: num_non_system_to_keep = 0
                        
                        trimmed_non_system_history = non_system_messages[-num_non_system_to_keep:]
                        self.conversations[user_id] = system_messages_to_keep + trimmed_non_system_history
                        print(f"History for {user_id} trimmed by message count to {len(self.conversations[user_id])} messages.", flush=True)

                    return assistant_response
                else:
                    raise Exception("Error: Response format unexpected. 'message' or 'content' missing.")
            else:
                raise Exception("Error: Response format unexpected. 'choices' array missing or empty.")

        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error sending request to LLM: {e}")
        except Exception as e:
            # Log the payload that caused the error for easier debugging
            print(f"Error processing LLM response. Payload was: {json.dumps(payload, indent=2)}", flush=True)
            raise Exception(f"Error processing LLM response: {e}")
    
    def reset_conversation(self, user_id):
        if user_id in self.conversations:
            self.conversations[user_id] = []
            print(f"Conversation reset for {user_id}. Re-adding system message.")
            self.add_system_message(user_id, LLMClient.DEFAULT_SYSTEM_PROMPT)
            return True
        return False
    
    def add_system_message(self, user_id, system_message):
        if user_id not in self.conversations:
            self.conversations[user_id] = []

        # Remove any existing primary system messages (content matching DEFAULT_SYSTEM_PROMPT)
        # or all system messages if this is the default system prompt being added.
        # This ensures the DEFAULT_SYSTEM_PROMPT is unique and first if it's the one being added.
        # Summaries are added with different content and are preserved unless a full reset.
        
        temp_history = []
        is_default_prompt = (system_message == LLMClient.DEFAULT_SYSTEM_PROMPT)

        if is_default_prompt: # If adding the main persona, clear all other system messages too
            for msg in self.conversations[user_id]:
                if msg["role"] != "system":
                    temp_history.append(msg)
            self.conversations[user_id] = [{"role": "system", "content": system_message}] + temp_history
        else: # If adding a different system message (e.g. a summary, though not typical via this func)
            # Ensure it's not a duplicate of an existing system message
            if not any(msg["role"] == "system" and msg["content"] == system_message for msg in self.conversations[user_id]):
                 self.conversations[user_id].insert(0, {"role": "system", "content": system_message})
        
        # Ensure the primary DEFAULT_SYSTEM_PROMPT is always first if present
        final_history = []
        default_prompt_message = None
        other_system_messages = []
        non_system_messages_history = []

        for msg in self.conversations[user_id]:
            if msg["role"] == "system":
                if msg["content"] == LLMClient.DEFAULT_SYSTEM_PROMPT:
                    if default_prompt_message is None: # Keep only the first instance
                        default_prompt_message = msg
                else:
                    other_system_messages.append(msg) # Other system messages (like summaries)
            else:
                non_system_messages_history.append(msg)
        
        if default_prompt_message:
            final_history.append(default_prompt_message)
        final_history.extend(other_system_messages)
        final_history.extend(non_system_messages_history)
        self.conversations[user_id] = final_history
        
        return True