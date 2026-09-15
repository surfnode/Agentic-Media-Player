import zmq
import sys

def send_download_command(query):
    context = zmq.Context()
    # Connect to the worker's PULL socket
    push_socket = context.socket(zmq.PUSH)
    push_socket.connect("tcp://127.0.0.1:5556")
    
    command = {
        "action": "download",
        "query": query
    }
    
    print(f"Sending command to ZeroMQ bus: {command}")
    push_socket.send_json(command)

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Kavinsky Nightcall"
    send_download_command(query)
