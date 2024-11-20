import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
import tkinter as tk
from tkinter import filedialog
from datetime import datetime, timedelta
import re
from openpyxl.workbook import Workbook
from openpyxl.styles import PatternFill
from fuzzywuzzy import process
import json

#%% Base data setup
# loading data with services offered in the hospital and their cost
Procedure_file_path = 'synthea_sample_data_csv_latest/procedures.csv'
Medication_file_path = 'synthea_sample_data_csv_latest/medications.csv'
Base_data = pd.read_csv(Procedure_file_path)
medication_data = pd.read_csv(Medication_file_path)
# reading the first 5 rows of the data
print(Base_data.head(5))
# detailed info about the data
print(Base_data.info())

#%% data cleaning
# procedure base data cleaning
# dropping unnecessary columns
Base_data = Base_data.drop(
    ['START', 'STOP', 'PATIENT', 'ENCOUNTER', 'SYSTEM', 'CODE', 'REASONCODE', 'REASONDESCRIPTION'], axis=1)
# columns left
print(Base_data.columns)

# drop duplicates (if service and cost are identical)
# keep the first occurrence
Base_data = Base_data.drop_duplicates(subset=['DESCRIPTION', 'BASE_COST'], keep='first')

# mean calculation of different charges but same service
# as_index=false will group description as regular column to avoid fixed(indexing)
Base_data = Base_data.groupby('DESCRIPTION', as_index=False).agg({'BASE_COST': 'mean'})

# format base_cost column to 2 decimal places
Base_data['BASE_COST'] = Base_data['BASE_COST'].map(lambda x: f"{x:.2f}")
# renaming columns {'OldName':'NewName'}
Base_data = Base_data.rename(columns={'DESCRIPTION': 'Services provided at Wellness Hospital'})

# Save the grouped(base) data to an Excel file in the current working directory
output_file_name = 'Base_data_report.xlsx'
Base_data.to_excel(output_file_name, index=False)
print(f"Report successfully saved to the current directory as {output_file_name}\n")

# medication base data cleaning
medication_data = medication_data.drop(
    ['START', 'STOP', 'PATIENT', 'PAYER', 'ENCOUNTER', 'CODE', 'PAYER_COVERAGE',
     'DISPENSES', 'TOTALCOST', 'REASONCODE', 'REASONDESCRIPTION'], axis=1)
# printing the first 5 rows after dropping the columns
print(medication_data.head(5))

# convert the description column to lower case to avoid retaining same medications
medication_data['DESCRIPTION'] = medication_data['DESCRIPTION'].str.lower()

# dropping duplicates
# count of the initial rows
initial_rows = len(medication_data)

# remaining rows after duplicates dropped
final_rows = medication_data.drop_duplicates(subset=['DESCRIPTION', 'BASE_COST'], keep='first')
final_rows = final_rows.shape[0]

# remaining rows
dropped_rows = initial_rows - final_rows
print(f"dropped duplicates rows: {dropped_rows}")

# remaining rows (will act as a base medication data)
print(f"remaining rows: {final_rows}")

# renaming columns
medication_data = medication_data.rename(columns={'DESCRIPTION': 'Wellness Medication'})
print(medication_data.columns)

# calculation of the mean cost of same medication names with different cost
medication_data = medication_data.groupby('Wellness Medication', as_index=False).agg({'BASE_COST': 'mean'})

# converting cost column to 2 decimal places
medication_data['BASE_COST'] = medication_data['BASE_COST'].map(lambda x: f"{x:.2f}")

# saving the output as an Excel file
report_file_name = 'medication_base_report.xlsx'
medication_data.to_excel(report_file_name, index=False)
print(f"report saved successfully: {report_file_name}")


#%% Invoice upload, text extract, image extract, convert text to data frame
# invoice upload
def upload_file():
    root = tk.Tk()
    root.withdraw()
    invoice_file_path = filedialog.askopenfilename(title="Select invoice")
    return invoice_file_path


# Function to clean up invoice text
def clean_text(text):
    # Remove extra spaces, newlines, or unwanted characters
    cleaned_text = " ".join(text.split())  # removes extra spaces and newlines
    return cleaned_text


# Function to extract and save image (watermark) from PDF
# fitz module is crucial for: extracting images, image+text extraction from pdf
# fitz helps in modification of pdf
# Check watermark and save images if present

# Function to extract text from the PDF
def extract_text_from_pdf(pdf_invoice_path):
    try:
        # Open the PDF with pdfplumber
        with pdfplumber.open(pdf_invoice_path) as pdf:
            # Extract text from all pages of the PDF
            invoice_text = "\n".join([page.extract_text() or "" for page in pdf.pages if page.extract_text()])

            # Display the extracted text
            if invoice_text:
                print("Extracted Invoice Text:\n")
                print(invoice_text)
                return invoice_text  # return the extracted text

            else:
                print("No text found in the invoice.")
                return ""  # return empty string if no text found
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""


# fitz is a module in the library (PyMuPDF)
# fitz modifies a pdf file: extract images and text from a pdf
def check_watermark(pdf_file_path):
    watermark_found = False
    try:
        with fitz.open(pdf_file_path) as pdf_document:
            for page_num in range(pdf_document.page_count):
                page = pdf_document.load_page(page_num)
                image_list = page.get_images(full=True)
                for i, img in enumerate(image_list):
                    xref = img[0]
                    base_image = pdf_document.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_path = f"watermark_page{page_num + 1}_img{i + 1}.png"
                    with open(image_path, "wb") as img_file:
                        img_file.write(image_bytes)
                    print(f"Watermark image saved as {image_path}")
                    watermark_found = True
        return watermark_found
    except Exception as e:
        print(f"Error checking watermark: {e}")
        return False


#%%  validation of the invoices
# check before the fraud test
# mandatory fields
def check_mandatory_fields(invoice_text):
    reasons = []
    mandatory_fields = ['policy Number', 'Patient Name', 'Invoice No', 'Date', 'Bill to', 'Bank Name', 'Bank Account']
    metadata = {}
    patterns = {
        'policy Number': r'policy Number:\s*(\S+)',
        'Patient Name': r'Patient Name:\s*([\w\s]+)',
        'Invoice No': r'Invoice No:\s*([\w\d]+)',
        'Date': r'Date:\s*([\w\s,]+)',
        'Bank Name': r'Bank Name:\s*([\w\s,]+)',
        'Bill to': r'Bill to:\s*([\w\s]+)',
        'Bank Account': r'Bank Account:\s*(\d{4}\s\d{4}\s\d{4})'

    }


    for field in mandatory_fields:
        pattern = patterns.get(field, None)
        if pattern:
            match = re.search(pattern, invoice_text)
            if match:
                metadata[field] = match.group(1)
            else:
                print(f"Warning: No match found for field: {field}")
                metadata[field] = None  # Or handle as required
        else:
            print(f"No pattern defined for field: {field}")

            if field == "Date":
                try:
                    invoice_date = datetime.strptime(match.group(1), "%d %B, %Y")
                    if invoice_date > datetime.now():
                        reasons.append("Invoice date cannot be in the future")
                    three_months_ago = datetime.now() - timedelta(days=90)
                    if invoice_date < three_months_ago:
                        reasons.append("Invoice date is older than 3 months")
                except ValueError:
                    reasons.append("Invalid date format (expected format: 'DD Month, YYYY')")

    # Ensure 'Hospital Name' is added to metadata if not present
    if "Hospital Name" not in metadata:
        metadata["Hospital Name"] = "Wellness Hospital"

    return metadata, reasons


def extract_invoice_items(invoice_text):
    item_pattern = item_pattern = r"\d+\.\s+((?:\([A-Za-z0-9\s]+\)\s+)?[A-Za-z0-9\s/]+(?:\(\d+\s+[A-Za-z]+\))?)\s+\$(\d+[\.,]?\d{1,2})(?:\s+\$\d+[\.,]?\d{1,2})*"

    items = []
    matches = re.findall(item_pattern, invoice_text)
    for match in matches:
        description = re.sub(r"^\d+\.\s*", "", match[0].strip())  # Remove item numbers
        amount = float(match[1].replace(',', ''))
        items.append({'DESCRIPTION': description, 'AMOUNT': amount})
    items_df = pd.DataFrame(items)
    print("Extracted Invoice Items:\n", items_df)

    return items_df


# Process invoice for fraud detection
def process_invoice(pdf_file_path):
    print("Checking for watermark...")
    if not check_watermark(pdf_file_path):
        print("Watermark not detected. Invoice cannot be processed.")
        return  # Exit if watermark is missing

    print("Extracting text from invoice...")
    invoice_text = extract_text_from_pdf(pdf_file_path)
    if not invoice_text:
        print("No text found in the invoice.")
        return  # Exit if no text is found

    print("Checking for mandatory fields...")
    metadata, mandatory_reasons = check_mandatory_fields(invoice_text)
    if mandatory_reasons:
        print("Mandatory field validation failed. Reasons:")
        for reason in mandatory_reasons:
            print(reason)
        return  # Exit if any mandatory field is missing or invalid

    print(f"Extracted Metadata: {metadata}")

    # Only proceed with fraud detection if all checks are passed
    print("Invoice validated successfully. Proceeding with fraud detection...")

    # Generate fraud detection report if checks are passed and fraud results are available
    if len(fraud_results) > 0:
        generate_combined_report(fraud_results, metadata)
    else:
        print("No fraud results to report. Skipping report generation.")


# data after cleaning
base_data = pd.read_excel("Base_data_report.xlsx")
medication_data = pd.read_excel("medication_base_report.xlsx")


# for normalizing text to ensure consistence in formating
def normalize_description(desc):
    return re.sub(r"\s+", " ", desc.lower().strip())


base_data['Normalized DESCRIPTION'] = base_data['Services provided at Wellness Hospital'].apply(normalize_description)
medication_data['Normalized DESCRIPTION'] = medication_data['Wellness Medication'].apply(normalize_description)


#%% comparison of the invoice items and their prices with that of the base cost
# fraud detection and categorization
# different colors depending on the extent of fraud.

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
    # Calculate total invoice amount
    total_invoice_amount = invoice_items['AMOUNT'].sum()

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

    #%% generation of an Excel report
    # each item is highlighted and color-coded categorized


def generate_combined_report(fraud_results, metadata):
    """
        Generates a fraud detection report with metadata and fraud categories.

        Parameters:
            fraud_results (list): A list of dictionaries with fraud detection details.
            metadata (dict): A dictionary containing metadata about the invoice.
        """

    # Clean metadata
    metadata = {key: value.replace("\n", " ") if isinstance(value, str) else value for key, value in
                metadata.items()}

    # Validate and clean fraud_results
    if not isinstance(fraud_results, list):
        print("Fraud results are not in a list format.")
        return
    fraud_results = [result for result in fraud_results if isinstance(result, dict)]

    # Check for valid data
    if not fraud_results:
        print("No valid fraud detection results to process.")
        return

    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Fraud Detection Report"

    # Add metadata
    metadata_start_row = 1
    metadata_fields = [
        ("Hospital Name", metadata.get("Hospital Name", "N/A")),
        ("Bank Name", metadata.get("Bank Name", "N/A")),
        ("Bank Account", metadata.get("Bank Account", "N/A")),
        ("Patient Name", metadata.get("Patient Name", "N/A")),
        ("Policy Number", metadata.get("policy Number", "N/A")),
        ("Invoice Number", metadata.get("Invoice No", "N/A")),
    ]


    for idx, (label, value) in enumerate(metadata_fields):
        ws[f"A{metadata_start_row + idx}"] = f"{label}:"
        ws[f"B{metadata_start_row + idx}"] = value

    # Add fraud results
    metadata_end_row = metadata_start_row + len(metadata_fields) + 1
    headers = ["Description", "Invoice Cost", "Base Cost", "Price Difference", "Fraud Category"]
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=metadata_end_row, column=col_idx, value=header)

    # Define color coding
    colors = {
        "Legitimate": "00FF00",
        "Risk": "FFA500",
        "Fraud": "FF0000",
        "Service not found in base data": "FFFF00"
    }

    # Populate fraud results
    for row_idx, result in enumerate(fraud_results, start=metadata_end_row + 1):
        ws.cell(row=row_idx, column=1, value=result.get("Description", "N/A"))
        ws.cell(row=row_idx, column=2, value=result.get("Invoice Cost", "N/A"))
        ws.cell(row=row_idx, column=3, value=result.get("Base Cost", "N/A"))
        ws.cell(row=row_idx, column=4, value=result.get("Price Difference", "N/A"))
        fraud_category = result.get("Fraud Category", "Unknown")
        ws.cell(row=row_idx, column=5, value=fraud_category)

        # Apply color
        fill_color = colors.get(fraud_category, None)
        if fill_color:
            for col_idx in range(1, ws.max_column + 1):  # Loop through all columns in the row
                ws.cell(row=row_idx, column=col_idx).fill = PatternFill(start_color=fill_color,
                                                                        end_color=fill_color, fill_type="solid")

    # Save workbook
    report_file_path = "fraud_report_with_metadata_and_categories.xlsx"
    wb.save(report_file_path)
    print(f"Fraud detection report saved successfully as '{report_file_path}'!")

    # Save as JSON
    combined_report = {
        "Metadata": metadata,
        "Fraud Detection Results": fraud_results,
    }
    json_file_path = "fraud_report_with_metadata_and_categories.json"
    with open(json_file_path, "w") as json_file:
        json.dump(combined_report, json_file, indent=4)
    print(f"Fraud detection report saved successfully as '{json_file_path}'!")

    return report_file_path, json_file_path


def save_report(metadata, fraud_results, json_file="combined_report.json"):
    # Combine Metadata and Fraud Results
    combined_report = {
        "Metadata": metadata,
        "Fraud Detection Results": fraud_results,
    }

    # Save as JSON
    with open(json_file, "w") as json_out:
        json.dump(combined_report, json_out, indent=4)
    print(f"Report saved successfully as {json_file}")

pdf_file_path = upload_file()
invoice_text = extract_text_from_pdf(pdf_file_path)
invoice_items = extract_invoice_items(invoice_text)
fraud_results = compare_invoice_with_base(invoice_items, base_data, medication_data)
process_invoice(pdf_file_path)
