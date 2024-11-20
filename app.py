from flask import Flask, jsonify, request
import os
import json
import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
import re

from fuzzywuzzy import process

app = Flask(__name__)

# Load base data (you may want to load it at the start of the app for efficiency)
Procedure_file_path = 'synthea_sample_data_csv_latest/procedures.csv'
Medication_file_path = 'synthea_sample_data_csv_latest/medications.csv'
Base_data = pd.read_csv(Procedure_file_path)
medication_data = pd.read_csv(Medication_file_path)

print(os.path.exists('synthea_sample_data_csv_latest/procedures.csv'))
print(os.path.exists('synthea_sample_data_csv_latest/medications.csv'))

base_data = pd.read_excel("Base_data_report.xlsx")
medication_data = pd.read_excel("medication_base_report.xlsx")


# You can add your fraud detection functions here (from your long script above)
def normalize_description(desc):
    return re.sub(r"\s+", " ", desc.lower().strip())


base_data['Normalized DESCRIPTION'] = base_data['Services provided at Wellness Hospital'].apply(normalize_description)
medication_data['Normalized DESCRIPTION'] = medication_data['Wellness Medication'].apply(normalize_description)


# Example of a fraud detection function to be added

def compare_invoice_with_base(invoice_items, hospital_base_data, medication_base_data):
    # Normalize the DESCRIPTION column for both datasets if not already done
    if 'Normalized DESCRIPTION' not in hospital_base_data.columns:
        hospital_base_data['Normalized DESCRIPTION'] = (hospital_base_data['DESCRIPTION'].apply
                                                        (normalize_description))

    if 'Normalized DESCRIPTION' not in medication_base_data.columns:
        medication_base_data['Normalized DESCRIPTION'] = medication_base_data['DESCRIPTION'].apply(
            normalize_description)

    comparison_results = []
    unmatched_items = []
    if invoice_items is None or invoice_items.empty:
        raise ValueError("No valid invoice items found")

    total_invoice_amount = invoice_items['AMOUNT'].sum()
    # Calculate total invoice amount

    for _, item in invoice_items.iterrows():
        description = normalize_description(item['DESCRIPTION'])
        invoice_cost = item['AMOUNT']

        # Check if the item is a medication or a procedure
        if 'medication' in description.lower():  # You can refine this check
            base_data = medication_base_data
            is_medication = True
        else:
            base_data = hospital_base_data
            is_medication = False

        base_descriptions = base_data['Normalized DESCRIPTION'].tolist()
        match = process.extractOne(description, base_descriptions)
        # Retrieve base row based on the description
        if match:
            # Retrieve base row based on the best match
            base_row = base_data[base_data['Normalized DESCRIPTION'] == match[0]]
        else:
            base_row = pd.DataFrame()  # If no match is found
        print(f"Invoice item description: {description}")
        print(f"Base data item descriptions:\n{base_data['Normalized DESCRIPTION'].head()}")

        if base_row.empty:
            # If service is not found in the base data
            unmatched_items.append(description)
            comparison_results.append({
                'Description': item['DESCRIPTION'],
                'Invoice Cost': invoice_cost,
                'Base Cost': None,
                'Price Difference': None,
                'Fraud Category': "Service not found in base data"
            })
            continue

            # Base cost retrieved

        base_cost = float(base_row['BASE_COST'].values[0])
        price_difference = invoice_cost - base_cost
        price_difference = round(price_difference, 2)  # 2 decimal places

        # Determine fraud category based on the price difference for both procedures and medications
        if is_medication:
            # Adjust thresholds for medication (example values)
            if invoice_cost == base_cost or (invoice_cost > base_cost and (invoice_cost - base_cost) <= 20):
                fraud_category = "Legitimate"
            elif invoice_cost > base_cost:
                fraud_category = "Risk" if (invoice_cost - base_cost) <= 200 else "Fraud"
            else:
                fraud_category = "Potential Underreporting"
        else:
            # Hospital procedure fraud categorization logic
            if invoice_cost == base_cost or (invoice_cost > base_cost and (invoice_cost - base_cost) <= 100):
                fraud_category = "Legitimate"
            elif invoice_cost > base_cost:
                fraud_category = "Risk" if (invoice_cost - base_cost) <= 3000 else "Fraud"
            else:
                fraud_category = "Potential Underreporting"

        # Append result with the new price difference column
        comparison_results.append({
            'Description': item['DESCRIPTION'],
            'Invoice Cost': invoice_cost,
            'Base Cost': base_cost,
            'Price Difference': price_difference,
            'Fraud Category': fraud_category
        })

    # Add summary row for total invoice amount after the loop
    total_row = {
        'Description': 'Total Invoice Amount',
        'Invoice Cost': total_invoice_amount,
        'Base Cost': None,
        'Price Difference': None,
        'Fraud Category': None
    }

    comparison_results.append(total_row)  # Add total row only once after processing all items

    # If unmatched items exist, print them
    if unmatched_items:
        print("Unmatched invoice items (descriptions not found in base data):")
        for item in unmatched_items:
            print(f"- {item}")

    return comparison_results


@app.route('/generate-report', methods=['GET'])
def generate_report():
    file_path = os.path.join(os.path.dirname(__file__), "fraud_report_with_metadata_and_categories.json")
    try:
        with open(file_path, 'r') as file:
            report = json.load(file)
        return jsonify(report), 200
    except FileNotFoundError:
        return jsonify({"error": "Report file not found"}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/process-invoice', methods=['POST'])
def process_invoice_request():
    invoice_file = request.files.get('invoice_file')  # If it's a PDF or image
    invoice_text = request.form.get('invoice_text')  # If it's raw text

    if invoice_file:
        # Process PDF file
        invoice_file_path = os.path.join("temp", invoice_file.filename)
        invoice_file.save(invoice_file_path)
        invoice_text = extract_text_from_pdf(invoice_file_path)
        if not invoice_text:
            return jsonify({"error": "Unable to extract text from the invoice PDF"}), 400

    if not invoice_text:
        return jsonify({"error": "No invoice text or file provided"}), 400

    metadata, mandatory_reasons = check_mandatory_fields(invoice_text)
    if mandatory_reasons:
        return jsonify({"error": f"Mandatory field validation failed: {mandatory_reasons}"}), 400

    invoice_items = extract_invoice_items(invoice_text)
    fraud_results = compare_invoice_with_base(invoice_items, Base_data, medication_data)

    # Save the results to a JSON file
    report = {"metadata": metadata, "fraud_results": fraud_results}
    try:
        with open("fraud_report_with_metadata_and_categories.json", "w") as f:
            json.dump(report, f)
    except Exception as e:
        return jsonify({"error": f"Error saving the fraud report: {str(e)}"}), 500

    return jsonify({"message": "Invoice processed and fraud results saved."}), 200


def extract_text_from_pdf(pdf_invoice_path):
    try:
        with pdfplumber.open(pdf_invoice_path) as pdf:
            invoice_text = "\n".join([page.extract_text() or "" for page in pdf.pages if page.extract_text()])
            print(invoice_text)  # Print the extracted text to verify
            return invoice_text
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""


def check_mandatory_fields(invoice_text):
    mandatory_fields = ["policy Number", "Patient Name", "Invoice No", "Date", "Bill to", "Bank Name", "Bank Account"]

    missing_fields = []

    # Define patterns for extracting metadata
    patterns = {
        'Hospital Name': r'Hospital Name:\s*([\w\s]+)',
        'policy Number': r'policy Number:\s*(\S+)',
        'Patient Name': r'Patient Name:\s*([\w\s]+)',
        'Invoice No': r'Invoice No:\s*([\w\d]+)',
        'Date': r'Date:\s*([\w\s,]+)',
        'Bank Name': r'Bank Name:\s*([\w\s,]+)',
        'Bank Account': r'Bank Account:\s*(\d{4}\s\d{4}\s\d{4})'
    }

    # Extract metadata
    metadata = {}
    for field, pattern in patterns.items():
        match = re.search(pattern, invoice_text)
        metadata[field] = match.group(1) if match else "N/A"

    # Check for missing mandatory fields
    for field in mandatory_fields:
        if field not in invoice_text:
            missing_fields.append(field)

    # Ensure 'Hospital Name' has a default value if not found
    if metadata["Hospital Name"] == "N/A":
        metadata["Hospital Name"] = "Wellness Hospital"

    # Prepare metadata to return
    metadata_fields = [
        ("Hospital Name", metadata.get("Hospital Name", "N/A")),
        ("Bank Name", metadata.get("Bank Name", "N/A")),
        ("Bank Account", metadata.get("Bank Account", "N/A")),
        ("Patient Name", metadata.get("Patient Name", "N/A")),
        ("Policy Number", metadata.get("policy Number", "N/A")),
        ("Invoice Number", metadata.get("Invoice No", "N/A")),
    ]

    if missing_fields:
        return metadata_fields, missing_fields
    else:
        return metadata_fields, None


def extract_invoice_items(invoice_text):
    item_pattern = r"\d+\.\s+((?:\([A-Za-z0-9\s]+\)\s+)?[A-Za-z0-9\s/]+(?:\(\d+\s+[A-Za-z]+\))?)\s+\$(\d+[\.,]?\d{1,2})"

    items = []
    matches = re.findall(item_pattern, invoice_text)
    for match in matches:
        description = re.sub(r"^\d+\.\s*", "", match[0].strip())  # Remove item numbers
        amount = float(match[1].replace(',', ''))
        items.append({'DESCRIPTION': description, 'AMOUNT': amount})
    items_df = pd.DataFrame(items)
    print("Extracted Invoice Items:\n", items_df)

    return items_df


if __name__ == '__main__':
    app.run(host="127.0.0.1", port=5000, debug=True)
