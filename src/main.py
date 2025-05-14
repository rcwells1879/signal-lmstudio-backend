import time
<<<<<<< HEAD
import signal as signal_module # Renamed to avoid potential conflicts

# Import necessary components from your project
from .config import API_URL, MODEL_IDENTIFIER
from .llm_client import LLMClient
from .signal_handler import start_listener_thread, stop_listener # 'running' flag is managed within signal_handler
=======
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
>>>>>>> ad1f17e1352c6da3380c1a89c04735f759837ca0

# Global variable to hold the LLM client instance
llm_client = None

def shutdown_handler(signum, frame):
    """Handles shutdown signals gracefully."""
    print(f"\nReceived signal {signum}. Initiating shutdown...")
    stop_listener() # This will now also handle terminating signal-cli
    # The main loop (if any) or script will exit after this

if __name__ == '__main__':
    print("Starting Signal LMStudio Backend...")

    # Initialize the LLM Client
    try:
        llm_client = LLMClient(API_URL, MODEL_IDENTIFIER)
    except Exception as e:
        print(f"Failed to initialize LLM Client: {e}")
        exit(1) # Exit if LLM client fails

<<<<<<< HEAD
    # Start the Signal listener thread (which also starts signal-cli)
    listener_thread = start_listener_thread(llm_client)
    if not listener_thread or not listener_thread.is_alive():
        print("Failed to start the Signal listener thread (or signal-cli). Exiting.")
        # Ensure signal-cli is stopped if it partially started
        stop_listener()
        exit(1)

    # Register signal handlers for graceful shutdown
    signal_module.signal(signal_module.SIGINT, shutdown_handler)  # Handle Ctrl+C
    signal_module.signal(signal_module.SIGTERM, shutdown_handler) # Handle termination signals
=======
    # Start the Signal listener thread
    listener_thread = start_listener_thread(llm_client)
    if not listener_thread or not listener_thread.is_alive():
        print("Failed to start the Signal listener thread. Exiting.")
        exit(1)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, shutdown_handler)  # Handle Ctrl+C
    signal.signal(signal.SIGTERM, shutdown_handler) # Handle termination signals
>>>>>>> ad1f17e1352c6da3380c1a89c04735f759837ca0

    print("Application started. Signal listener is running.")
    print("Press Ctrl+C to stop.")

<<<<<<< HEAD
    # Keep the main thread alive until shutdown is triggered
    try:
        while listener_thread.is_alive(): # Or use a more robust check based on 'running' flag if needed
            time.sleep(1)
    except KeyboardInterrupt: # Should be caught by the signal handler
        print("Main loop interrupted by Ctrl+C (should be handled by shutdown_handler).")
    finally:
        print("Exiting main application.")
=======
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
>>>>>>> ad1f17e1352c6da3380c1a89c04735f759837ca0
