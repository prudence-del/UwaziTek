import pandas as pd
import tkinter as tk  # GUI library for desktop application
from tkinter import filedialog
import pdfplumber
import re
import matplotlib.pyplot as plt
from datetime import datetime

# Load baseline data from CSV
file_path = 'E:/NJENGA/Downloads/synthea_sample_data_csv_latest/procedures.csv'
Base_data = pd.read_csv(file_path)

# Dropping unnecessary columns
Base_data = Base_data.drop(
    ['START', 'STOP', 'PATIENT', 'ENCOUNTER', 'SYSTEM', 'CODE', 'REASONCODE', 'REASONDESCRIPTION'], axis=1)

# Data cleaning: removing duplicates
initial_rows = len(Base_data)
print(f"Initial rows: {initial_rows}")
Base_data = Base_data.drop_duplicates(subset='DESCRIPTION', keep='first')

# Aggregate the base costs grouped by DESCRIPTION
Base_data_aggregated = Base_data.groupby('DESCRIPTION', as_index=False).agg({'BASE_COST': 'mean'})

# Rename columns
Base_data = Base_data.rename(columns={'DESCRIPTION': 'WELLNESS_HOSPITAL PROCEDURE SERVICES'})

# Strip spaces from string cells
Base_data['WELLNESS_HOSPITAL PROCEDURE SERVICES'] = Base_data['WELLNESS_HOSPITAL PROCEDURE SERVICES'].str.strip()

# Convert BASE_COST to currency format
Base_data['BASE_COST'] = Base_data['BASE_COST'].apply(lambda x: f"${x:.2f}")

# Remove "(procedure)" from each service description
Base_data['WELLNESS_HOSPITAL PROCEDURE SERVICES'] = Base_data['WELLNESS_HOSPITAL PROCEDURE SERVICES'].str.replace(
    r"\s*\(procedure\)$", "", regex=True)

print(f"Data after cleaning:\n{Base_data}")


# Function to upload file
def upload_file():
    root = tk.Tk()
    root.withdraw()
    files_path = filedialog.askopenfilename(title="Select the invoice")
    return files_path


selected_file = upload_file()
extracted_data = []
print(f"You selected: {selected_file}")

# Extracting text from the uploaded PDF file
try:
    with pdfplumber.open(selected_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:  # Check if text extraction was successful
                lines = text.split('\n')
                print(text)
                for line in lines:
                    # Improved regex pattern to capture description, price, and amount
                    match = re.match(r'^\d+\.\s+([A-Za-z0-9\s()]+)\s+\$?([\d,.]+)\s+\$?([\d,.]+)', line)
                    if match:
                        description = match.group(1).strip()
                        price = float(match.group(2).replace(',', ''))
                        amount = float(match.group(3).replace(',', ''))
                        extracted_data.append([description, price, amount])
            else:
                print("No text extracted from this page.")

    # Create the DataFrame
    invoice_DataFrame = pd.DataFrame(extracted_data, columns=["Description", "Price", "Amount"])
    print(invoice_DataFrame)

except Exception as e:
    print(f"Error extracting text from PDF: {e}")


# Approval/authentication of the invoices
def approve_invoice(invoice):
    reasons = []

    try:
        # Mandatory fields check
        mandatory_fields = ['Invoice Number', 'Description', 'Price', 'Date', 'Policy Number', 'Patient Name', 'Status']
        for field in mandatory_fields:
            if field not in invoice or pd.isnull(invoice[field]) or invoice[field] == '':
                reasons.append(f"Missing mandatory field: {field}")

        # Ensure price is a positive number
        if invoice['Price'] <= 0:
            reasons.append(f"invalid Price: Must be a positive number")

            # Check if the invoice date is within a valid format and range
        date_str = invoice.get('Date', '')
        try:
            invoice_date = datetime.strptime(date_str, "%d %B, %Y")
            if (datetime.now() - invoice_date).days > 90:  # 90 days = approx. 3 months
                reasons.append("Invoice Date: older than 3 months")
        except ValueError:
            reasons.append(f"Invalid Date format")

        # Only process invoices with "Approved" status
        if invoice['Status'] != 'Approved':
            reasons.append(f"Status not 'Approved'")

        # return approval status and reasons
        if reasons:
            return False, reasons  # not approved with reasons
        else:
            return True, []  # Approved, no issues

    except Exception as e:
        print(f"Error in invoice approval: {e}")
        return False, [f"Unexpected error: {e}"]  # Capture unexpected errors


# Check if each row in the invoice DataFrame is approved
invoice_DataFrame['Approved'] = invoice_DataFrame.apply(approve_invoice, axis=1)

# Filter only the approved invoices
approved_invoices = invoice_DataFrame[invoice_DataFrame['Approved'] == True]
if approved_invoices.empty:
    print("No approved invoices to process.")
else:
    # Proceed with comparison for approved invoices only
    baseline_df = Base_data.copy()
    baseline_df['BASE_COST'] = baseline_df['BASE_COST'].replace({'\$': '', '': ''}, regex=True).astype(float)

    # Clean the procedure names in the approved invoice DataFrame
    approved_invoices['Description'] = approved_invoices['Description'].str.replace(r'\s*\(procedure\)', '', regex=True)

    # List to store comparison results
    comparison_results = []

    # Loop through each item in the approved invoices DataFrame
    for index, row in approved_invoices.iterrows():
        procedure = row["Description"]
        invoice_price = row["Price"]

        # Find matching procedure in the baseline data
        baseline_match = baseline_df[baseline_df["WELLNESS_HOSPITAL PROCEDURE SERVICES"] == procedure]

        # Default value for items not found
        label = "Unknown Item"

        if not baseline_match.empty:
            base_cost = baseline_match.iloc[0]["BASE_COST"]

            # Compare prices according to the criteria
            if invoice_price == base_cost:
                label = "Legit"
            elif invoice_price >= base_cost + 300:
                label = "Risk"
            elif invoice_price > base_cost:
                label = "Fraud"
            else:
                label = "Unknown"  # To catch any unexpected values

            # Append results with the label and cost details
            comparison_results.append({
                "Description": procedure,
                "Invoice Price": invoice_price,
                "Base Cost": base_cost,
                "Status": label
            })
        else:
            # If the procedure is not found in baseline data, label as "Unknown Item"
            comparison_results.append({
                "Description": procedure,
                "Invoice Price": invoice_price,
                "Base Cost": None,
                "Status": label
            })

    # Convert comparison results to a DataFrame
    comparison_df = pd.DataFrame(comparison_results)

    # Display the comparison results
    print(comparison_df)

    # Color code categorization for visualization
    report_df = comparison_df[comparison_df['Status'].isin(['Legit', 'Fraud', 'Risk'])]


    # Function to assign colors based on the status
    def assign_color(status):
        if status == 'Legit':
            return 'green'
        elif status == 'Fraud':
            return 'orange'
        elif status == 'Risk':
            return 'red'
        return 'gray'  # Default color for anything else


    # Color categorization
    report_df['Color'] = report_df['Status'].apply(assign_color)

    # Bar plot for visualization
    plt.figure(figsize=(10, 6))
    plt.barh(report_df['Description'], report_df['Invoice Price'], color=report_df['Color'])
    plt.xlabel('Invoice Price ($)')
    plt.title('Invoice Price Comparison with Status Categorization')
    plt.axvline(0, color='black', linewidth=0.5)  # Adding a line at x=0 for reference

    # Adding text labels on the bars
    for index, value in enumerate(report_df['Invoice Price']):
        plt.text(value + 1, index, f"{value:.2f}", va='center')

    plt.tight_layout()
    plt.show()
