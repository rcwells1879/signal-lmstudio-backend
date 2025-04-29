# Signal LMStudio Backend

This project is a backend server that integrates with the Signal messaging app, allowing users to interact with an OpenAI API endpoint. The server is built using Python and Flask, and it communicates with the Signal app to process messages and generate responses using the specified language model.

## Project Structure

```
signal-lmstudio-backend
├── src
│   ├── __init__.py
│   ├── main.py          # Entry point of the application
│   ├── config.py        # Configuration settings
│   ├── llm_client.py    # Client for OpenAI API communication
│   └── signal_handler.py # Handles interactions with the Signal app
├── tests
│   ├── __init__.py      # Package for tests
│   └── test_example.py   # Unit tests for the application
├── requirements.txt      # Project dependencies
└── README.md             # Project documentation
```

## Setup Instructions

1.  **Navigate to the project directory:**
    If you are not already in the project's root directory (`signal-lmstudio-backend`), navigate to it using the `cd` command in your terminal.

2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    venv\Scripts\activate  # On Windows
    # source venv/bin/activate  # On macOS/Linux
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the server:**
    ```bash
    python src/main.py
    ```

## Usage

Once the server is running, it will listen for incoming messages from the Signal app. The server processes these messages and generates responses using the OpenAI API.

## API Configuration

-   **API Endpoint:** `http://127.0.0.1:1234`
-   **Model API Identifier:** `cydonia-24b-v2.1`

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.