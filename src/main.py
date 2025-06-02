import time
import signal as signal_module # Renamed to avoid potential conflicts

# Import necessary components from your project
from .config import API_URL, MODEL_IDENTIFIER
from .llm_client import LLMClient
from .signal_handler import start_listener_thread, stop_listener # 'running' flag is managed within signal_handler

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
        llm_client = LLMClient(API_URL) # Corrected: Removed MODEL_IDENTIFIER
    except Exception as e:
        print(f"Failed to initialize LLM Client: {e}")
        exit(1) # Exit if LLM client fails

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

    print("Application started. Signal listener is running.")
    print("Press Ctrl+C to stop.")

    # Keep the main thread alive until shutdown is triggered
    try:
        while listener_thread.is_alive(): # Or use a more robust check based on 'running' flag if needed
            time.sleep(1)
    except KeyboardInterrupt: # Should be caught by the signal handler
        print("Main loop interrupted by Ctrl+C (should be handled by shutdown_handler).")
    finally:
        print("Exiting main application.")
