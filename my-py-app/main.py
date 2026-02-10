from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({'message': 'Hello World'})

@app.route('/echo', methods=['POST'])
def echo():
    data = request.get_json()
    print(f"Echoing back: {data}")
    return jsonify({'you_sent': data})

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=False)