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



