# Signal LMStudio Backend

This project provides a backend service that connects the Signal messaging app (via `signal-cli`) to a local Large Language Model (LLM) running through a server like LM Studio, which exposes an OpenAI-compatible API endpoint. It allows you to interact with the LLM by sending messages to your own number ("Note to Self") in the Signal app.

## Features

*   Connects to `signal-cli` running in daemon mode via TCP socket.
*   Listens for incoming Signal messages, specifically messages sent to your own number ("Note to Self").
*   Forwards messages from "Note to Self" to a specified LLM API endpoint.
*   Maintains conversation history (context) for interactions with the LLM.
*   Sends the LLM's response back to your "Note to Self" chat in Signal.
*   Handles graceful shutdown on Ctrl+C.

## Project Structure

```
signal-lmstudio-backend
├── src
│   ├── __init__.py
│   ├── main.py          # Entry point of the application
│   ├── config.py        # Configuration settings
│   ├── llm_client.py    # Client for OpenAI API communication (with history)
│   └── signal_handler.py # Manages signal-cli processes and message handling
├── tests
│   ├── __init__.py      # Package for tests
│   └── test_example.py   # Unit tests for the application

├── requirements.txt      # Project dependencies
└── README.md             # Project documentation
```

## Prerequisites

1.  **Python:** Version 3.8 or higher recommended.
2.  **Java:** JRE version 21 or higher (required by `signal-cli` 0.13.14+). Verify with `java -version`.
3.  **signal-cli:** Version 0.13.14 or compatible.
    *   Download from the [signal-cli releases page](https://github.com/AsamK/signal-cli/releases).
    *   Extract it to a known location on your system.
    *   Ensure `signal-cli` is registered and linked to your Signal account. You might need to run commands like `signal-cli -u YOUR_SIGNAL_NUMBER register` and `signal-cli -u YOUR_SIGNAL_NUMBER verify CODE` separately first if this is a new setup.
4.  **LM Studio (or similar):** An OpenAI-compatible API server running locally. The default configuration expects it at `http://127.0.0.1:1234`.

## Setup Instructions

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd signal-lmstudio-backend
    ```

2.  **Create and Activate Virtual Environment:**
    ```bash
    # Create the environment
    python -m venv venv

    # Activate it (Windows)
    .\venv\Scripts\activate

    # Activate it (macOS/Linux)
    # source venv/bin/activate
    ```
    *(You should see `(venv)` at the beginning of your terminal prompt)*

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    *   Create a file named `.env` in the project's root directory (`signal-lmstudio-backend/.env`).
    *   Add the following lines, **adjusting the paths and numbers accordingly**:

        ```dotenv
        # Example .env content:
        SIGNAL_CLI_PATH=C:\path\to\your\signal-cli-0.13.14\bin\signal-cli.bat # Use signal-cli.bat on Windows
        # SIGNAL_CLI_PATH=/path/to/your/signal-cli-0.13.14/bin/signal-cli # Use signal-cli on Linux/macOS
        YOUR_SIGNAL_NUMBER=+1xxxxxxxxxx # Your Signal phone number in international format

        # Optional: Override default LM Studio URL or model if needed
        # API_URL=http://127.0.0.1:1234
        # MODEL_IDENTIFIER=your-model-name
        ```
    *   **Important:** Ensure `SIGNAL_CLI_PATH` points to the correct executable (`signal-cli.bat` for Windows, `signal-cli` for Linux/macOS) within your extracted `signal-cli` directory.
    *   Replace `+1xxxxxxxxxx` with your actual Signal phone number, including the `+` and country code.

## Running the Application

1.  **Ensure Prerequisites are Met:** Make sure your LLM server (e.g., LM Studio) is running and `signal-cli` is correctly set up and linked to your account.
2.  **Activate Virtual Environment:** If not already active, run `.\venv\Scripts\activate` (Windows) or `source venv/bin/activate` (macOS/Linux).
3.  **Start the Backend:**
    ```bash
    python -m src.main
    ```

    The application will:
    *   Load configuration from `.env`.
    *   Initialize the LLM client.
    *   Attempt to start the `signal-cli` daemon process in the background, listening on a TCP port.
    *   Connect to the `signal-cli` daemon.
    *   Wait for incoming messages.

4.  **Interact via Signal:**
    *   Open the Signal app on your phone or desktop client.
    *   Go to the "Note to Self" conversation (the chat with your own number).
    *   Send a message.
    *   The backend script will detect this message, send it to your LLM, and send the response back to your "Note to Self" chat.

5.  **Stopping the Application:**
    *   Press `Ctrl+C` in the terminal where the script is running. The application will attempt to shut down `signal-cli` gracefully.

## Troubleshooting

*   **"Connection refused" errors:** Ensure `signal-cli` can start correctly. Run the `signal-cli ... daemon --tcp ...` command shown in the script's output manually in a separate terminal to check for errors from `signal-cli` itself. Also, ensure your LLM server is running at the configured `API_URL`.
*   **"No recipients given" error from `signal-cli`:** This might occur if `signal-cli` has trouble sending "Note to Self" messages. The current code attempts to use the UUID, which usually works. Check `signal-cli`'s own logs if issues persist.
*   **Messages not appearing:** Verify the `YOUR_SIGNAL_NUMBER` in `.env` is correct. Check the script's console output for errors during message processing or sending. Ensure `signal-cli` is properly linked and running.
*   **Java Version:** Double-check your Java version (`java -version`) meets the requirement for your `signal-cli` version.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## License

This project is licensed under the MIT License.