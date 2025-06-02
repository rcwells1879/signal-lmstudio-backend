import subprocess
import json
import threading
import time
import socket
import select
import queue
import os
import signal as os_signal

from .config import SIGNAL_CLI_PATH, YOUR_SIGNAL_NUMBER, SIGNAL_DAEMON_ADDRESS, JSON_RPC_PORT
from .llm_client import LLMClient
from .image_generator import generate_image

# Global variables
llm_client_global = None
signal_cli_process = None
signal_socket = None
listener_thread_global = None
sender_thread_global = None
signal_cli_stdout_thread = None
signal_cli_stderr_thread = None

send_queue = queue.Queue()
receive_buffer = ""
request_id_counter = 0
running = True

def log_stream(stream, prefix, stop_event):
    """Reads and prints lines from a stream until stop_event is set."""
    try:
        for line in iter(stream.readline, ''):
            if stop_event.is_set() and not line:
                break
            if line:
                print(f"[{prefix}] {line.strip()}", flush=True)
            elif stop_event.is_set():
                break
            else:
                time.sleep(0.01)
        stream.close()
    except ValueError:
        pass
    except Exception as e:
        print(f"[{prefix}] Error reading stream: {e}", flush=True)

def start_signal_cli_daemon():
    """Starts the signal-cli daemon process and threads to log its output."""
    global signal_cli_process, signal_cli_stdout_thread, signal_cli_stderr_thread, running
    
    log_stop_event = threading.Event()

    command = [
        SIGNAL_CLI_PATH,
        "-u", YOUR_SIGNAL_NUMBER,
        "daemon",
        "--tcp", SIGNAL_DAEMON_ADDRESS
    ]
    
    try:
        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        signal_cli_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding='utf-8',
            errors='ignore',
            bufsize=1,
            creationflags=creationflags
        )

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

        time.sleep(5)

        if signal_cli_process.poll() is not None:
            print(f"signal-cli failed to start. Return code: {signal_cli_process.returncode}", flush=True)
            log_stop_event.set()
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
    
    try:
        signal_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        signal_socket.connect((host, port))
        signal_socket.setblocking(False)
        return True
    except Exception as e:
        print(f"Error connecting to signal-cli daemon: {e}", flush=True)
        running = False
        return False

def process_incoming_message(data):
    """Processes a received message JSON from signal-cli."""
    global llm_client_global
    
    try:
        envelope = data.get('params', {}).get('envelope', {})
        if not envelope:
            return

        sender_identifier = envelope.get('sourceUuid') or envelope.get('sourceNumber')
        sender_number = envelope.get('sourceNumber')
        
        message_body = None
        recipient_for_reply = None 

        if envelope.get('dataMessage'):
            if sender_identifier == YOUR_SIGNAL_NUMBER or sender_number == YOUR_SIGNAL_NUMBER:
                return
            message_body = envelope['dataMessage'].get('message')
            recipient_for_reply = sender_identifier

        elif envelope.get('syncMessage'):
            sync_message = envelope['syncMessage']
            if sync_message.get('sentMessage'):
                sent_message = sync_message['sentMessage']
                destination_uuid = sent_message.get('destinationUuid')
                destination_number = sent_message.get('destinationNumber')
                
                if destination_uuid == YOUR_SIGNAL_NUMBER or destination_number == YOUR_SIGNAL_NUMBER:
                    message_body = sent_message.get('message')
                    recipient_for_reply = sender_identifier
                else:
                    return
            else:
                return
        else:
            return

        if message_body and recipient_for_reply:
            message_body_stripped = message_body.strip()
            message_body_lower = message_body_stripped.lower()

            # Reset conversation command
            if message_body_lower == "/reset":
                if llm_client_global.reset_conversation(sender_identifier):
                    send_signal_message(recipient_for_reply, "Conversation history reset.")
                else:
                    send_signal_message(recipient_for_reply, "Could not find conversation to reset.")
                return

            # Direct image generation
            elif message_body_lower.startswith("xx"):
                direct_image_prompt = message_body_stripped[2:].strip()
                if not direct_image_prompt:
                    send_signal_message(recipient_for_reply, "Please provide a prompt after 'xx'. Example: xx a cute cat")
                    return
                try:
                    image_path = generate_image(direct_image_prompt)
                    if image_path:
                        send_signal_message(recipient_for_reply, f"Direct image for '{direct_image_prompt}':", attachments=[image_path])
                    else:
                        send_signal_message(recipient_for_reply, f"Sorry, failed to generate image directly for: '{direct_image_prompt}'")
                except Exception as e:
                     send_signal_message(recipient_for_reply, f"Sorry, an error occurred during direct image generation: {e}")
                return

            # LLM-assisted image generation
            elif ";" in message_body_lower:
                if llm_client_global:
                    try:
                        image_prompt_instruction = f"Based on the following user request, generate a detailed and effective prompt suitable for an AI image generator. Avoid full sentences. It should consist mainly of single words, and two word phrases separated by commas. (example: 1girl, Brunette, sweater, thong, green eyes, bent over, nervous, realistic, best quality, dark skin, fair skin, couch, bed, penthouse, cityscape, scenic,etc). Don't forget the commas between each descriptor. include at least 20 descriptors. ALWAYS include hair color and style, eye color, skin color and any other physical description of the character portrayed by the roleplay assistant.prompt should be contextually relevant to what is currently happening in the conversation. limit prompt length to 300 characters. User request: '{message_body}'"
                        image_gen_prompt = llm_client_global.send_request(image_prompt_instruction, user_id=sender_identifier)
                        if not image_gen_prompt: 
                            raise Exception("LLM failed to generate an image prompt.")
                        image_path = generate_image(image_gen_prompt)
                        if image_path:
                            send_signal_message(recipient_for_reply, "", attachments=[image_path])
                        else:
                            send_signal_message(recipient_for_reply, "Sorry, I couldn't generate the image.")
                    except Exception as e:
                        send_signal_message(recipient_for_reply, f"Sorry, an error occurred: {e}")
                return
            
            # Regular text response
            else:
                if llm_client_global:
                    try:
                        llm_response = llm_client_global.send_request(message_body, user_id=sender_identifier)
                        send_signal_message(recipient_for_reply, llm_response)
                    except Exception as e:
                        send_signal_message(recipient_for_reply, f"Sorry, an error occurred: {e}")
                return

    except Exception as e:
        print(f"Error processing incoming message JSON: {e}", flush=True)

def handle_socket_data_loop():
    """Reads data from socket, parses JSON, and processes messages."""
    global receive_buffer, running, signal_socket
    
    while running:
        if not signal_socket:
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
                            except json.JSONDecodeError:
                                pass
                            except Exception:
                                pass
                else:
                    running = False
                    break
            except ConnectionResetError:
                running = False
                break
            except BlockingIOError:
                pass
            except Exception:
                if running:
                    running = False
                break
        if not running: 
            break
        time.sleep(0.05)

def handle_send_queue_loop():
    """Sends messages from the queue over the socket."""
    global request_id_counter, running, signal_socket, send_queue
    
    while running:
        try:
            recipient, message, attachments = send_queue.get(timeout=0.5)
            if recipient is None:
                break

            if not signal_socket:
                send_queue.task_done()
                continue

            request_id_counter += 1
            params = {("number" if recipient.startswith('+') else "recipient"): recipient, "message": message}
            if attachments:
                params["attachments"] = [os.path.abspath(att) for att in attachments]

            request_json = {"jsonrpc": "2.0", "method": "send", "params": params, "id": request_id_counter}
            try:
                json_string = json.dumps(request_json) + '\n'
                signal_socket.sendall(json_string.encode('utf-8'))
            except BrokenPipeError:
                running = False
            except Exception:
                pass
            finally:
                send_queue.task_done()
        except queue.Empty:
            pass
        except Exception:
            pass

def send_signal_message(recipient, message, attachments=None):
    """Queues a message to be sent."""
    send_queue.put((recipient, message, attachments if attachments is not None else []))

def listener_main_loop():
    """Main function for the listener thread."""
    global running, sender_thread_global
    
    if not start_signal_cli_daemon():
        running = False
        return
    if not connect_socket_to_daemon():
        running = False
        if signal_cli_process and signal_cli_process.poll() is None:
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

def start_listener_thread(llm_instance):
    """Starts the main listener logic in a new thread."""
    global llm_client_global, listener_thread_global, running
    llm_client_global = llm_instance
    running = True

    if listener_thread_global and listener_thread_global.is_alive():
        return listener_thread_global

    listener_thread_global = threading.Thread(target=listener_main_loop, name="SignalListenerThread")
    listener_thread_global.start()
    return listener_thread_global

def stop_listener():
    """Stops all processes and threads gracefully."""
    global running, signal_socket, signal_cli_process, listener_thread_global, sender_thread_global, signal_cli_stdout_thread, signal_cli_stderr_thread, send_queue

    running = False

    # Signal sender_thread to stop
    if sender_thread_global and sender_thread_global.is_alive():
        send_queue.put((None, None, None))

    # Close socket
    if signal_socket:
        try:
            signal_socket.close()
        except OSError:
            pass
        finally:
            signal_socket = None

    # Wait for threads
    if listener_thread_global and listener_thread_global.is_alive():
        listener_thread_global.join(timeout=10)

    if sender_thread_global and sender_thread_global.is_alive():
        sender_thread_global.join(timeout=5)

    # Terminate signal-cli process
    if signal_cli_process and signal_cli_process.poll() is None:
        try:
            if os.name == 'nt':
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(signal_cli_process.pid)])
            else:
                signal_cli_process.terminate()
                try:
                    signal_cli_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    signal_cli_process.kill()
                    signal_cli_process.wait(timeout=5)
        except Exception:
            pass
        finally:
            signal_cli_process = None

    # Wait for signal-cli output logging threads
    if signal_cli_stdout_thread and signal_cli_stdout_thread.is_alive():
        signal_cli_stdout_thread.join(timeout=5)
    if signal_cli_stderr_thread and signal_cli_stderr_thread.is_alive():
        signal_cli_stderr_thread.join(timeout=5)

if __name__ == '__main__':
    try:
        from .config import API_URL
        test_llm_client = LLMClient(API_URL)
        start_listener_thread(test_llm_client)

        while running:
            if listener_thread_global and not listener_thread_global.is_alive():
                running = False
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_listener()