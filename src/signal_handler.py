import subprocess
import json
import threading
import time
import socket
import select # For non-blocking socket reads
import queue # For thread-safe communication
import os # Needed for image cleanup path check
import signal as os_signal # Added to avoid conflict with signal module in main.py

from .config import SIGNAL_CLI_PATH, YOUR_SIGNAL_NUMBER, SIGNAL_DAEMON_ADDRESS, JSON_RPC_PORT
from .llm_client import LLMClient
from .image_generator import generate_image

# --- Globals ---
llm_client_global = None # Renamed to avoid conflict with module-level llm_client
signal_cli_process = None
signal_socket = None
listener_thread_global = None # Renamed
sender_thread_global = None  # Added
signal_cli_stdout_thread = None # Added
signal_cli_stderr_thread = None # Added

send_queue = queue.Queue()
receive_buffer = ""
request_id_counter = 0
running = True
# --- End Globals ---

def log_stream(stream, prefix, stop_event):
    """Reads and prints lines from a stream until stop_event is set."""
    try:
        for line in iter(stream.readline, ''):
            if stop_event.is_set() and not line: # Check stop event and if stream is truly empty
                break
            if line:
                print(f"[{prefix}] {line.strip()}", flush=True)
            elif stop_event.is_set(): # If stop_event is set and line is empty, break
                break
            else: # If line is empty but stop_event not set, stream might just be slow
                time.sleep(0.01) # Small sleep to avoid busy-waiting on an empty line
        stream.close()
    except ValueError: # Handle "I/O operation on closed file"
        print(f"[{prefix}] Stream closed.", flush=True)
    except Exception as e:
        print(f"[{prefix}] Error reading stream: {e}", flush=True)
    finally:
        print(f"[{prefix}] Logging thread finished.", flush=True)


def start_signal_cli_daemon():
    """Starts the signal-cli daemon process and threads to log its output."""
    global signal_cli_process, signal_cli_stdout_thread, signal_cli_stderr_thread, running
    
    # Event to signal log_stream threads to stop
    log_stop_event = threading.Event()

    command = [
        SIGNAL_CLI_PATH,
        "-u", YOUR_SIGNAL_NUMBER,
        "daemon",
        "--tcp", SIGNAL_DAEMON_ADDRESS # Use the full address from config
    ]
    print(f"Starting signal-cli daemon: {' '.join(command)}", flush=True)
    try:
        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        signal_cli_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, # Explicitly set stdin
            text=True,
            encoding='utf-8',
            errors='ignore',
            bufsize=1, # Line buffered
            creationflags=creationflags
        )
        print(f"signal-cli daemon process started with PID: {signal_cli_process.pid}", flush=True)

        # Start threads to log stdout and stderr from signal-cli
        signal_cli_stdout_thread = threading.Thread(
            target=log_stream,
            args=(signal_cli_process.stdout, "signal-cli-out", log_stop_event),
            daemon=True
        )
        signal_cli_stderr_thread = threading.Thread(
            target=log_stream,
            args=(signal_cli_process.stderr, "signal-cli-err", log_stop_event),
            daemon=True
        )
        signal_cli_stdout_thread.start()
        signal_cli_stderr_thread.start()

        time.sleep(5) # Give signal-cli time to initialize

        if signal_cli_process.poll() is not None:
            print(f"signal-cli failed to start or terminated prematurely. Return code: {signal_cli_process.returncode}", flush=True)
            log_stop_event.set() # Signal logging threads to stop
            return False
        return True
    except FileNotFoundError:
        print(f"Error: signal-cli executable not found at {SIGNAL_CLI_PATH}", flush=True)
        running = False
        return False
    except Exception as e:
        print(f"Error starting signal-cli daemon: {e}", flush=True)
        running = False
        return False

def connect_socket_to_daemon():
    """Connects to the running signal-cli daemon."""
    global signal_socket, running
    host, port_str = SIGNAL_DAEMON_ADDRESS.split(':')
    port = int(port_str)
    print(f"Attempting to connect to signal-cli daemon at {host}:{port}...", flush=True)
    try:
        signal_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        signal_socket.connect((host, port))
        signal_socket.setblocking(False) # Important for select
        print("Successfully connected to signal-cli daemon.", flush=True)
        return True
    except socket.timeout:
        print(f"Error: Connection to signal-cli daemon at {SIGNAL_DAEMON_ADDRESS} timed out.", flush=True)
    except ConnectionRefusedError:
        print(f"Error: Connection to signal-cli daemon at {SIGNAL_DAEMON_ADDRESS} refused.", flush=True)
    except Exception as e:
        print(f"An error occurred connecting to signal-cli daemon: {e}", flush=True)
    
    running = False # If connection fails, stop
    return False

# process_incoming_message function remains largely the same
# Ensure llm_client is used as llm_client_global if it's passed from main
def process_incoming_message(data):
    """Processes a received message JSON from signal-cli."""
    global llm_client_global # Use the renamed global
    print(f"--- Entering process_incoming_message ---", flush=True)
    try:
        envelope = data.get('params', {}).get('envelope', {})
        if not envelope:
            print("process_incoming_message: No envelope found.", flush=True)
            return

        sender_identifier = envelope.get('sourceUuid') or envelope.get('sourceNumber')
        sender_number = envelope.get('sourceNumber')
        # It's crucial to use YOUR_SIGNAL_NUMBER from config here
        # Ensure YOUR_SIGNAL_NUMBER is correctly loaded and accessible
        
        print(f"process_incoming_message: Sender identified as {sender_identifier}", flush=True)

        message_body = None
        # timestamp = None # timestamp variable was unused
        recipient_for_reply = None 

        if envelope.get('dataMessage'):
            # Check if the message is from self by comparing source with YOUR_SIGNAL_NUMBER
            # This logic might need adjustment if YOUR_SIGNAL_NUMBER is not directly comparable
            # or if 'sourceName' being 'Note to Self' is a more reliable check.
            if sender_identifier == YOUR_SIGNAL_NUMBER or sender_number == YOUR_SIGNAL_NUMBER:
                 print(f"process_incoming_message: Ignoring regular dataMessage from self ({sender_identifier})", flush=True)
                 return # Usually, we want to process messages to self if they are commands
            print("process_incoming_message: Found dataMessage (from external contact).", flush=True)
            message_body = envelope['dataMessage'].get('message')
            # timestamp = envelope['dataMessage'].get('timestamp') # Unused
            recipient_for_reply = sender_identifier

        elif envelope.get('syncMessage'):
            print("process_incoming_message: Found syncMessage.", flush=True)
            sync_message = envelope['syncMessage']
            if sync_message.get('sentMessage'):
                sent_message = sync_message['sentMessage']
                destination_uuid = sent_message.get('destinationUuid')
                destination_number = sent_message.get('destinationNumber')
                # Check if the message was sent TO your number (i.e., it's a "Note to Self")
                if destination_uuid == YOUR_SIGNAL_NUMBER or destination_number == YOUR_SIGNAL_NUMBER:
                    print("process_incoming_message: Found sync'd 'sent' message addressed to self (potential bot command).", flush=True)
                    message_body = sent_message.get('message')
                    # timestamp = sent_message.get('timestamp') # Unused
                    # Reply to the original sender of the sync message, which is 'sourceUuid' or 'sourceNumber'
                    # For "Note to Self", this will be your own UUID/number.
                    recipient_for_reply = sender_identifier # This should be YOUR_SIGNAL_NUMBER's UUID
                    print(f"process_incoming_message: Set recipient_for_reply to UUID: {recipient_for_reply}", flush=True)
                else:
                    print(f"process_incoming_message: Ignoring sync'd 'sent' message not addressed to self (sent to {destination_number or destination_uuid}).", flush=True)
                    return
            elif sync_message.get('readMessages'):
                print("process_incoming_message: Ignoring 'readMessages' sync message.", flush=True)
                return
            else:
                 print(f"process_incoming_message: Ignoring other sync message type: {list(sync_message.keys())}", flush=True)
                 return
        # ... (rest of message type checks: typing, receipt, etc. - keep as is) ...
        elif envelope.get('typingMessage'):
            print(f"process_incoming_message: Ignoring typing message from {sender_identifier}", flush=True)
            return
        elif envelope.get('receiptMessage'):
            print(f"process_incoming_message: Ignoring receipt message from {sender_identifier}", flush=True)
            return
        else:
            print(f"process_incoming_message: Envelope type not handled: {list(envelope.keys())}", flush=True)
            return

        if message_body and recipient_for_reply:
            message_body_stripped = message_body.strip()
            message_body_lower = message_body_stripped.lower()

            if message_body_lower == "/reset":
                print(f"Resetting conversation for {sender_identifier}", flush=True)
                if llm_client_global.reset_conversation(sender_identifier):
                    send_signal_message(recipient_for_reply, "Conversation history reset.")
                else:
                    send_signal_message(recipient_for_reply, "Could not find conversation to reset.")
                return

            elif message_body_lower.startswith("xx"):
                print("Keyword 'xx' detected. Initiating direct image generation flow (bypassing LLM).", flush=True)
                direct_image_prompt = message_body_stripped[2:].strip()
                if not direct_image_prompt:
                    send_signal_message(recipient_for_reply, "Please provide a prompt after 'xx'. Example: xx a cute cat")
                    return
                try:
                    print(f"Calling image generator directly with prompt: '{direct_image_prompt}'", flush=True)
                    image_path = generate_image(direct_image_prompt)
                    if image_path:
                        send_signal_message(recipient_for_reply, "", attachments=[image_path])
                    else:
                        send_signal_message(recipient_for_reply, "Sorry, direct image generation failed.")
                except Exception as e:
                     print(f"Error during direct image generation or sending: {e}", flush=True)
                     send_signal_message(recipient_for_reply, f"Sorry, an error occurred during direct image generation: {e}")
                return

            elif ";" in message_body_lower: # LLM-assisted image generation
                print("Keyword ';' detected. Initiating LLM-assisted image generation flow.", flush=True)
                if llm_client_global:
                    try:
                        image_prompt_instruction = f"Based on the following user request, generate a concise and effective prompt suitable for an AI image generator. Avoid full sentences. It should consist mainly of single words, and two word phrases separated by commas. (example: 1girl, Brunette, sweater, thong, green eyes, bent over, nervous, realistic, best quality,etc). Don't forget the commas. include hair color, eye color, and clothing in prompt. Only do this for image request prompts like this one. limit prompt length to 200 characters. User request: '{message_body}'"
                        image_gen_prompt = llm_client_global.send_request(image_prompt_instruction, user_id=sender_identifier)
                        print(f"Received image generation prompt from LLM: '{image_gen_prompt}'", flush=True)
                        if not image_gen_prompt: raise Exception("LLM failed to generate an image prompt.")
                        image_path = generate_image(image_gen_prompt)
                        if image_path:
                            send_signal_message(recipient_for_reply, "", attachments=[image_path])
                        else:
                            send_signal_message(recipient_for_reply, "Sorry, I couldn't generate the image.")
                    except Exception as e:
                        print(f"Error during LLM-assisted image generation: {e}", flush=True)
                        send_signal_message(recipient_for_reply, f"Sorry, an error occurred: {e}")
                return
            else: # Regular text response
                 if llm_client_global:
                    try:
                        print(f"No special keyword. Sending prompt to LLM for text response: '{message_body}'", flush=True)
                        llm_response = llm_client_global.send_request(message_body, user_id=sender_identifier)
                        print(f"Received LLM text response: '{llm_response}'", flush=True)
                        send_signal_message(recipient_for_reply, llm_response)
                    except Exception as e:
                        print(f"Error during LLM request: {e}", flush=True)
                        send_signal_message(recipient_for_reply, f"Sorry, an error occurred: {e}")
                 return

        elif message_body is None:
             print("process_incoming_message: No message body found to process.", flush=True)

    except Exception as e:
        print(f"Error processing incoming message JSON: {e}\nData: {data}", flush=True)
    finally:
        print(f"--- Exiting process_incoming_message ---", flush=True)


def handle_socket_data_loop():
    """Reads data from socket, parses JSON, and processes messages."""
    global receive_buffer, running, signal_socket
    print("--- handle_socket_data_loop started ---", flush=True)
    while running:
        if not signal_socket: # Check if socket is still valid
            print("handle_socket_data_loop: Socket is None, exiting loop.", flush=True)
            running = False
            break
        ready_to_read, _, _ = select.select([signal_socket], [], [], 0.1)
        if ready_to_read:
            try:
                data = signal_socket.recv(4096)
                if data:
                    receive_buffer += data.decode('utf-8', errors='ignore')
                    while '\n' in receive_buffer:
                        message_json, receive_buffer = receive_buffer.split('\n', 1)
                        if message_json:
                            try:
                                message_data = json.loads(message_json)
                                if message_data.get('method') == 'receive':
                                    process_incoming_message(message_data)
                                # else: # Log other JSON-RPC responses/errors from signal-cli if needed
                                # print(f"Received JSON-RPC from signal-cli: {message_data}", flush=True)
                            except json.JSONDecodeError as jde:
                                print(f"ERROR: JSONDecodeError: {jde}. Malformed JSON: {message_json}", flush=True)
                            except Exception as e:
                                print(f"ERROR: Exception processing JSON message: {e}\nJSON: {message_json}", flush=True)
                else: # Socket closed
                    print("Socket connection closed by signal-cli (recv returned 0 bytes).", flush=True)
                    running = False # Signal all loops to stop
                    break
            except ConnectionResetError:
                print("ERROR: ConnectionResetError during recv(). Socket connection reset by signal-cli.", flush=True)
                running = False
                break
            except BlockingIOError: # Should not happen with select
                pass
            except Exception as e: # Catch other socket errors
                if running: # Only print if we weren't already stopping
                    print(f"ERROR: Unhandled exception during socket read: {e}", flush=True)
                running = False
                break
        if not running: break # Check running flag again before sleep
        time.sleep(0.05)
    print("--- handle_socket_data_loop finished ---", flush=True)

def handle_send_queue_loop():
    """Sends messages from the queue over the socket."""
    global request_id_counter, running, signal_socket, send_queue
    print("--- handle_send_queue_loop started ---", flush=True)
    while running:
        try:
            recipient, message, attachments = send_queue.get(timeout=0.5) # Timeout to allow checking 'running' flag
            if recipient is None: # Sentinel value to stop the thread
                print("handle_send_queue_loop: Received stop sentinel.", flush=True)
                break

            if not signal_socket:
                print("handle_send_queue_loop: Socket is None, cannot send. Discarding message.", flush=True)
                send_queue.task_done()
                continue

            request_id_counter += 1
            params = {("number" if recipient.startswith('+') else "recipient"): recipient, "message": message}
            if attachments:
                params["attachments"] = [os.path.abspath(att) for att in attachments]

            request_json = {"jsonrpc": "2.0", "method": "send", "params": params, "id": request_id_counter}
            try:
                json_string = json.dumps(request_json) + '\n'
                log_message = message[:50] + "..." if len(message) > 50 else message
                log_message = log_message if message else "[Attachment Only]"
                print(f"Sending JSON-RPC ID {request_id_counter} to {recipient}: '{log_message}'", flush=True)
                signal_socket.sendall(json_string.encode('utf-8'))
            except BrokenPipeError:
                print("Error sending: Socket connection broken (BrokenPipeError).", flush=True)
                running = False # Stop all loops
                # Re-queue the message? Or discard? For now, discard.
            except Exception as e:
                print(f"Error sending JSON-RPC ID {request_id_counter}: {e}", flush=True)
            finally:
                send_queue.task_done()
        except queue.Empty:
            pass # Continue if queue is empty and timeout occurs
        except Exception as e: # Catch other errors in the send loop
            print(f"Error in send queue handler: {e}", flush=True)
    print("--- handle_send_queue_loop finished ---", flush=True)

def send_signal_message(recipient, message, attachments=None):
    """Queues a message to be sent."""
    send_queue.put((recipient, message, attachments if attachments is not None else []))

def listener_main_loop():
    """Main function for the listener thread."""
    global running, llm_client_global, listener_thread_global, sender_thread_global
    
    if not start_signal_cli_daemon():
        running = False # Ensure running is false if daemon fails
        return
    if not connect_socket_to_daemon():
        running = False # Ensure running is false if socket fails
        # Attempt to clean up signal_cli if socket connection failed after start
        if signal_cli_process and signal_cli_process.poll() is None:
            print("Terminating signal-cli due to socket connection failure...", flush=True)
            if os.name == 'nt':
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(signal_cli_process.pid)])
            else:
                signal_cli_process.terminate()
        return

    # Start the sender thread
    sender_thread_global = threading.Thread(target=handle_send_queue_loop, daemon=True)
    sender_thread_global.start()

    # Handle socket data in the current thread
    handle_socket_data_loop()

    print("listener_main_loop finished.", flush=True)


def start_listener_thread(llm_instance):
    """Starts the main listener logic in a new thread."""
    global llm_client_global, listener_thread_global, running
    llm_client_global = llm_instance
    running = True # Reset running flag at the start

    if listener_thread_global and listener_thread_global.is_alive():
        print("Listener thread already running.", flush=True)
        return listener_thread_global

    print("Initializing Signal listener thread...", flush=True)
    listener_thread_global = threading.Thread(target=listener_main_loop, name="SignalListenerThread")
    # Not setting daemon=True for listener_thread_global, so main can join it.
    listener_thread_global.start()
    print("Signal listener thread started.", flush=True)
    return listener_thread_global

def stop_listener():
    """Stops all processes and threads gracefully."""
    global running, signal_socket, signal_cli_process, listener_thread_global, sender_thread_global, signal_cli_stdout_thread, signal_cli_stderr_thread, send_queue

    print("Initiating shutdown sequence...", flush=True)
    running = False # Signal all loops to stop

    # Signal sender_thread to stop
    if sender_thread_global and sender_thread_global.is_alive():
        print("Signaling sender thread to stop...", flush=True)
        send_queue.put((None, None, None)) # Sentinel value

    # Close socket
    if signal_socket:
        print("Closing signal socket...", flush=True)
        try:
            # signal_socket.shutdown(socket.SHUT_RDWR) # Can cause issues if already closed
            signal_socket.close()
        except OSError as e:
            print(f"Error closing socket: {e}", flush=True)
        finally:
            signal_socket = None
            print("Signal socket set to None.", flush=True)

    # Wait for listener thread (which runs listener_main_loop)
    if listener_thread_global and listener_thread_global.is_alive():
        print("Waiting for listener thread to join...", flush=True)
        listener_thread_global.join(timeout=10)
        if listener_thread_global.is_alive():
            print("Listener thread did not join in time.", flush=True)

    # Wait for sender thread
    if sender_thread_global and sender_thread_global.is_alive():
        print("Waiting for sender thread to join...", flush=True)
        sender_thread_global.join(timeout=5)
        if sender_thread_global.is_alive():
            print("Sender thread did not join in time.", flush=True)

    # Terminate signal-cli process
    if signal_cli_process and signal_cli_process.poll() is None:
        print(f"Terminating signal-cli process (PID: {signal_cli_process.pid})...", flush=True)
        log_stop_event = threading.Event() # Create a new one for this scope if needed
                                          # Or ensure the one from start_signal_cli_daemon is accessible
                                          # For simplicity, assume log_stream threads will see process.stdout/stderr close
        
        # Signal logging threads that the process is about to be terminated
        # This is tricky because log_stop_event was local to start_signal_cli_daemon
        # A better approach would be to pass a shared stop event or make it global.
        # For now, rely on stream closure.

        try:
            if os.name == 'nt':
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(signal_cli_process.pid)])
            else:
                signal_cli_process.terminate()
                try:
                    signal_cli_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    print("signal-cli did not terminate gracefully, killing...", flush=True)
                    signal_cli_process.kill()
                    signal_cli_process.wait(timeout=5) # Wait for kill
            
            if signal_cli_process.poll() is not None:
                 print("signal-cli process terminated.", flush=True)
            else:
                 print("signal-cli process might still be running.", flush=True)

        except Exception as e:
            print(f"Error terminating signal-cli: {e}", flush=True)
        finally:
            signal_cli_process = None

    # Wait for signal-cli output logging threads
    if signal_cli_stdout_thread and signal_cli_stdout_thread.is_alive():
        print("Waiting for signal-cli stdout logger thread to join...", flush=True)
        signal_cli_stdout_thread.join(timeout=5)
    if signal_cli_stderr_thread and signal_cli_stderr_thread.is_alive():
        print("Waiting for signal-cli stderr logger thread to join...", flush=True)
        signal_cli_stderr_thread.join(timeout=5)

    print("Shutdown sequence complete.", flush=True)

# If running signal_handler.py directly for testing (as per existing __main__ block)
# This part needs to be updated to use the new function names and structure
if __name__ == '__main__':
    print("Running signal_handler.py directly for testing JSON-RPC mode...", flush=True)
    # This test setup is simplified and may need adjustment
    # It assumes config.py is in the parent directory and loads .env
    try:
        from .config import API_URL, MODEL_IDENTIFIER
        test_llm_client = LLMClient(API_URL, MODEL_IDENTIFIER) # MODEL_IDENTIFIER is now auto-detected
        start_listener_thread(test_llm_client)

        while running: # Keep main test thread alive
            if listener_thread_global and not listener_thread_global.is_alive():
                print("Listener thread died unexpectedly.", flush=True)
                running = False # Stop if listener thread dies
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nCtrl+C detected in test. Stopping...", flush=True)
    finally:
        stop_listener()
        print("Test finished.", flush=True)