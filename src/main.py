from flask import Flask, request, jsonify
from config import API_URL, MODEL_IDENTIFIER
from llm_client import LLMClient
from signal_handler import SignalHandler

app = Flask(__name__)
llm_client = LLMClient(API_URL, MODEL_IDENTIFIER)
signal_handler = SignalHandler(llm_client)

@app.route('/message', methods=['POST'])
def handle_message():
    data = request.json
    response = signal_handler.process_message(data)
    return jsonify(response)

if __name__ == '__main__':
    app.run(port=5000)