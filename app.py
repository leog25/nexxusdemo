from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
import threading
import simulation  # Import the simulation module

app = Flask(__name__, static_folder='static')
socketio = SocketIO(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/simulation')
def simulation_page():
    return render_template('simulation.html')

@app.route('/ledger')
def ledger_page():
    return render_template('ledger.html')

def start_web_server():
    socketio.run(app, debug=True, use_reloader=False)  # Disable reloader for threaded mode

if __name__ == '__main__':
    # Start the Flask web server in a separate thread
    web_thread = threading.Thread(target=start_web_server)
    web_thread.start()

    # Run the simulation in the main thread
    simulation.run_simulation(socketio)
