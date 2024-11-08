import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
import tkinter as tk
from tkinter import filedialog
from datetime import datetime, timedelta
import re

#%% Base data setup
file_path = 'E:/NJENGA/Downloads/synthea_sample_data_csv_latest/procedures.csv'
Base_data = pd.read_csv(file_path)
Base_data = Base_data.drop(
    ['START', 'STOP', 'PATIENT', 'ENCOUNTER', 'SYSTEM', 'CODE', 'REASONCODE', 'REASONDESCRIPTION'], axis=1)
Base_data = Base_data.drop_duplicates(subset=['DESCRIPTION', 'BASE_COST'], keep='first')
Base_data = Base_data.groupby('DESCRIPTION', as_index=False).agg({'BASE_COST': 'mean'})
Base_data['BASE_COST'] = Base_data['BASE_COST'].map(lambda x: f"{x:.2f}")
Base_data = Base_data.rename(columns={'DESCRIPTION': 'Services provided at Wellness Hospital'})
output_file_name = 'Base_data_report.xlsx'
Base_data.to_excel(output_file_name, index=False)
print(f"Report successfully saved to the current directory as {output_file_name}\n")

#%% Invoice upload, text extract, image extract, convert text to data frame
def upload_file():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title="Select invoice")
    return file_path

def clean_text(text):
    cleaned_text = " ".join(text.split())
    return cleaned_text

# Function to extract text from the PDF
def extract_text_from_pdf(pdf_invoice_path):
    try:
        # Open the PDF with pdfplumber
        with pdfplumber.open(pdf_invoice_path) as pdf:
            # Extract text from all pages of the PDF
            invoice_text = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])

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
                    image_path = f"watermark_page{page_num+1}_img{i+1}.png"
                    with open(image_path, "wb") as img_file:
                        img_file.write(image_bytes)
                    print(f"Watermark image saved as {image_path}")
                    watermark_found = True
        return watermark_found
    except Exception as e:
        print(f"Error checking watermark: {e}")
        return False

def check_mandatory_fields(invoice_text):
    reasons = []
    required_fields = {
        "Invoice No": r"Invoice No:\s*([A-Za-z0-9]+)",
        "Policy Number": r"[Pp]olicy\s*[Nn]umber:\s*([\w\-]+)",
        "Bill to": r"Bill to:\s*(.*)",
        "Patient Name": r"Patient Name:\s*(.*)",
        "Date": r"Date:\s*(\d{1,2}\s\w+,\s\d{4})"
    }
    for field, pattern in required_fields.items():
        match = re.search(pattern, invoice_text, re.IGNORECASE)
        if not match:
            reasons.append(f"Missing field: {field}")
        elif field == "Date":
            try:
                invoice_date = datetime.strptime(match.group(1), "%d %B, %Y")
                print(f"Extracted Invoice Date: {invoice_date}")
                if invoice_date > datetime.now():
                    reasons.append("Invoice date cannot be in the future")
                    break
                three_months_ago = datetime.now() - timedelta(days=90)
                if invoice_date < three_months_ago:
                    reasons.append("Invoice date is older than 3 months")
            except ValueError:
                reasons.append("Invalid date format (expected format: 'DD Month, YYYY')")
    return reasons

def extract_invoice_items(invoice_text):
    item_pattern = r"\d+\.\s+([\w\s]+)\s+\$([\d,]+(?:\.\d{1,2})?)"
    items = []
    matches = re.findall(item_pattern, invoice_text)
    for match in matches:
        description = re.sub(r"^\d+\.\s*", "", match[0].strip())  # Remove item numbers
        amount = float(match[1].replace(',', ''))
        items.append({'DESCRIPTION': description, 'AMOUNT': amount})
    items_df = pd.DataFrame(items)
    print("Extracted Invoice Items:")
    print(items_df)
    return items_df

def process_invoice(pdf_file_path):
    print("Checking for watermark...")
    if not check_watermark(pdf_file_path):
        print("Watermark not detected. Invoice cannot be processed.")
        return

    print("Extracting text from invoice...")
    invoice_text = extract_text_from_pdf(pdf_file_path)
    if not invoice_text:
        print("No text found in the invoice.")
        return

    print("Checking for mandatory fields...")
    mandatory_reasons = check_mandatory_fields(invoice_text)
    if mandatory_reasons:
        print("Mandatory field validation failed. Reasons:")
        for reason in mandatory_reasons:
            print(reason)
        return

    print("Invoice validated successfully. Proceeding with fraud detection...")
    invoice_items = extract_invoice_items(invoice_text)
    fraud_results = compare_invoice_with_base(invoice_items, base_data)
    print(fraud_results)

base_data = pd.read_excel("Base_data_report.xlsx")

def normalize_description(desc):
    return re.sub(r"\s+", " ", desc.lower().strip())

base_data['DESCRIPTION'] = base_data['Services provided at Wellness Hospital'].apply(normalize_description)


def compare_invoice_with_base(invoice_items, hospital_base_data):
    fraud_detection_results = []
    for _, item in invoice_items.iterrows():
        description = normalize_description(item['DESCRIPTION'])
        invoice_cost = item['AMOUNT']

        # Locate the base cost row in the hospital data
        base_row = hospital_base_data[hospital_base_data['DESCRIPTION'] == description]

        if base_row.empty:
            # If service is not found in the base data
            fraud_detection_results.append({
                'Description': item['DESCRIPTION'],
                'Invoice Cost': invoice_cost,
                'Base Cost': None,
                'Price Difference': None,
                'Fraud Category': "Service not found in base data"
            })
        else:
            # Base cost retrieved
            hospital_base_cost = float(base_row['BASE_COST'].values[0])
            price_difference = invoice_cost - hospital_base_cost

            # Determine fraud category based on the price difference
            if invoice_cost == hospital_base_cost:
                fraud_category = "Legitimate"
            elif invoice_cost > hospital_base_cost:
                fraud_category = "Risk" if invoice_cost <= hospital_base_cost * 1.2 else "Fraud"
            else:
                fraud_category = "Potential Underreporting"

            # Append result with the new price difference column
            fraud_detection_results.append({
                'Description': item['DESCRIPTION'],
                'Invoice Cost': invoice_cost,
                'Base Cost': hospital_base_cost,
                'Price Difference': price_difference,
                'Fraud Category': fraud_category
            })

    return pd.DataFrame(fraud_detection_results)


pdf_file_path = upload_file()
process_invoice(pdf_file_path)
