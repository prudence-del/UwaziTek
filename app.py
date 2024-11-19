from flask import Flask, jsonify
import os
import json

app = Flask(__name__)


@app.route('/generate-report', methods=['GET'])
def generate_report():
    file_path = os.path.join(os.path.dirname(__file__), "fraud_report_with_metadata_and_categories.json")

    try:
        # Open and load the JSON file
        with open(file_path, 'r') as file:
            report = json.load(file)
        return jsonify(report), 200
    except FileNotFoundError:
        return jsonify({"error": "Report file not found"}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
