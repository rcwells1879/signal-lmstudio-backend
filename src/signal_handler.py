import subprocess
import json
import threading
import time
import socket
import select # For non-blocking socket reads
import queue # For thread-safe communication
from .config import SIGNAL_CLI_PATH, YOUR_SIGNAL_NUMBER
from .llm_client import LLMClient

# --- Globals for JSON-RPC ---
llm_client = None
signal_cli_process = None
signal_socket = None
listener_thread = None
send_queue = queue.Queue() # Queue for messages to send
receive_buffer = "" # Buffer for incoming socket data
request_id_counter = 0 # Simple counter for JSON-RPC request IDs
running = True # Flag to control loops
JSON_RPC_PORT = 7583 # Default port for signal-cli jsonRpc, adjust if needed
# --- End Globals ---

def start_signal_cli_jsonrpc():
    """Starts the signal-cli process in jsonRpc mode."""
    global signal_cli_process, running
    command = [
        SIGNAL_CLI_PATH,
        "-u", YOUR_SIGNAL_NUMBER,
        # Use the 'daemon' command, not 'jsonRpc' for socket/tcp mode
        "daemon",
        # Use the --tcp flag with the host and port
        "--tcp", f"127.0.0.1:{JSON_RPC_PORT}"
    ]
    print(f"Starting signal-cli daemon for JSON-RPC on TCP for {YOUR_SIGNAL_NUMBER}...") # Updated print
    print(f"Command: {' '.join(command)}")
    try:
        signal_cli_process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE, # Keep stdin open
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='ignore',
            bufsize=1
        )
        # Give signal-cli a moment to start
        time.sleep(3)
        if signal_cli_process.poll() is not None:
             stderr_output = signal_cli_process.stderr.read()
             print(f"signal-cli failed to start! Exit code: {signal_cli_process.poll()}")
             print(f"Stderr:\n{stderr_output}")
             running = False
             return False
        print("signal-cli process started.")
        return True
    except FileNotFoundError:
        print(f"Error: signal-cli not found at '{SIGNAL_CLI_PATH}'. Cannot start JSON-RPC mode.")
        running = False
        return False
    except Exception as e:
        print(f"An error occurred starting signal-cli: {e}")
        running = False
        return False

def connect_socket():
    """Connects to the signal-cli JSON-RPC socket."""
    global signal_socket, running
    print(f"Attempting to connect to signal-cli socket at 127.0.0.1:{JSON_RPC_PORT}...")
    try:
        signal_socket = socket.create_connection(("127.0.0.1", JSON_RPC_PORT), timeout=10)
        signal_socket.setblocking(False) # Use non-blocking socket
        print("Successfully connected to signal-cli socket.")
        return True
    except socket.timeout:
        print("Error: Connection to signal-cli socket timed out.")
        running = False
        return False
    except ConnectionRefusedError:
        print("Error: Connection to signal-cli socket refused. Is signal-cli running in jsonRpc mode?")
        running = False
        return False
    except Exception as e:
        print(f"An error occurred connecting to socket: {e}")
        running = False
        return False

def process_incoming_message(data):
    """Processes a received message JSON from signal-cli."""
    global llm_client
    print(f"--- Entering process_incoming_message ---")
    try:
        envelope = data.get('params', {}).get('envelope', {})
        if not envelope:
            print("process_incoming_message: No envelope found.")
            return

        sender_identifier = envelope.get('sourceUuid') or envelope.get('sourceNumber')
        sender_number = envelope.get('sourceNumber')
        print(f"process_incoming_message: Sender identified as {sender_identifier}")

        message_body = None
        timestamp = None
        recipient_for_reply = None # Determine who to reply to

        # --- MODIFIED LOGIC ---
        # Case 1: Regular incoming message from another contact
        if envelope.get('dataMessage'):
            # Check if sender is self (e.g., message from another linked device NOT intended for bot)
            # We generally want to ignore these unless explicitly handled below.
            if sender_identifier == YOUR_SIGNAL_NUMBER or sender_number == YOUR_SIGNAL_NUMBER:
                 print(f"process_incoming_message: Ignoring regular dataMessage from self ({sender_identifier})")
                 return # Ignore regular messages from self

            print("process_incoming_message: Found dataMessage (from external contact).")
            message_body = envelope['dataMessage'].get('message')
            timestamp = envelope['dataMessage'].get('timestamp')
            recipient_for_reply = sender_identifier # Reply to the sender

        # Case 2: Sync message (potentially a message sent *to* self)
        elif envelope.get('syncMessage'):
            print("process_incoming_message: Found syncMessage.")
            sync_message = envelope['syncMessage']
            # Check if it's a "sent" message sync (message you sent from a device)
            if sync_message.get('sentMessage'):
                sent_message = sync_message['sentMessage']
                destination_uuid = sent_message.get('destinationUuid')
                destination_number = sent_message.get('destinationNumber')
                # IMPORTANT: Check if the message was sent TO your bot's number
                if destination_uuid == YOUR_SIGNAL_NUMBER or destination_number == YOUR_SIGNAL_NUMBER:
                    print("process_incoming_message: Found sync'd 'sent' message addressed to self (potential bot command).")
                    message_body = sent_message.get('message')
                    timestamp = sent_message.get('timestamp')
                    # Reply to yourself USING THE UUID (sender_identifier)
                    recipient_for_reply = sender_identifier # NEW - Use UUID for Note to Self replies
                    print(f"process_incoming_message: Set recipient_for_reply to UUID: {recipient_for_reply}") # Optional: Add log
                else:
                    print(f"process_incoming_message: Ignoring sync'd 'sent' message not addressed to self (sent to {destination_number or destination_uuid}).")
                    return # Ignore messages you sent to others
            else:
                 print("process_incoming_message: Ignoring non-'sent' sync message.")
                 return # Ignore other sync types (read receipts, etc.)

        # Case 3: Typing indicator
        elif envelope.get('typingMessage'):
            print(f"process_incoming_message: Ignoring typing message from {sender_identifier}")
            return # Ignore typing

        # Case 4: Receipt message
        elif envelope.get('receiptMessage'):
            print(f"process_incoming_message: Ignoring receipt message from {sender_identifier}")
            return # Ignore receipts

        # Case 5: Unhandled type
        else:
            print(f"process_incoming_message: Envelope type not handled: {list(envelope.keys())}")
            return # Ignore other types

        # --- LLM Interaction (if message found and recipient determined) ---
        if message_body and recipient_for_reply:
            print(f"Processing message: '{message_body}' from {sender_identifier or 'self'} at {timestamp}. Replying to: {recipient_for_reply}")

            if llm_client:
                try:
                    print(f"Sending prompt to LLM: '{message_body}'")
                    # Pass sender_identifier as user_id to maintain conversation context
                    llm_response = llm_client.send_request(message_body, user_id=sender_identifier)
                    print(f"Received LLM response: '{llm_response}'")
                    # Queue the response to be sent
                    send_signal_message(recipient_for_reply, llm_response)
                except Exception as e:
                    print(f"Error during LLM request or queuing Signal response: {e}")
            else:
                print("LLM client not initialized. Cannot process message.")
        elif message_body is None:
             print("process_incoming_message: No message body found to process.")

    except Exception as e:
        print(f"Error processing incoming message JSON: {e}\nData: {data}")
    finally:
        print(f"--- Exiting process_incoming_message ---")

def handle_socket_data():
    """Reads data from socket, parses JSON, and processes messages."""
    global receive_buffer, running
    print("--- handle_socket_data loop started ---")
    while running:
        # print("--- Top of handle_socket_data loop ---") # Optional: Very verbose
        ready_to_read = []
        try:
            # Check if socket is readable
            # print("--- Checking socket readability (select)... ---") # Optional: Verbose
            ready_to_read, _, _ = select.select([signal_socket], [], [], 0.1) # 0.1s timeout
        except Exception as e:
            print(f"Error during select: {e}")
            running = False
            break

        if ready_to_read:
            print("--- Socket is ready to read ---") # ADDED
            try:
                data = signal_socket.recv(4096) # Read up to 4KB
                if not data:
                    print("Socket connection closed by signal-cli.")
                    running = False
                    break
                print(f"--- Received {len(data)} bytes from socket ---")
                decoded_data = data.decode('utf-8', errors='ignore')
                print(f"--- Decoded data chunk: {decoded_data[:200]}... ---") # ADDED
                receive_buffer += decoded_data
                print(f"--- Buffer size after adding: {len(receive_buffer)} ---") # ADDED

                # Process complete JSON messages (newline-delimited)
                print("--- Processing buffer for newline chars ---") # ADDED
                while '\n' in receive_buffer:
                    print(f"--- Found newline in buffer. Current buffer head: {receive_buffer[:100]}... ---") # ADDED
                    message_json, receive_buffer = receive_buffer.split('\n', 1)
                    print(f"--- Split message_json: {message_json[:100]}... | Remaining buffer head: {receive_buffer[:100]}... ---") # ADDED
                    if message_json:
                        print(f"--- Processing JSON line: {message_json[:200]}... ---")
                        try:
                            message_data = json.loads(message_json)
                            if message_data.get('method') == 'receive':
                                process_incoming_message(message_data)
                            else:
                                print(f"--- Received JSON is not a 'receive' method: {message_data.get('method')} (ID: {message_data.get('id')}) ---") # ADDED ID
                        except json.JSONDecodeError:
                            print(f"Error decoding JSON: {message_json}")
                        except Exception as e:
                            print(f"Error processing JSON message: {e}\nJSON: {message_json}")
                    else:
                        print("--- Split resulted in empty message_json (likely consecutive newlines) ---") # ADDED
                print(f"--- Finished processing buffer for newlines. Remaining buffer size: {len(receive_buffer)} ---") # ADDED

            except BlockingIOError:
                print("--- BlockingIOError during recv (should not happen after select?) ---") # ADDED
                pass
            except ConnectionResetError:
                 print("Socket connection reset by signal-cli.")
                 running = False
                 break
            except Exception as e:
                print(f"Error reading from socket or processing buffer: {e}") # Changed error message scope
                running = False
                break
        # else: # Optional: Log when socket is not ready
            # print("--- Socket not ready to read ---")

        # Small sleep to prevent high CPU usage in loop if socket isn't readable often
        time.sleep(0.05)
    print("--- handle_socket_data loop finished ---")


def handle_send_queue():
    """Sends messages from the queue over the socket."""
    global request_id_counter, running
    while running:
        try:
            # Wait for a message in the queue (with timeout to allow checking 'running' flag)
            recipient, message = send_queue.get(timeout=0.5)

            request_id_counter += 1
            request_json = {
                "jsonrpc": "2.0",
                "method": "send",
                "params": {
                    # Use 'recipient' for UUIDs, 'number' for phone numbers
                    # Heuristic: Check if recipient looks like a phone number
                    ("number" if recipient.startswith('+') else "recipient"): recipient,
                    "message": message
                    # Add other params like attachments if needed
                },
                "id": request_id_counter
            }

            try:
                json_string = json.dumps(request_json) + '\n'
                print(f"Sending JSON-RPC request ID {request_id_counter} to {recipient}: {message[:50]}...")
                signal_socket.sendall(json_string.encode('utf-8'))
                # print(f"Sent JSON: {json_string.strip()}") # Debug print
                send_queue.task_done() # Mark task as complete
            except BrokenPipeError:
                 print("Error sending: Socket connection broken.")
                 running = False # Stop loops
                 break
            except Exception as e:
                print(f"Error sending JSON-RPC request: {e}")
                # Optionally, re-queue the message or handle error

        except queue.Empty:
            # Queue is empty, loop continues
            continue
        except Exception as e:
            print(f"Error in send queue handler: {e}")


def send_signal_message(recipient, message):
    """Queues a message to be sent via JSON-RPC."""
    if not isinstance(recipient, str):
        print(f"Error: Recipient must be a string, got {type(recipient)}")
        return
    send_queue.put((recipient, message))


def json_rpc_listener_main():
    """Main function to start signal-cli, connect socket, and handle I/O."""
    global running
    running = True # Reset running flag

    if not start_signal_cli_jsonrpc():
        return # Exit if signal-cli failed to start

    if not connect_socket():
        # Attempt to clean up process if socket connection failed
        if signal_cli_process:
            signal_cli_process.terminate()
        return # Exit if socket connection failed

    # Start thread to handle sending messages from the queue
    sender_thread = threading.Thread(target=handle_send_queue, daemon=True)
    sender_thread.start()

    # Start handling socket data in this thread
    handle_socket_data()

    # --- Cleanup ---
    print("Listener loop stopped. Cleaning up...")
    if signal_socket:
        try:
            signal_socket.close()
            print("Socket closed.")
        except Exception as e:
            print(f"Error closing socket: {e}")
    if signal_cli_process and signal_cli_process.poll() is None:
        try:
            signal_cli_process.terminate() # Ask nicely first
            signal_cli_process.wait(timeout=5) # Wait a bit
            print("signal-cli process terminated.")
        except subprocess.TimeoutExpired:
            print("signal-cli did not terminate gracefully, killing.")
            signal_cli_process.kill() # Force kill
        except Exception as e:
            print(f"Error terminating signal-cli process: {e}")
    print("JSON-RPC listener finished.")


def start_listener_thread(llm_client_instance):
    """Starts the JSON-RPC listener in a separate thread."""
    global llm_client, listener_thread
    llm_client = llm_client_instance

    if listener_thread and listener_thread.is_alive():
        print("Listener thread already running.")
        return listener_thread

    print("Initializing Signal JSON-RPC listener thread...")
    listener_thread = threading.Thread(target=json_rpc_listener_main, daemon=True)
    listener_thread.start()
    print("Signal JSON-RPC listener thread started.")
    return listener_thread

def stop_listener():
    """Stops the listener thread and cleans up."""
    global running
    print("Stopping listener...")
    running = False # Signal loops to stop
    # Wait for threads? The main listener thread should exit when socket closes or running is False.
    # The sender thread is daemon, so it will exit when main thread exits.
    # Cleanup happens in json_rpc_listener_main's finally block


if __name__ == '__main__':
    print("Running signal_handler.py directly for testing JSON-RPC mode...")
    from .config import API_URL, MODEL_IDENTIFIER
    from .llm_client import LLMClient

    test_llm_client = LLMClient(API_URL, MODEL_IDENTIFIER)
    start_listener_thread(test_llm_client)

    try:
        # Keep main thread alive, listener runs in background
        while running and listener_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Stopping...")
    finally:
        stop_listener()
        print("Test finished.")