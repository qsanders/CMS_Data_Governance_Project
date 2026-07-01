import os
import sys
import csv
import logging
import datetime
import pandas as pd
import psycopg2
import pyodbc
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# ==============================================================================
# SETUP: Paths and Logging
# ==============================================================================

# 1. Define where our files live based on the project structure
# We assume the script is running from inside the 'code_scripts' folder.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# data_raw_src is expected to be sitting next to code_scripts
DATA_RAW_DIR = os.path.join(SCRIPT_DIR, '..', 'data_raw_src')

# Define file names
LOG_FILE = os.path.join(SCRIPT_DIR, 'raw_cms_DE_SynPUF_data_profiling.log')
PARAM_FILE = os.path.join(SCRIPT_DIR, 'raw_cms_DE_SynPUF_data_profiling_parameters.csv')
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'raw_cms_DE_SynPUF_data_profiling_results.csv')
DB_FILE = os.path.join(SCRIPT_DIR, 'profiling_database.sqlite')

# 2. Configure Logging
# The prompt explicitly requires deleting the log file if it exists before creating a new one
if os.path.exists(LOG_FILE):
    try:
        os.remove(LOG_FILE)
    except Exception as e:
        print(f"Warning: Could not delete old log file: {e}")

# We use filemode='w' to OVERWRITE (clear out) the existing log file every time the script starts.
logging.basicConfig(
    filename=LOG_FILE,
    filemode='w', 
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
# Create a logger object we can use throughout the code
logger = logging.getLogger()
logger.info("Script started. Log file has been cleared and initialized.")

# ==============================================================================
# STEP 1: Read the Parameter File
# ==============================================================================

# We will store our parameters in a dictionary (key-value pairs)
# Example: {'null_cnt': True, 'space_cnt': False}
run_params = {}

# Check if the parameter file exists before trying to open it
if not os.path.exists(PARAM_FILE):
    logger.error(f"CRITICAL ERROR: Parameter file not found at {PARAM_FILE}. Stopping script.")
    sys.exit(1) # Stop the script entirely with an error code of 1

try:
    # Open the parameter file and read it using the csv library
    with open(PARAM_FILE, mode='r', encoding='utf-8') as p_file:
        csv_reader = csv.DictReader(p_file)
        # Loop through each row in the CSV
        for row in csv_reader:
            # Clean up the text: remove spaces and make it lowercase to handle any casing
            par_name = row['Par_name'].strip().lower()
            run_switch = row['run_switch'].strip().lower()
            
            # If the switch is 'y', set it to True in our dictionary. Otherwise, False.
            if run_switch == 'y':
                run_params[par_name] = True
            else:
                run_params[par_name] = False
    logger.info("Parameter file successfully read and processed.")
except Exception as e:
    # Catch any reading/parsing errors, log them, and stop the script.
    logger.error(f"CRITICAL ERROR: Failed to read or parse parameter file. Details: {e}")
    sys.exit(1)

# ==============================================================================
# STEP 2: Setup Output File Structure
# ==============================================================================

# These are the standard fields required by the specifications that do NOT have a parameter
base_fields = [
    'file_name', 'file_num', 'field_name', 'field_num', 'cat1', 'cat2', 'cat3', 'cat4', 'cat5',
    'start_dt', 'end_dt', 'rec_cnt'
]

# These are the metric fields that MIGHT be turned on or off by the parameter file.
# The prompt states the output file should have all fields listed in the table, 
# so we will write headers for all of them.
metric_fields = [
    'null_cnt', 'null_cnt_pct', 'space_cnt', 'space_cnt_pct', 
    'spchr_cnt', 'spchr_cnt_pct', 'alpnmc_cnt', 'alpnmc_cnt_pct', 
    'numrc_cnt', 'numrc_cnt_pct', 'date_cnt', 'date_cnt_pct', 
    'curr_cnt', 'curr_cnt_pct', 'negcurr_cnt', 'negcurr_cnt_pct', 
    'poscurr_cnt', 'poscurr_cnt_pct', 'mdlspce_cnt', 'mdlspce_cnt_pct', 
    'mdldash_cnt', 'mdldash_cnt_pct', 'min_len', 'min_len_pct', 
    'max_len', 'max_len_pct', 'ledspc', 'ledspc_pct', 'uniqu', 'uniqu_pct'
]

all_output_headers = base_fields + metric_fields

# Delete the old output file if it exists, so we start completely fresh
if os.path.exists(OUTPUT_FILE):
    os.remove(OUTPUT_FILE)
    logger.info(f"Old output file deleted: {OUTPUT_FILE}")

# Create the new output file and write the header row
try:
    with open(OUTPUT_FILE, mode='w', newline='', encoding='utf-8') as out_file:
        writer = csv.writer(out_file)
        writer.writerow(all_output_headers)
    logger.info("New output results file created with headers.")
except Exception as e:
    logger.error(f"CRITICAL ERROR: Could not create output file. Details: {e}")
    sys.exit(1)

# ==============================================================================
# STEP 3: Data Profiling Logic
# ==============================================================================

# Check if the raw data directory exists and is explicitly readable
if not os.path.exists(DATA_RAW_DIR) or not os.access(DATA_RAW_DIR, os.R_OK):
    logger.error(f"CRITICAL ERROR: Cannot read files from the data folder at {DATA_RAW_DIR}. Stopping script.")
    sys.exit(1)

# Get a list of all CSV files in the data directory
raw_files = [f for f in os.listdir(DATA_RAW_DIR) if f.endswith('.csv')]
if not raw_files:
    logger.warning("No CSV files found in the data_raw_src folder to profile.")

# Initialize a counter for our files (Starts at 1 for the first file)
file_num = 1

# Loop over every CSV file found
for file_name in raw_files:
    logger.info(f"Starting to process file: {file_name} (File Number: {file_num})")
    
    # --- Category 1 Logic (cat1) ---
    # We turn the file name to lowercase to check for specific words regardless of casing
    file_name_lower = file_name.lower()
    if "_outpatient_claims_" in file_name_lower:
        cat1 = "outpatient_claims"
    elif "beneficiary" in file_name_lower:
        cat1 = "beneficiary"
    elif "_inpatient_claims_" in file_name_lower:
        cat1 = "_inpatient_claims_"
    else:
        cat1 = ""
    
    # Load the raw data file using pandas (treat all columns as strings so we can check character counts)
    file_path = os.path.join(DATA_RAW_DIR, file_name)
    try:
        # We use dtype=str so pandas doesn't accidentally change "0123" into the number 123
        df = pd.read_csv(file_path, dtype=str)
    except Exception as e:
        logger.error(f"Error reading file {file_name}: {e}")
        continue # Skip to the next file if this one fails
    
    # rec_cnt is total rows excluding header. Pandas len(df) gets exactly this.
    rec_cnt = len(df)
    
    # Initialize a counter for the fields/columns
    field_num = 1
    
    # Loop over every column (field) in the dataframe
    for col_name in df.columns:
        logger.info(f"Profiling field: {col_name} (Field Number: {field_num})")
        
        # Capture the exact start time of profiling this specific field
        start_dt = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # We extract just this column's data as a pandas Series, replacing actual Nulls with python None
        col_data = df[col_name]
        
        # --- Pre-calculate some basic arrays to make counting faster ---
        # A list of booleans representing whether a row is null (NaN or empty)
        is_null_mask = col_data.isna() | (col_data == '')
        
        # A list of the valid (non-null) strings in this column to check text patterns
        valid_data = col_data.dropna()
        valid_data = valid_data[valid_data != ''] 
        
        # Create a dictionary to hold this field's results. 
        # We start by initializing everything to empty strings or 0.
        results = {header: '' for header in all_output_headers}
        
        # Populate the base information
        results['file_name'] = file_name
        results['file_num'] = file_num
        results['field_name'] = col_name
        results['field_num'] = field_num
        results['cat1'] = cat1
        results['start_dt'] = start_dt
        results['rec_cnt'] = rec_cnt
        
        # ---------------------------------------------------------
        # Helper Function to handle Percentages
        # ---------------------------------------------------------
        def calc_pct(count, total):
            if total == 0:
                return 0.0
            # (count / total) * 100 rounded to 2 decimal places
            return round((count / total) * 100, 2)
            
        # ---------------------------------------------------------
        # Profiling Checks (Controlled by run_params)
        # ---------------------------------------------------------
        
        # Null Counts
        if run_params.get('null_cnt', False):
            null_count = is_null_mask.sum() # sum() counts the True values
            results['null_cnt'] = null_count
            if run_params.get('null_cnt_pct', False):
                results['null_cnt_pct'] = calc_pct(null_count, rec_cnt)
                
        # Space Counts (Value is nothing but spaces)
        if run_params.get('space_cnt', False):
            space_count = valid_data.str.isspace().sum()
            results['space_cnt'] = space_count
            if run_params.get('space_cnt_pct', False):
                results['space_cnt_pct'] = calc_pct(space_count, rec_cnt)
                
        # Special Character Counts (Contains anything other than letters, numbers, or spaces)
        if run_params.get('spchr_cnt', False):
            # regex [^a-zA-Z0-9\s] means "Not a-z, A-Z, 0-9, or whitespace"
            spchr_count = valid_data.str.contains(r'[^a-zA-Z0-9\s]', regex=True, na=False).sum()
            results['spchr_cnt'] = spchr_count
            if run_params.get('spchr_cnt_pct', False):
                results['spchr_cnt_pct'] = calc_pct(spchr_count, rec_cnt)
                
        # Alphanumeric Counts
        if run_params.get('alpnmc_cnt', False):
            alpnmc_count = valid_data.str.isalnum().sum()
            results['alpnmc_cnt'] = alpnmc_count
            if run_params.get('alpnmc_cnt_pct', False):
                results['alpnmc_cnt_pct'] = calc_pct(alpnmc_count, rec_cnt)
                
        # Numeric Counts
        if run_params.get('numrc_cnt', False):
            # Check if it's strictly digits, or represents a numeric float value
            # regex ^[-+]?\d*\.?\d+$ captures decimals and negatives
            numrc_count = valid_data.str.match(r'^[-+]?\d*\.?\d+$', na=False).sum()
            results['numrc_cnt'] = numrc_count
            if run_params.get('numrc_cnt_pct', False):
                results['numrc_cnt_pct'] = calc_pct(numrc_count, rec_cnt)
                
        # Date Counts
        if run_params.get('date_cnt', False):
            # pandas to_datetime tries to parse dates. Coerce turns failures into NaT (Not a Time).
            parsed_dates = pd.to_datetime(valid_data, errors='coerce', format='mixed')
            date_count = parsed_dates.notna().sum()
            results['date_cnt'] = date_count
            if run_params.get('date_cnt_pct', False):
                results['date_cnt_pct'] = calc_pct(date_count, rec_cnt)
                
        # Currency Counts
        if run_params.get('curr_cnt', False) or run_params.get('negcurr_cnt', False) or run_params.get('poscurr_cnt', False):
            # Look for strings starting with $ (or -$ or ($)) followed by digits/commas/decimals
            # Example: $100.00, -$50, ($20.50)
            is_curr = valid_data.str.match(r'^\s*\(?-?\$[0-9,]+(\.[0-9]{2})?\)?\s*$', na=False)
            
            if run_params.get('curr_cnt', False):
                curr_count = is_curr.sum()
                results['curr_cnt'] = curr_count
                if run_params.get('curr_cnt_pct', False):
                    results['curr_cnt_pct'] = calc_pct(curr_count, rec_cnt)
                    
            if run_params.get('negcurr_cnt', False):
                # Negative currencies usually have a '-' or are wrapped in '(' ')'
                neg_curr_count = (is_curr & valid_data.str.contains(r'[-()]', regex=True)).sum()
                results['negcurr_cnt'] = neg_curr_count
                if run_params.get('negcurr_cnt_pct', False):
                    results['negcurr_cnt_pct'] = calc_pct(neg_curr_count, rec_cnt)
                    
            if run_params.get('poscurr_cnt', False):
                pos_curr_count = (is_curr & ~valid_data.str.contains(r'[-()]', regex=True)).sum()
                results['poscurr_cnt'] = pos_curr_count
                if run_params.get('poscurr_cnt_pct', False):
                    results['poscurr_cnt_pct'] = calc_pct(pos_curr_count, rec_cnt)
                    
        # Middle Space Count
        if run_params.get('mdlspce_cnt', False):
            # A space in the middle means it contains a space after we strip the outer edges
            mdlspce_count = valid_data.str.strip().str.contains(' ', regex=False).sum()
            results['mdlspce_cnt'] = mdlspce_count
            if run_params.get('mdlspce_cnt_pct', False):
                results['mdlspce_cnt_pct'] = calc_pct(mdlspce_count, rec_cnt)
                
        # Middle Dash Count
        if run_params.get('mdldash_cnt', False):
            # Strip ends, then look for a dash
            mdldash_count = valid_data.str.strip().str.contains('-', regex=False).sum()
            results['mdldash_cnt'] = mdldash_count
            if run_params.get('mdldash_cnt_pct', False):
                results['mdldash_cnt_pct'] = calc_pct(mdldash_count, rec_cnt)
                
        # Length profiling (Min/Max Lengths)
        if len(valid_data) > 0 and (run_params.get('min_len', False) or run_params.get('max_len', False)):
            lengths = valid_data.str.len()
            min_val = lengths.min()
            max_val = lengths.max()
            
            if run_params.get('min_len', False):
                min_len_count = (lengths == min_val).sum()
                results['min_len'] = min_len_count
                if run_params.get('min_len_pct', False):
                    results['min_len_pct'] = calc_pct(min_len_count, rec_cnt)
                    
            if run_params.get('max_len', False):
                max_len_count = (lengths == max_val).sum()
                results['max_len'] = max_len_count
                if run_params.get('max_len_pct', False):
                    results['max_len_pct'] = calc_pct(max_len_count, rec_cnt)
                    
        # Leading Space Count
        if run_params.get('ledspc', False):
            ledspc_count = valid_data.str.startswith(' ', na=False).sum()
            results['ledspc'] = ledspc_count
            if run_params.get('ledspc_pct', False):
                results['ledspc_pct'] = calc_pct(ledspc_count, rec_cnt)
                
        # Unique Value Count
        if run_params.get('uniqu', False):
            unique_count = valid_data.nunique()
            results['uniqu'] = unique_count
            if run_params.get('uniqu_pct', False):
                results['uniqu_pct'] = calc_pct(unique_count, rec_cnt)

        # ---------------------------------------------------------
        # Finalize and Save Field Results
        # ---------------------------------------------------------
        # Capture the exact end time now that all checks are done
        results['end_dt'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Append this field's result row to the output CSV
        try:
            with open(OUTPUT_FILE, mode='a', newline='', encoding='utf-8') as out_file:
                writer = csv.DictWriter(out_file, fieldnames=all_output_headers)
                writer.writerow(results)
        except Exception as e:
            logger.error(f"Error writing results for field {col_name} to output file: {e}")
            
        field_num += 1
        
    file_num += 1

logger.info("Finished profiling all files. Output file generated.")


# ==============================================================================
# STEP 4: Database Table Creation and Loading
# ==============================================================================
logger.info("Connecting to database and preparing to load results.")

# 1. Pull the unified configuration directly from the .env file
TARGET_DB = os.getenv('TARGET_DB', 'postgres').lower()
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT') 
DB_NAME = os.getenv('DB_NAME', 'cms_data_governance')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')

try:
    # 2. Establish connection based on the target flag
    if TARGET_DB == 'postgres':
        # Default port to 5432 if missing
        port = DB_PORT if DB_PORT else '5432' 
        conn = psycopg2.connect(
            host=DB_HOST,
            port=port,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        placeholder = "%s"
        
    elif TARGET_DB == 'sqlserver':
        # Default port to 1433 if missing, formatted for the connection string
        port_str = f",{DB_PORT}" if DB_PORT else ",1433"
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 18 for SQL Server};'
            f'SERVER={DB_HOST}{port_str};'
            f'DATABASE={DB_NAME};'
            f'UID={DB_USER};'
            f'PWD={DB_PASS};'
            'TrustServerCertificate=yes;'
        )
        placeholder = "?"
        
    else:
        raise ValueError(f"Invalid TARGET_DB specified in .env: {TARGET_DB}")
        
    cursor = conn.cursor()
    
    # 3. Drop and Create Table
    table_name = "raw_cms_profile"
    cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
    
    columns_sql = ", ".join([f"{header} VARCHAR(80)" for header in all_output_headers])
    create_table_sql = f"CREATE TABLE {table_name} ({columns_sql})"
    
    cursor.execute(create_table_sql)
    conn.commit() 
    
    logger.info(f"Database table '{table_name}' dropped (if existed) and recreated in {TARGET_DB}.")
    
    # 4. Load the Data
    with open(OUTPUT_FILE, mode='r', encoding='utf-8') as result_file:
        csv_reader = csv.reader(result_file)
        headers = next(csv_reader) 
        
        # Build the insert string using the correct placeholder
        placeholders = ", ".join([placeholder for _ in all_output_headers])
        insert_sql = f"INSERT INTO {table_name} VALUES ({placeholders})"
        
        for row_idx, row in enumerate(csv_reader):
            
            # Force row length match
            if len(row) > len(all_output_headers):
                row = row[:len(all_output_headers)]
            elif len(row) < len(all_output_headers):
                row.extend([''] * (len(all_output_headers) - len(row)))

            # Check Data Sizes
            for col_idx, val in enumerate(row):
                val_str = str(val)
                if len(val_str) > 80:
                    field_name = all_output_headers[col_idx]
                    logger.error(
                        f"CRITICAL DB ERROR: Size of value '{val_str}' is {len(val_str)}, "
                        f"exceeding field size 80 for '{field_name}'."
                    )
                    raise ValueError("Field size exceeded 80 characters.")
            
            cursor.execute(insert_sql, row)
            
    # Commit the inserts
    conn.commit()
    logger.info(f"All data successfully loaded into {TARGET_DB}.")

except (psycopg2.Error, pyodbc.Error) as e:
    logger.error(f"CRITICAL ERROR: Database issue. Details: {e}")
    sys.exit(1)
except ValueError as ve:
    logger.error("Process stopped due to data size violation or invalid DB target.")
    sys.exit(1)
except Exception as e:
    logger.error(f"CRITICAL ERROR: Unexpected issue. Details: {e}")
    sys.exit(1)
finally:
    if 'conn' in locals() and conn:
        conn.close()
        
logger.info("Data profiling script completed successfully.")