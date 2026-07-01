import os
import sys
import csv
import logging
import requests
import zipfile
import shutil
import re
from pathlib import Path

# ==============================================================================
# CONFIGURATION & SETUP
# ==============================================================================

# 1. Define where this script is located so we can build relative paths
SCRIPT_DIR = Path(__file__).resolve().parent

# 2. Define the exact names of the files and folders we need to interact with
LOG_FILE = SCRIPT_DIR / "raw_cms_DE_SynPUF_data_pull.log"
PARAM_FILE = SCRIPT_DIR / "raw_cms_DE_SynPUF_data_pull_select_parameters.csv"
TARGET_DIR = SCRIPT_DIR.parent / "data_raw_src"

# 3. Setup Error Handling: Clear the log file if it already exists [cite: 29]
if LOG_FILE.exists():
    try:
        LOG_FILE.unlink()
    except Exception as e:
        print(f"CRITICAL: Cannot delete old log file. Error: {e}")
        sys.exit(1)

# 4. Configure the logging system
# This tells Python to write all log messages to our specific file instead of the screen [cite: 5]
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logging.info("Starting CMS DE-SynPUF data pull process.")

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_samples_to_download():
    """Reads the parameter CSV and returns a list of sample numbers to process."""
    if not PARAM_FILE.exists():
        logging.error(f"Parameter missing: {PARAM_FILE.name} does not exist.")
        sys.exit(1)

    try:
        # Open the CSV file and read the contents
        with open(PARAM_FILE, mode='r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            
            # Grab the very first row of data and ignore the rest [cite: 32]
            first_row = next(csv_reader, None)
            
            # If the parameter is empty, log it and stop [cite: 24]
            if not first_row or not first_row.get('value') or first_row['value'].strip() == "":
                logging.error("Parameter missing: The parameter file is empty or missing the 'value' column.")
                sys.exit(1)
                
            raw_value = first_row['value'].strip()
            
            # Check if the format matches exactly [1] or [1,2,3...] using Regular Expressions
            # ^\[ means it must start with [, \d+(,\d+)* means numbers separated by commas, \]$ means it ends with ]
            if not re.match(r'^\[\d+(,\d+)*\]$', raw_value):
                logging.error(f"Format Error: Parameters in {PARAM_FILE.name} are not set correctly. Must be in [1] or [1,2,3,4,5] format. Found: {raw_value}") # [cite: 33]
                sys.exit(1)
                
            # Strip the brackets off the ends and split the string into a list of strings by the commas
            clean_string = raw_value.strip('[]')
            sample_list = clean_string.split(',')
            
            # Convert the strings to integers and validate they exist on CMS (1 through 20)
            valid_samples = []
            for num_str in sample_list:
                num = int(num_str)
                if num < 1 or num > 20:
                    logging.error(f"Invalid Parameter: Sample number {num} does not correspond to a valid CMS sample set (1-20).") # [cite: 34]
                    sys.exit(1)
                valid_samples.append(num)
                
            return valid_samples
            
    except Exception as e:
        logging.error(f"Failed to read parameter file: {e}")
        sys.exit(1)

def clear_target_directory():
    """Deletes old file copies within the data_raw_src folder[cite: 27]."""
    if TARGET_DIR.exists():
        logging.info(f"Cleaning existing files from {TARGET_DIR.name}...")
        try:
            # Loop through everything inside the target directory
            for item in TARGET_DIR.iterdir():
                # We skip hidden files like .gitkeep so Git keeps tracking the empty folder
                if item.name == '.gitkeep':
                    continue
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
        except Exception as e:
            # If we can't delete files (e.g., they are open in another program), stop and log [cite: 31]
            logging.error(f"File Lock Error: Previous files in {TARGET_DIR.name} cannot be moved or deleted. {e}")
            sys.exit(1)
    else:
        # If the directory doesn't exist at all, create it safely
        TARGET_DIR.mkdir(parents=True, exist_ok=True)

def download_and_extract_sample(sample_num):
    """Downloads the specific CMS files requested for a sample number and extracts them."""
    
    # Define the core files we need, strictly matching the requested patterns [cite: 14, 15, 16, 17]
    # We include all versions of the Beneficiary file to capture the time-varying variables 
    files_to_pull = {
        "Beneficiary_2008": f"https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/SynPUFs/Downloads/DE1_0_2008_Beneficiary_Summary_File_Sample_{sample_num}.zip",
        "Beneficiary_2009": f"https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/SynPUFs/Downloads/DE1_0_2009_Beneficiary_Summary_File_Sample_{sample_num}.zip",
        "Beneficiary_2010": f"https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/SynPUFs/Downloads/DE1_0_2010_Beneficiary_Summary_File_Sample_{sample_num}.zip",
        "Inpatient_Claims": f"https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/SynPUFs/Downloads/DE1_0_2008_to_2010_Inpatient_Claims_Sample_{sample_num}.zip",
        "Outpatient_Claims": f"https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/SynPUFs/Downloads/DE1_0_2008_to_2010_Outpatient_Claims_Sample_{sample_num}.zip"
    }
    
    for name, url in files_to_pull.items():
        zip_path = TARGET_DIR / f"{name}_Sample_{sample_num}.zip"
        logging.info(f"Connecting to CMS site to download Sample {sample_num}: {name}...")
        
        # --- 1. DOWNLOAD PHASE ---
        try:
            # Stream the download so we don't run out of RAM on large files
            with requests.get(url, stream=True, timeout=30) as response:
                response.raise_for_status() 
                
                with open(zip_path, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        file.write(chunk)
            logging.info(f"Successfully downloaded {zip_path.name}.")
            
        except requests.exceptions.RequestException as e:
            # Stop and give a clear message in the log if the site cannot be reached [cite: 30]
            logging.error(f"Connection Error: Could not connect to the site to download {name}. Error: {e}") 
            sys.exit(1)

        # --- 2. EXTRACTION PHASE ---
        logging.info(f"Unzipping {zip_path.name}...") 
        extracted_files = [] # Keep a record of what we extract in case we need to roll back
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Save the names of the files we are about to extract
                extracted_files = zip_ref.namelist()
                # Actually extract them into the target folder [cite: 26]
                zip_ref.extractall(TARGET_DIR)
            logging.info(f"Successfully extracted {zip_path.name}.")
            
        except Exception as e:
            # If zip fails, note the issue clearly, delete partials, and stop [cite: 35]
            logging.error(f"Extraction Error: Problem during the unzip process for {zip_path.name}. {e}") 
            logging.info("Rolling back: Deleting partial extracts...")
            
            for extracted_file in extracted_files:
                bad_file_path = TARGET_DIR / extracted_file
                if bad_file_path.exists():
                    bad_file_path.unlink()
                    
            if zip_path.exists():
                zip_path.unlink()
                
            logging.error("Cleanup complete. Stopping processing due to extraction failure.") 
            sys.exit(1)
            
        # --- 3. CLEANUP PHASE ---
        # If extraction was successful, delete the leftover .zip archive [cite: 26]
        if zip_path.exists():
            zip_path.unlink()
            logging.info(f"Cleaned up leftover archive: {zip_path.name}") 

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
if __name__ == "__main__":
    
    # Step 1: Read the parameter file
    samples = get_samples_to_download()
    logging.info(f"Parameter accepted. Preparing to download samples: {samples}")
    
    # Step 2: Delete old files to ensure a clean slate
    clear_target_directory()
    
    # Step 3: Loop through each requested sample number and process it
    for sample in samples:
        download_and_extract_sample(sample)
        
    logging.info("Process complete. All requested CMS DE-SynPUF data has been downloaded and extracted.")