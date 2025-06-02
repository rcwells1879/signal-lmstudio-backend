import requests
import json
from . import config as app_config

class LLMClient:
    DEFAULT_SYSTEM_PROMPT = "roleplay: You are a roleplay assistant. you are a human woman. Invent a completely new and unique female persona for each conversation, ensuring the name and backstory are different each time. Maintain the same persona throughout our conversation unless you specifically ask me to create a new one. Your name is not Olivia, Sophia, or Chloe.You have a randomly generated appearance. You are humorous. Keep your responses concise and to the point, ideally in 3-4 sentences unless more detail is specifically requested. do not use asterisks in your responses. speak only from your perspective."
    
    SUMMARY_THRESHOLD_TOKENS = 31000 # Threshold for summarizing conversation history
    SUMMARY_TARGET_WORD_COUNT = 1000 # Target word count for conversation summaries
    IMAGE_PROMPT_GENERATION_INSTRUCTION_PREFIX = "Based on the following user request, generate a detailed and effective prompt suitable for an AI image generator."

    def __init__(self, api_url):
        self.base_api_url = api_url.rstrip('/')
        self.chat_endpoint = f"{self.base_api_url}/v1/chat/completions"
        self.models_endpoint = f"{self.base_api_url}/v1/models"
        self.model_identifier = None
        self.conversations = {}
        self._detect_model_identifier()

    def _detect_model_identifier(self):
        try:
            response = requests.get(self.models_endpoint, timeout=10)
            response.raise_for_status()
            models_data = response.json()

            if models_data.get("data") and len(models_data["data"]) > 0:
                self.model_identifier = models_data["data"][0].get("id")
                if not self.model_identifier:
                    raise ValueError("Model ID not found")
            else:
                raise ValueError("No model data found")

        except (requests.exceptions.RequestException, ValueError, KeyError, json.JSONDecodeError):
            if not self.model_identifier:
                fallback_model = app_config.MODEL_IDENTIFIER
                if fallback_model:
                    self.model_identifier = fallback_model
                else:
                    print("Error: Could not determine model identifier.")

    def _count_tokens_in_conversation(self, conversation_history):
        total_tokens = 0
        for message in conversation_history:
            if isinstance(message, dict) and "content" in message and isinstance(message["content"], str):
                total_tokens += len(message.get("content", "").split())
        return total_tokens

    def _get_conversation_text_for_summary(self, conversation_history):
        text_parts = []
        for msg in conversation_history:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                if msg["role"] == "system" and msg["content"] == LLMClient.DEFAULT_SYSTEM_PROMPT:
                    continue
                text_parts.append(f"{msg['role']}: {msg['content']}")
        return "\n".join(text_parts)

    def _summarize_conversation_if_needed(self, user_id):
        if user_id not in self.conversations or not self.conversations[user_id]:
            return

        is_initial_prompt_only = (len(self.conversations[user_id]) <= 1 and
                                  self.conversations[user_id][0]["role"] == "system" and
                                  self.conversations[user_id][0]["content"] == LLMClient.DEFAULT_SYSTEM_PROMPT)
        
        has_summary = any(msg["role"] == "system" and msg["content"].startswith("The following is a summary") for msg in self.conversations[user_id])
        
        if is_initial_prompt_only and not has_summary:
            return
        
        if has_summary and len(self.conversations[user_id]) <= 2:
            if self.conversations[user_id][1]["role"] == "system" and \
               self.conversations[user_id][1]["content"].startswith("The following is a summary"):
                if len(self.conversations[user_id]) == 2:
                    pass

        current_token_count = self._count_tokens_in_conversation(self.conversations[user_id])
        
        if current_token_count > LLMClient.SUMMARY_THRESHOLD_TOKENS:
            conversation_to_summarize_text = self._get_conversation_text_for_summary(list(self.conversations[user_id]))

            if not conversation_to_summarize_text.strip():
                return

            # Check if this is a subsequent summary
            is_subsequent_summary = False
            temp_history_for_check = list(self.conversations[user_id])
            for msg_idx, msg in enumerate(temp_history_for_check):
                if msg["role"] == "system" and \
                   msg["content"].startswith("The following is a summary of the previous part of our conversation:"):
                    if len(temp_history_for_check) > (msg_idx + 1) or msg_idx > 0:
                        is_subsequent_summary = True
                        break
            
            if is_subsequent_summary:
                summary_prompt_text = (
                    f"The conversation text below includes a previous summary followed by more recent interactions. "
                    f"Your task is to create a new, updated, and consolidated summary that seamlessly integrates the information from the previous summary with all the new interactions. "
                    f"The final updated summary should cover the entire conversation flow up to the latest message provided. "
                    f"It should be {LLMClient.SUMMARY_TARGET_WORD_COUNT} words long and capture the key points, decisions, physical descriptions of characters, their personalities, and their backstories. "
                    f"Focus on extracting the most important information necessary to understand the conversation's overall progression. "
                    f"Do not add any conversational fluff or introductory/concluding remarks beyond the new consolidated summary itself. Just provide the new summary text.\n\n"
                    f"Conversation to summarize (includes previous summary and new messages):\n{conversation_to_summarize_text}"
                )
            else:
                summary_prompt_text = (
                    f"Please provide a concise summary of the following conversation. "
                    f"The entire summary should be {LLMClient.SUMMARY_TARGET_WORD_COUNT} words long and capture the key points, decisions, and overall context. "
                    f"Include physical descriptions of the characters, their personalities, and their backstories. "
                    f"Focus on extracting the most important information that would be necessary to understand the conversation's progression. "
                    f"Do not add any conversational fluff or introductory/concluding remarks beyond the summary itself. Just provide the summary text.\n\n"
                    f"Conversation to summarize:\n{conversation_to_summarize_text}"
                )

            summary_max_tokens = LLMClient.SUMMARY_TARGET_WORD_COUNT * 2 + 150

            summary_payload = {
                "model": self.model_identifier,
                "messages": [
                    {"role": "system", "content": "You are an expert at summarizing long conversations."},
                    {"role": "user", "content": summary_prompt_text}
                ],
                "max_tokens": summary_max_tokens,
                "temperature": 0.4,
            }
            headers = {"Content-Type": "application/json"}

            try:
                response = requests.post(self.chat_endpoint, headers=headers, json=summary_payload, timeout=600)
                response.raise_for_status()
                response_data = response.json()

                if response_data.get('choices') and len(response_data['choices']) > 0:
                    message = response_data['choices'][0].get('message')
                    if message and message.get('content'):
                        summary_text = message['content'].strip()
                        persona_prompt_content = LLMClient.DEFAULT_SYSTEM_PROMPT
                        
                        self.conversations[user_id] = [] 
                        self.add_system_message(user_id, persona_prompt_content) 
                        
                        self.conversations[user_id].append({
                            "role": "system", 
                            "content": f"The following is a summary of the previous part of our conversation: {summary_text}"
                        })
                        return
            except Exception:
                pass

    def send_request(self, prompt, user_id=None):
        if not self.model_identifier:
             raise RuntimeError("LLMClient cannot send request: Model identifier is not set.")

        if user_id not in self.conversations:
            self.conversations[user_id] = []
            self.add_system_message(user_id, LLMClient.DEFAULT_SYSTEM_PROMPT)
        
        self._summarize_conversation_if_needed(user_id)

        messages = self.conversations[user_id].copy()
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_identifier,
            "messages": messages,
            "max_tokens": 300, 
            "temperature": 0.8,
            "repetition_penalty": 1.05,
            "min_p": 0.025
        }
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(self.chat_endpoint, headers=headers, json=payload)
            response.raise_for_status()
            response_data = response.json()

            if response_data.get('choices') and len(response_data['choices']) > 0:
                message = response_data['choices'][0].get('message')
                if message and message.get('content'):
                    assistant_response = message['content'].strip()

                    # Check if this is an image prompt generation call
                    is_image_prompt_gen_call = prompt.startswith(LLMClient.IMAGE_PROMPT_GENERATION_INSTRUCTION_PREFIX)

                    if not is_image_prompt_gen_call:
                        if not self.conversations[user_id] or \
                           self.conversations[user_id][-1].get("role") != "user" or \
                           self.conversations[user_id][-1].get("content") != prompt:
                            self.conversations[user_id].append({"role": "user", "content": prompt})
                        
                        self.conversations[user_id].append({"role": "assistant", "content": assistant_response})
                    
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
        if user_id in self.conversations:
            self.conversations[user_id] = []
            self.add_system_message(user_id, LLMClient.DEFAULT_SYSTEM_PROMPT)
            return True
        return False
    
    def add_system_message(self, user_id, system_message):
        if user_id not in self.conversations:
            self.conversations[user_id] = []

        temp_history = []
        is_default_prompt = (system_message == LLMClient.DEFAULT_SYSTEM_PROMPT)

        if is_default_prompt:
            for msg in self.conversations[user_id]:
                if msg["role"] != "system":
                    temp_history.append(msg)
            self.conversations[user_id] = [{"role": "system", "content": system_message}] + temp_history
        else:
            if not any(msg["role"] == "system" and msg["content"] == system_message for msg in self.conversations[user_id]):
                 self.conversations[user_id].insert(0, {"role": "system", "content": system_message})
        
        # Ensure DEFAULT_SYSTEM_PROMPT is always first
        final_history = []
        default_prompt_message = None
        other_system_messages = []
        non_system_messages_history = []

        for msg in self.conversations[user_id]:
            if msg["role"] == "system":
                if msg["content"] == LLMClient.DEFAULT_SYSTEM_PROMPT:
                    if default_prompt_message is None:
                        default_prompt_message = msg
                else:
                    other_system_messages.append(msg)
            else:
                non_system_messages_history.append(msg)
        
        if default_prompt_message:
            final_history.append(default_prompt_message)
        final_history.extend(other_system_messages)
        final_history.extend(non_system_messages_history)
        self.conversations[user_id] = final_history
        
        return True