import os
import sys
import logging
import pandas as pd
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.types import VARCHAR
from sqlalchemy.exc import SQLAlchemyError

# ==============================================================================
# CONFIGURATION & SETUP
# ==============================================================================

# 1. Define where this script is located so we can reliably build relative paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data_raw_src"
LOG_FILE = SCRIPT_DIR / "raw_cms_DE_SynPUF_data_loader.log"

PARAM_FILE_MAIN = SCRIPT_DIR / "raw_cms_DE_SynPUF_data_loader_parameters.csv"
PARAM_FILE_SIZES = SCRIPT_DIR / "raw_cms_DE_SynPUF_data_loader_field_size_parameters.csv"

# 2. Setup Error Handling: Clear the log file if it already exists before writing
if LOG_FILE.exists():
    try:
        LOG_FILE.unlink()
    except Exception as e:
        print(f"CRITICAL: Cannot delete old log file. {e}")
        sys.exit(1)

# 3. Configure the logging system
# This records our actions and errors to the .log file instead of printing them to the screen
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logging.info("Starting CMS DE-SynPUF data load process.")

# Load environment variables to securely get database credentials from the .env file
load_dotenv()

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_database_engine():
    """Builds the database connection and handles connection errors."""
    db_user = os.getenv("DB_USER")
    db_pass = os.getenv("DB_PASS")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "5432") # Added 5432 as a default fallback
    db_name = os.getenv("DB_NAME")
    
    url = f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    
    try:
        engine = create_engine(url)
        # Briefly test the connection to trigger any immediate errors
        with engine.connect() as conn:
            pass 
        return engine
    except Exception as e:
        # If there is a database connection issue, it should be logged.
        logging.error(f"Database Connection Issue: Cannot connect to PostgreSQL. Error: {e}")
        sys.exit(1)

def validate_field_sizes(df, max_allowed_size):
    """
    Checks the maximum string length of every column in the dataframe.
    Stops the script if any value is larger than the requested field size.
    """
    for column in df.columns:
        # Calculate the length of the longest string in the column
        # We use dropna() to ignore empty cells when measuring lengths
        max_length_found = df[column].dropna().astype(str).map(len).max()
        
        # If the column was completely empty, it will be NaN. We can skip it.
        if pd.isna(max_length_found):
            continue
            
        # Error Handling: Check if the value is too big for the database field
        if max_length_found > max_allowed_size:
            logging.error(
                f"Cannot populate field. Value is too large for the column '{column}'. "
                f"Size of the value trying to load: {int(max_length_found)}. "
                f"Size of the field: {max_allowed_size}."
            )
            sys.exit(1)

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
if __name__ == "__main__":
    
    # --- 1. VALIDATE & READ PARAMETER FILES ---
    # Error Handling: If the parameter file cannot be found then note it and stop.
    if not PARAM_FILE_MAIN.exists():
        logging.error(f"Parameter file not found: {PARAM_FILE_MAIN.name}")
        sys.exit(1)
    if not PARAM_FILE_SIZES.exists():
        logging.error(f"Parameter file not found: {PARAM_FILE_SIZES.name}")
        sys.exit(1)
        
    try:
        # Read the parameter files into pandas dataframes
        df_main_params = pd.read_csv(PARAM_FILE_MAIN)
        df_size_params = pd.read_csv(PARAM_FILE_SIZES)
        
        # Verify that all required columns exist in the main parameter file
        required_cols = ['file_name', 'table_name', 'load', 'load_rec_count']
        for col in required_cols:
            if col not in df_main_params.columns:
                raise ValueError(f"Missing required parameter column: '{col}'")
                
    except Exception as e:
        # Error Handling: Problem reading in or using the values set in the parameter file
        logging.error(f"Problem reading in or using the values set in the parameter file: {e}")
        sys.exit(1)

    # --- 2. CONNECT TO DATABASE ---
    engine = get_database_engine()
    logging.info("Successfully connected to the database.")

    # --- 3. LOOP THROUGH FILES AND LOAD ---
    # To allow multiple files to load into the same table, we track what has been created.
    # The first file will DROP the table, and subsequent files will APPEND.
    tables_created_this_run = set()
    
    for index, row in df_main_params.iterrows():
        try:
            # Extract parameters for this specific row, accounting for blank spaces
            file_name = str(row['file_name']).strip()
            table_name = str(row['table_name']).strip()
            # Allow Y or N in any casing for the load parameter
            load_flag = str(row['load']).strip().upper() 
            rec_count_raw = str(row['load_rec_count']).strip().upper()
        except Exception as e:
            # Error Handling: Problem using values set in the parameter file
            logging.error(f"Problem reading in or using the values set in the parameter file on row {index + 1}: {e}")
            sys.exit(1)

        # Use the load parameter to control if it performs the load for that specific combination
        if load_flag != 'Y':
            logging.info(f"Skipping {file_name} because 'load' parameter is set to '{load_flag}'.")
            continue
            
        file_path = DATA_DIR / file_name
        
        # Error Handling: If script cannot read files from the folder, stop and say that
        if not file_path.exists():
            logging.error(f"Cannot read files from the data_raw_src folder. Missing: {file_name}")
            sys.exit(1)

        # Parse the record count parameter ([ALL] vs [100])
        nrows_to_read = None
        if rec_count_raw != '[ALL]':
            try:
                # Remove brackets and convert to an integer
                nrows_to_read = int(rec_count_raw.replace('[', '').replace(']', ''))
            except ValueError:
                logging.error(f"Problem using parameter values: Invalid load_rec_count format '{rec_count_raw}'.")
                sys.exit(1)

        # Use the size parameters file to match the text pattern to the current file name
        field_size = None
        for _, size_row in df_size_params.iterrows():
            if str(size_row['file_name_txt']) in file_name:
                field_size = int(size_row['field_size'])
                break
                
        if not field_size:
            logging.error(f"Problem using parameter values: No field_size mapping found for {file_name}.")
            sys.exit(1)
        
        logging.info(f"Preparing to load {file_name} into {table_name}. Limit: {rec_count_raw}, Size: {field_size}.")

        # --- EXTRACT PHASE ---
        try:
            # Force everything to be read as text strings
            df = pd.read_csv(file_path, nrows=nrows_to_read, dtype=str)
        except Exception as e:
            logging.error(f"Cannot read files from the data_raw_src folder: Failed reading {file_name}. Error: {e}")
            sys.exit(1)

        # --- TRANSFORM PHASE ---
        # Create table field names based on the header field names (pandas does this by default)
        
        # Add new fields at the end of the table
        df['file_name'] = file_name
        df['load_ts'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Validation: Check that no data value exceeds the allowed field size parameter
        validate_field_sizes(df, field_size)

        # All field types should be text, with sizes set by the field_size parameter
        sql_dtypes = {col: VARCHAR(field_size) for col in df.columns}

        # --- LOAD PHASE ---
        try:
            # Determine if we should replace the table (first file) or append (subsequent files)
            if table_name in tables_created_this_run:
                action = 'append'
            else:
                action = 'replace' # This drops and recreates the table
                tables_created_this_run.add(table_name)
                
            df.to_sql(
                name=table_name,
                con=engine,
                if_exists=action, 
                index=False,
                dtype=sql_dtypes 
            )
            logging.info(f"Success: Loaded {len(df)} records into {table_name} using '{action}'.")
            
        except SQLAlchemyError as e:
            # Error Handling: Issue creating a table or populating a field, clearly noted and stopped
            logging.error(f"Issue creating a table or populating a field: Failed on {table_name}. Error: {e}")
            sys.exit(1)

    # Clean up the database connection pool
    engine.dispose()
    logging.info("Process complete. Database connection closed.")