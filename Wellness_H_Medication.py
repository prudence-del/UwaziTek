
import pandas as pd



#%% medication data setup
files_path = 'E:/NJENGA/Downloads/synthea_sample_data_csv_latest/medications.csv'
medication_data = pd.read_csv(files_path)
# data info
print(medication_data.head())
print(medication_data.info())

#%% cleaning the data
# dropping unnecessary columns
# axis = 1 for columns while axis = 0 is for dropping rows
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
medication_data = medication_data.groupby('Wellness Medication', as_index=False) .agg({'BASE_COST': 'mean'})

# converting cost column to 2 decimal places
medication_data['BASE_COST'] = medication_data['BASE_COST'].map(lambda x: f"{x:.2f}")

# saving the output as an Excel file
report_file_name = 'medication_base_report.xlsx'
medication_data.to_excel(report_file_name, index=False)
print(f"report saved successfully: {report_file_name}")

