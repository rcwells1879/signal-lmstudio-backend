import requests
import json

class LLMClient:
    def __init__(self, api_url, model_identifier, max_history=50):
        # Ensure the base URL doesn't end with a slash, then add the specific endpoint
        self.base_api_url = api_url.rstrip('/')
        self.chat_endpoint = f"{self.base_api_url}/v1/chat/completions"
        self.model_identifier = model_identifier
        self.max_history = max_history  # Maximum number of messages to keep in history per user
        self.conversations = {}  # Dictionary to store conversations by user ID
        print(f"LLMClient initialized. Using endpoint: {self.chat_endpoint}")

    def send_request(self, prompt, user_id=None):
        """
        Send a request to the LLM with conversation history if available
        
        Args:
            prompt (str): The user's message
            user_id (str): Identifier for the conversation (Signal UUID or number)
        
        Returns:
            str: The model's response
        """
        # Initialize or retrieve conversation history
        if user_id not in self.conversations:
            self.conversations[user_id] = []
        
        # Prepare messages with history
        messages = self.conversations[user_id].copy()
        # Add the new user message
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model_identifier,
            "messages": messages,
            "max_tokens": 300,
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
                    
                    # Update conversation history with both the user message and assistant response
                    self.conversations[user_id].append({"role": "user", "content": prompt})
                    self.conversations[user_id].append({"role": "assistant", "content": assistant_response})
                    
                    # Trim history if it gets too long
                    if len(self.conversations[user_id]) > self.max_history:
                        # Remove oldest messages but keep the first system message if present
                        has_system = False
                        if self.conversations[user_id] and self.conversations[user_id][0]["role"] == "system":
                            has_system = True
                        
                        if has_system:
                            system_msg = self.conversations[user_id][0]
                            self.conversations[user_id] = self.conversations[user_id][-(self.max_history-1):]
                            self.conversations[user_id].insert(0, system_msg)
                        else:
                            self.conversations[user_id] = self.conversations[user_id][-self.max_history:]
                    
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