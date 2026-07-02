
## Source Information

Data Asset Documentation: CMS DE-SynPUF

Data Source: Centers for Medicare & Medicaid Services (CMS), U.S. Department of Health & Human Services.			

License / Terms of Use: Public Domain. No Data Use Agreement (DUA) is required. Data is provided as a Synthetic Public Use File (SynPUF).			

Retrieval Date: [INSERT DATE: e.g., 2026-06-26]			

Known Limitations: 
1. Synthetic Origin: Data represents realistic patterns but is algorithmically generated. It does not represent actual Medicare beneficiaries.

2. No Clinical Validity: Data is intended for software testing and methodology development. It should not be used for clinical or economic research, as it may lack the statistical variance of real-world claims.

3. Data Coarsening: Data has been mathematically ""coarsened"" (e.g., age ranges, geographic aggregation) to protect privacy, which may obscure small-sample patterns.			

Raw Data Location: [CMS Official SynPUF Page](https://www.cms.gov/data-research/statistics-trends-and-reports/medicare-claims-synthetic-public-use-files/cms-2008-2010-data-entrepreneurs-synthetic-public-use-file-de-synpuf)

<br>

Quality and Governance Workbook: https://docs.google.com/spreadsheets/d/1ojJ4pg8HakVxw_WWOKRbWEDmxj-CBS7LEx0SUBzOjx8/edit?usp=sharing

<br>

## Environment Setup

1. Run command to clone the repository:

    `git clone https://github.com/qsanders/CMS_Data_Governance_Project.git`

2. Create a virtual environment named venv:

    `python -m venv venv`

3. Activate the virtual environment:

    `venv\Scripts\activate`

4. In the root directory of the `CMS_Data_Governance_Project` folder, create a new plain text file and name it exactly: 

    `.env`

5. Open this file in a text editor (like Notepad or VS Code) and add the following parameters. Adjust the username and password to match your local MySQL setup:

    ```plaintext
    DB_HOST=localhost
    DB_PORT=3306
    DB_NAME=cms_data_governance
    DB_USER=your_mysql_username
    DB_PASS=your_mysql_password
    ```

<br>

## Running the Scripts

There are 3 .py scripts built handle the jobs of pulling down the data, profiling the data, and loading the new raw data into new database tables.  All of the files that are necessary for these actions live in the `CMS_Data_Governance_Project/code_scripts` directory.

### Pulling the Data

The following files are for pulling the data:
* Logs = raw_cms_DE_SynPUF_data_pull.log
* Execution = raw_cms_DE_SynPUF_data_pull.py
* Parameters = raw_cms_DE_SynPUF_data_pull_select_parameters.csv

The parameter file `raw_cms_DE_SynPUF_data_pull_select_parameters.csv` is responsible for controlling the which sample data set to pull from the CMS website.  This parameter file can accept one number [#] representing the sample set to pull down or a list.

```plaintext
Par_name,value
sample_set,"[2]"  <--- one number

or 

Par_name,value
sample_set,"[2,3,4]"  <---- a list of numbers
```

1. Open the `raw_cms_DE_SynPUF_data_pull_select_parameters.csv`.  Edit it to your liking.  SAVE your changes.

2. Run the .py file that will automatically delete any old files laying around, pull the fresh raw data down, unzip it, and clean up the `CMS_Data_Governance_Project/data_raw_src` folder.
```python
python code_scripts/raw_cms_DE_SynPUF_data_pull.py
```
<br>

### Profiling the Data

The following files are for profiling the data:
* Logs = raw_cms_DE_SynPUF_data_profiling.log
* Execution = raw_cms_DE_SynPUF_data_profiling.py
* Parameters = raw_cms_DE_SynPUF_data_profiling_parameters.csv
* Result File = raw_cms_DE_SynPUF_data_profiling_results.csv

The parameter file `raw_cms_DE_SynPUF_data_profiling_parameters.csv` is responsible for controlling which profiling routines the script is allowed to run.  This parameter file can accept a Y or N for switch each routine on or off. 

```plaintext
Par_name,run_switch
null_cnt,Y
null_cnt_pct,Y
space_cnt,Y
space_cnt_pct,Y
spchr_cnt,Y
```

1. Open the `raw_cms_DE_SynPUF_data_profiling_parameters.csv` file.  Edit it to your liking.  SAVE your changes.

2. Run the .py file that will automatically loop through each field within each file (found in `CMS_Data_Governance_Project/data_raw_src` folder) and run the list of profiling logic against the value found.
```python
python code_scripts/raw_cms_DE_SynPUF_data_profiling.py
```
3. A results CSV file with be produced in the same scripts folder.  The script will automaticlly drop/create the table for this file and load it to the database.


<br>

### Loading the Data

The following files are for loading the data:
* Logs = raw_cms_DE_SynPUF_data_loader.log
* Execution = raw_cms_DE_SynPUF_data_loader.py
* Parameters #1 = raw_cms_DE_SynPUF_data_loader_field_size_parameters.csv
* Parameters #2 = raw_cms_DE_SynPUF_data_loader_parameters.csv

The [1st] parameter file `raw_cms_DE_SynPUF_data_loader_field_size_parameters.csv` is responsible for controlling the size of the fields being created and loaded.  All fields for this table will be setup as TEXT and they will all have the same size.  This parameter file can accepts a # for the "field_size" parameter. 

```plaintext
Par_num,file_name_txt,field_size
1,_Beneficiary_,100
2,_Inpatient_Claims_,150
3,_Outpatient_Claims_,150
```


The [2nd] parameter file `raw_cms_DE_SynPUF_data_loader_field_size_parameters.csv` is responsible for controlling ...
* file_num = What file is being loaded.
* table_name = What table is it loading to
* load = switc to execut load for this combination.
* load_rec_count = how many lines to load.  (Accepts [ALL] or [#])



```plaintext
Par_num,file_name,table_name,load,load_rec_count
1,DE1_0_2008_Beneficiary_Summary_File_Sample_2.csv,raw_cms_beneficiary,Y,[ALL]
2,DE1_0_2008_Beneficiary_Summary_File_Sample_3.csv,raw_cms_beneficiary,Y,[ALL]
3,DE1_0_2008_Beneficiary_Summary_File_Sample_4.csv,raw_cms_beneficiary,Y,[ALL]
4,DE1_0_2009_Beneficiary_Summary_File_Sample_2.csv,raw_cms_beneficiary,Y,[ALL]
5,DE1_0_2009_Beneficiary_Summary_File_Sample_3.csv,raw_cms_beneficiary,Y,[ALL]
6,DE1_0_2009_Beneficiary_Summary_File_Sample_4.csv,raw_cms_beneficiary,Y,[ALL]
7,DE1_0_2010_Beneficiary_Summary_File_Sample_2.csv,raw_cms_beneficiary,Y,[ALL]
8,DE1_0_2010_Beneficiary_Summary_File_Sample_3.csv,raw_cms_beneficiary,Y,[ALL]
9,DE1_0_2010_Beneficiary_Summary_File_Sample_4.csv,raw_cms_beneficiary,Y,[ALL]
10,DE1_0_2008_to_2010_Inpatient_Claims_Sample_2.csv,raw_cms_inpatient_claims,Y,[1000]
11,DE1_0_2008_to_2010_Inpatient_Claims_Sample_3.csv,raw_cms_inpatient_claims,Y,[1000]
12,DE1_0_2008_to_2010_Inpatient_Claims_Sample_4.csv,raw_cms_inpatient_claims,Y,[1000]
13,DE1_0_2008_to_2010_Outpatient_Claims_Sample_2.csv,raw_cms_outpatient_claims,Y,[1000]
14,DE1_0_2008_to_2010_Outpatient_Claims_Sample_3.csv,raw_cms_outpatient_claims,Y,[1000]
15,DE1_0_2008_to_2010_Outpatient_Claims_Sample_4.csv,raw_cms_outpatient_claims,Y,[1000]
```

1. Open the `raw_cms_DE_SynPUF_data_loader_field_size_parameters.csv` file.  Edit it to your liking.  SAVE your changes.

2. Open the `raw_cms_DE_SynPUF_data_loader_parameters.csv` file.  Edit it to your liking.  SAVE your changes.

2. Run the .py file that will create table schema, drop and create a tables based on the parameters, and load the tables based on parameters. 
```python
python code_scripts/raw_cms_DE_SynPUF_data_loader.py
```

<br>

## Additional Work Files
There are a few files save in the `CMS_Data_Governance_Project/code_scripts` directory that document the AI Prompts used to develop the scripts and the AI Prompt used to create the queries for manual analysis.

* AI SQL and Dev Prompts - `CMS_Data_Governance_Project/code_scripts/ai_prompts`
* SQL queries used - `CMS_Data_Governance_Project/code_scripts/sql_scripts`

NOTE: The numbers found in the SQL .txt files correspond to the Check Number found in the CHECKS tab of the Google Sheets Workbook.

<br>

## Google Sheets Workbook
This workbook is where most of my work is recorded.  This can be found in https://docs.google.com/spreadsheets/d/1ojJ4pg8HakVxw_WWOKRbWEDmxj-CBS7LEx0SUBzOjx8/edit?usp=sharing


NOTE: The permission for the workbook are wide open so feel free to make a copy before any changes.

* [Lineage] tab - Tells where the raw files came from and which processes touched it.

* [Dictionary] tab - Describes the each data set, it's scehma, who is responsible for it, what are the field sensitivity levels, notes on what was found regarding fields. 

* [CHECKS] tab - Log of all issues found, the category of those issue, and the impact of the issue.

* [Appendix] tab - holds additional information that my be too much to fit in the notes on the CHECKS tab.

* [Report] tab - Summary of the Health of the data and which issue are priority.


## Data Quality and Risk Measurements

### The Measures
Data quality is measured by a scoring system.  Penality point are assigned and based on the sum of those penalities a priority is set.
* CATEGORY - This describes the overall area of risk for the issue.  This can act as a multipler for the over all Penality score since some areas pose a higher risk than others.

* IMPACT - This describes what the analyst believes is the impact to the business.

### The Score
The overall Penality score is calculated by ( Category Weight * Business Impact)

### The Priority
The priority is calculated by (Category Weigth * Business impact) for each issue.  The largest number become the highest priority and so on ...
* High = Issues to be handled immediately.   
* MEDIUM = Issue to be handled with 30 days   
* LOW = Issues to be handled 30 days or more



