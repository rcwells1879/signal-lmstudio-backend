import time
import signal # Import signal module for handling termination signals

# Import necessary components from your project
from .config import API_URL, MODEL_IDENTIFIER
from .llm_client import LLMClient
from .signal_handler import start_listener_thread, stop_listener, running # Import 'running' flag

from flask import Flask, request, jsonify

app = Flask(__name__)
llm_client = None

def shutdown_handler(signum, frame):
    """Handles shutdown signals gracefully."""
    print(f"\nReceived signal {signum}. Initiating shutdown...")
    stop_listener()
    # The main loop will exit because 'running' becomes False

@app.route('/message', methods=['POST'])
def handle_message():
    data = request.json
    response = signal_handler.process_message(data)
    return jsonify(response)

if __name__ == '__main__':
    print("Starting Signal LMStudio Backend...")

    # Initialize the LLM Client
    try:
        llm_client = LLMClient(API_URL, MODEL_IDENTIFIER)
    except Exception as e:
        print(f"Failed to initialize LLM Client: {e}")
        exit(1) # Exit if LLM client fails

    # Start the Signal listener thread
    listener_thread = start_listener_thread(llm_client)
    if not listener_thread or not listener_thread.is_alive():
        print("Failed to start the Signal listener thread. Exiting.")
        exit(1)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, shutdown_handler)  # Handle Ctrl+C
    signal.signal(signal.SIGTERM, shutdown_handler) # Handle termination signals

    print("Application started. Signal listener is running.")
    print("Press Ctrl+C to stop.")

    try:
        # Keep the main thread alive while the listener runs
        # Check the 'running' flag from signal_handler
        while running and listener_thread.is_alive():
            time.sleep(1) # Sleep to prevent busy-waiting
    except Exception as e:
        print(f"An unexpected error occurred in the main loop: {e}")
    finally:
        # Ensure cleanup happens even if the loop exits unexpectedly
        if running: # If stop_listener wasn't called by signal handler
            print("Main loop exited unexpectedly. Initiating cleanup...")
            stop_listener()
        print("Application finished.")
