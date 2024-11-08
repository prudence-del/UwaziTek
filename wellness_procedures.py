import pandas as pd
import pdfplumber
import re
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import tkinter as tk
from tkinter import filedialog

#%% Base data setup
# Load baseline data containing items/services offered by the hospital
file_path = 'E:/NJENGA/Downloads/synthea_sample_data_csv_latest/procedures.csv'
Base_data = pd.read_csv(file_path)

#%% Data cleaning
# Cleans and prepares baseline data by dropping unnecessary columns,
# removing duplicates, renaming columns, and formatting data types.
Base_data = Base_data.drop(['START', 'STOP', 'PATIENT', 'ENCOUNTER', 'SYSTEM', 'CODE', 'REASONCODE', 'REASONDESCRIPTION'], axis=1)
Base_data = Base_data.drop_duplicates(subset='DESCRIPTION', keep='first')
Base_data = Base_data.rename(columns={'DESCRIPTION': 'WELLNESS_HOSPITAL PROCEDURE SERVICES'})
Base_data['WELLNESS_HOSPITAL PROCEDURE SERVICES'] = Base_data['WELLNESS_HOSPITAL PROCEDURE SERVICES'].str.strip()
Base_data['BASE_COST'] = Base_data['BASE_COST'].astype(float)

#%% File upload
def upload_file():
    """Open a dialog to upload a PDF file and return the file path."""
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title="Select the invoice")
    return file_path

#%% Invoice validation
def check_mandatory_fields(invoice_text):
    """
    Validates mandatory fields in the invoice text.
    Ensures that fields like Invoice No, Policy Number, Bill To, Patient Name, and Date are present and correctly formatted.

    Parameters:

    invoice_text (str): Extracted text from the invoice.

    Returns:
    list: A list of reasons for rejection if mandatory fields are missing or invalid.
    """
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

#%% Main extraction and validation
selected_file = upload_file()
try:
    with pdfplumber.open(selected_file) as pdf:
        invoice_text = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
        print("Extracted Text:", invoice_text)

    # Run the mandatory field checks
    reasons_for_rejection = check_mandatory_fields(invoice_text)
    if reasons_for_rejection:
        print("Mandatory field check failed with the following reasons:")
        for reason in reasons_for_rejection:
            print("-", reason)
    else:
        print("Mandatory field check passed. Proceeding with item-level approval...")

except Exception as e:
    print(f"Error extracting text from PDF: {e}")

#%% Data extraction from PDF
def extracted_pdf_data(pdf_path):
    """
    Extracts item descriptions, prices, and amounts from the PDF.

    Parameters:
    pdf_path (str): The file path of the PDF invoice.

    Returns:
    pd.DataFrame: A dataframe containing Description, Price, and Amount columns.
    """
    extracted_data = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines = text.split('\n')
                for line in lines:
                    match = re.match(r'^\d+\.\s+([A-Za-z0-9\s()]+)\s+\$?([\d,.]+)\s+\$?([\d,.]+)', line)
                    if match:
                        description = match.group(1).strip()
                        price = float(match.group(2).replace(',', ''))
                        amount = float(match.group(3).replace(',', ''))
                        extracted_data.append([description, price, amount])
    return pd.DataFrame(extracted_data, columns=["Description", "Price", "Amount"])

#%% Item comparison with baseline
def compare_with_baseline(df, baseline):
    """
    Compares each item in the invoice with the baseline data to categorize as Legit, Risk, or Fraud.

    Parameters:
    df (pd.DataFrame): Dataframe containing invoice items and prices.
    baseline (pd.DataFrame): Baseline data with standard procedure names and base costs.

    Returns:
    pd.DataFrame: Dataframe with additional columns for Base Cost and Status.
    """
    results = []
    for _, row in df.iterrows():
        procedure = row["Description"]
        invoice_price = row["Price"]
        baseline_match = baseline[baseline["WELLNESS_HOSPITAL PROCEDURE SERVICES"] == procedure]
        label = "Unknown Item"
        base_cost = None

        if not baseline_match.empty:
            base_cost = baseline_match.iloc[0]["BASE_COST"]

            # Categorize based on comparison of invoice price to base cost
            if invoice_price == base_cost:
                label = "Legit"
            elif invoice_price > base_cost + 500:
                label = "Risk"
            elif invoice_price > base_cost:
                label = "Fraud"
            else:
                label = "Unknown"

        results.append({
            "Description": procedure,
            "Invoice Price": invoice_price,
            "Base Cost": base_cost,
            "Status": label
        })
    return pd.DataFrame(results)

#%% Display results in terminal
def display_results(df):
    """
    Prints each item's description, base cost, invoice price, and fraud classification in the terminal.

    Parameters:
    df (pd.DataFrame): Dataframe containing items with Invoice Price, Base Cost, and Status.
    """
    print("\nInvoice Item Classification Report:")
    print("-" * 50)
    for _, row in df.iterrows():
        description = row["Description"]
        invoice_price = row["Invoice Price"]
        base_cost = row["Base Cost"]
        status = row["Status"]

        print(f"Description: {description}")
        print(f"Base Cost: ${base_cost}")
        print(f"Invoice Price: ${invoice_price}")
        print(f"Status: {status}")
        print("-" * 50)  # number of hyphens


#%% Output the results to an Excel file
def save_to_excel(df, filename='fraud_detection_report.xlsx'):
    # Save the results DataFrame to an Excel file
    df.to_excel(filename, index=False)
    print(f"Results have been saved to {filename}")
    save_to_excel(comparison_df, filename='fraud_detection_report.xlsx')

#%% fraud categorization(color coded) will be viewed in plot form
# Visualization
# each item/procedure of the invoice will have its fraud category
def visualize_results(df):
    def assign_color(status):
        return {'Legit': 'green', 'Risk': 'red', 'Fraud': 'orange', 'Unknown': 'gray'}.get(status, 'gray')
    df['Color'] = df['Status'].apply(assign_color)
    plt.figure(figsize=(10, 6))
    plt.barh(df['Description'], df['Invoice Price'], color=df['Color'])
    plt.xlabel('Invoice Price ($)')
    plt.title('Invoice Price Comparison with Status Categorization')
    for index, value in enumerate(df['Invoice Price']):
        plt.text(value + 1, index, f"{value:.2f}", va='center')
    plt.tight_layout()
    plt.show()

#%% Execution
# Extract data and run the baseline comparison
invoice_df = extracted_pdf_data(selected_file)
comparison_df = compare_with_baseline(invoice_df, Base_data)
display_results(comparison_df)
visualize_results(comparison_df)



import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
import tkinter as tk
from tkinter import filedialog
from datetime import datetime, timedelta
import re


#%% Base data setup
# loading data with services offered in the hospital and their cost
file_path = 'E:/NJENGA/Downloads/synthea_sample_data_csv_latest/procedures.csv'
Base_data = pd.read_csv(file_path)
# reading the first 5 rows of the data
print(Base_data.head(5))
# detailed info about the data
print(Base_data.info())

#%% cleaning Base data
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


#%% invoice upload, text extract, image extract, convert text to data frame
# invoice upload
def upload_file():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title="select invoice")
    return file_path


# Function to clean up invoice text
def clean_text(text):
    # Remove extra spaces, newlines, or unwanted characters
    cleaned_text = " ".join(text.split())  # This removes extra spaces and newlines
    return cleaned_text
# Function to extract and save image (watermark) from PDF
# fitz module is crucial for: extracting images, image+text extraction from pdf
# fitz helps in modification of pdf
# Check watermark and save images if present
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

                    # Save image in 'watermarks' directory with unique name
                    image_path = f"watermark_page{page_num+1}_img{i+1}.png"
                    with open(image_path, "wb") as img_file:
                        img_file.write(image_bytes)

                    print(f"Watermark image saved as {image_path}")
                    watermark_found = True

        return watermark_found
    except Exception as e:
        print(f"Error checking watermark: {e}")
        return False

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


# Function to extract invoice items from the invoice text
def extract_invoice_items(invoice_text):
    extracted_data = []

    # Define the regex pattern to match the lines with description and two price columns
    pattern = r'^\d+\.\s+([A-Za-z0-9\s()]+)\s+\$?([\d,.]+)\s+\$?([\d,.]+)'

    # Split the text into lines for line-by-line extraction
    lines = invoice_text.split("\n")

    # Loop through each line and apply the regex
    for line in lines:
        match = re.match(pattern, line.strip())  # Strip leading/trailing spaces
        if match:
            description = match.group(1).strip()  # Clean up any extra spaces
            price = float(match.group(2).replace(',', ''))  # Convert price to float, removing commas
            amount = float(match.group(3).replace(',', ''))  # Convert amount to float, removing commas
            extracted_data.append({'Description': description, 'Price': price, 'Amount': amount})

    return extracted_data

#%%  validation of the invoices
# check before the fraud test
# mandatory fields
def check_mandatory_fields(invoice_text):
    reasons = []  # list of the reasons for rejection if the mandatory check fails

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

# Process invoice for fraud detection
def process_invoice(pdf_file_path):
    # Check for watermark presence
    if not check_watermark(pdf_file_path):
        print("Watermark not detected. Invoice cannot be processed.")
        return  # Skip fraud categorization if no watermark

    # Extract text and validate fields
    invoice_text = extract_text_from_pdf(pdf_file_path)
    if not invoice_text:
        print("No text found in the invoice.")
        return  # Skip fraud categorization if no text is extracted

    mandatory_reasons = check_mandatory_fields(invoice_text)
    if mandatory_reasons:
        print("Mandatory field validation failed. Reasons:")
        for reason in mandatory_reasons:
            print(reason)
        return  # Skip fraud categorization if mandatory fields are missing or invalid

    # Both watermark and mandatory fields present
    print("Invoice validated successfully. Proceeding with fraud detection...")

    # Extract invoice items from the invoice text
    invoice_items = extract_invoice_items(invoice_text)

    # Now compare the extracted invoice items with the base data
    fraud_results = compare_invoice_with_base(invoice_items, base_data)

    # Print the results
    print(fraud_results)


# Run the main process
pdf_file_path = upload_file()
process_invoice(pdf_file_path)


#%% fraud detection and categorization
# comparison of the invoice amount with that of the base data
# basedata in Excel form will be used
# Excel is where the mean of base_cost of unique services ia
base_data = pd.read_excel("Base_data_report.xlsx")  # Load base data file


# Function to compare invoice services with base data
def compare_invoice_with_base(invoice_items, hospital_base_data):
    fraud_detection_results = []

    # Loop through each item in the invoice
    for item in invoice_items:
        description = item['Description']
        invoice_cost = item['Amount']

        # Find the matching service in the base data (make sure the column name is correct)
        base_row = hospital_base_data[base_data['Services provided at Wellness Hospital'] == description]

        if base_row.empty:
            # If no match is found in the base data
            fraud_detection_results.append({
                'Description': description,
                'Invoice Cost': invoice_cost,
                'Base Cost': None,
                'Fraud Category': "Service not found in base data"
            })
        else:
            # If a match is found, compare the base cost
            hospital_base_cost = base_row['BASE_COST'].values[0]  # Get the base cost

            # Determine fraud category
            if invoice_cost == hospital_base_cost:
                fraud_category = "Legitimate"
            elif invoice_cost > hospital_base_cost:
                # Define a threshold for risk or fraud (e.g., 20% above the base cost)
                if invoice_cost <= hospital_base_cost * 1.2:
                    fraud_category = "Risk (Slightly above base cost)"
                else:
                    fraud_category = "Fraud (Significantly above base cost)"
            else:
                fraud_category = "Potential Underreporting (Lower than base cost)"

            # Append the result with all relevant details
            fraud_detection_results.append({
                'Description': description,
                'Invoice Cost': invoice_cost,
                'Base Cost': hospital_base_cost,
                'Fraud Category': fraud_category
            })

    return pd.DataFrame(fraud_detection_results)
# Extract invoice items from the invoice text
# Extract invoice items from the invoice text
invoice_text = extract_text_from_pdf(pdf_file_path)  # Make sure to extract text from the PDF
invoice_items = extract_invoice_items(invoice_text)

# Now compare the extracted invoice items with the base data
fraud_results = compare_invoice_with_base(invoice_items, base_data)

# Print the results
print(fraud_results)

