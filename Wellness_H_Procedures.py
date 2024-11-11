import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
import tkinter as tk
from tkinter import filedialog
from datetime import datetime, timedelta
import re
from openpyxl.reader.excel import load_workbook
from openpyxl.styles import PatternFill


#%% Base data setup
# loading data with services offered in the hospital and their cost
file_path = 'E:/NJENGA/Downloads/synthea_sample_data_csv_latest/procedures.csv'
Base_data = pd.read_csv(file_path)
# reading the first 5 rows of the data
print(Base_data.head(5))
# detailed info about the data
print(Base_data.info())


#%% data cleaning
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


#%% Invoice upload, text extract, image extract, convert text to data frame
# invoice upload
def upload_file():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title="Select invoice")
    return file_path

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
                invoice_date = datetime.strptime(match.group(1), "%d %B, %Y")  # day month,year format
                print(f"Extracted Invoice Date: {invoice_date}")
                if invoice_date > datetime.now():
                    reasons.append("Invoice date cannot be in the future")
                    break
                three_months_ago = datetime.now() - timedelta(days=90)  # invoice should not be more than 3 months old
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
    mandatory_reasons = check_mandatory_fields(invoice_text)
    if mandatory_reasons:
        print("Mandatory field validation failed. Reasons:")
        for reason in mandatory_reasons:
            print(reason)
        return  # Exit if any mandatory field is missing or invalid

    # Only proceed with fraud detection if all checks are passed
    print("Invoice validated successfully. Proceeding with fraud detection...")
    invoice_items = extract_invoice_items(invoice_text)
    fraud_results = compare_invoice_with_base(invoice_items, base_data)

    # Generate fraud detection report if checks are passed and fraud results are available
    if not fraud_results.empty:
        generate_fraud_report(fraud_results)
    else:
        print("No fraud results to report. Skipping report generation.")


# data after cleaning
base_data = pd.read_excel("Base_data_report.xlsx")

# for normalizing text to ensure consistence in formating
def normalize_description(desc):
    return re.sub(r"\s+", " ", desc.lower().strip())


base_data['DESCRIPTION'] = base_data['Services provided at Wellness Hospital'].apply(normalize_description)


#%% comparison of the invoice items and their prices with that of the base cost
# fraud detection and categorization
# different colors depending on the extent of fraud.

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
            # invoice cost == or greater than base cost by 100 then green
            # invoice cost more than base cost by 3000 then risk
            # more than that is fraud
            if invoice_cost == hospital_base_cost or (
                    invoice_cost > hospital_base_cost and (invoice_cost - hospital_base_cost) <= 100):
                fraud_category = "Legitimate"

            elif invoice_cost > hospital_base_cost:
                fraud_category = "Risk" if (invoice_cost - hospital_base_cost) <= 3000 else "Fraud"
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

    # Updated function to generate the fraud detection report
    # Updated function to generate the fraud detection report


#%% generation of an Excel report
# each item is highlighted and color-coded categorized
def generate_fraud_report(fraud_detection_results):
    # Save the report to an Excel file
    report_file = "Fraud_Detection_Report.xlsx"
    fraud_detection_results.to_excel(report_file, index=False)

    # Load the workbook and select the active sheet
    workbook = load_workbook(report_file)
    sheet = workbook.active

    # Define colors for each fraud category
    colors = {
        "Legitimate": "00FF00",  # Green
        "Risk": "FFA500",  # Orange
        "Fraud": "FF0000",  # Red
        "Service not found in base data": "FF FF00"  # Yellow for unmatched services
    }

    # Apply color to each row based on fraud category
    for row in range(2, sheet.max_row + 1):  # Skip the header row
        fraud_category = sheet.cell(row=row, column=5).value  # 5th column (E)
        fill_color = colors.get(fraud_category, "FFFFFF")  # Default to white if no match
        fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")

        # Apply fill color to all columns in the row
        for col in range(1, sheet.max_column + 1):
            sheet.cell(row=row, column=col).fill = fill

    # Save the workbook with color formatting
    workbook.save(report_file)
    print(f"Fraud report saved as {report_file} with color-coded categories.")
    return report_file


pdf_file_path = upload_file()
invoice_text = extract_text_from_pdf(pdf_file_path)
invoice_items = extract_invoice_items(invoice_text)
fraud_results = compare_invoice_with_base(invoice_items, base_data)
process_invoice(pdf_file_path)


