# Databricks notebook source
#!/usr/bin python3

# -------------------------------------------------------------------------
# Copyright (c) 2021 NHS England and NHS Improvement. All rights reserved.
# Licensed under the MIT License. See license.txt in the project root for
# license information.
# -------------------------------------------------------------------------

"""
FILE:           cybersecurity_dspt_nhs_csu_ccg_standards_month_count_prop.py
DESCRIPTION:
                Databricks notebook with processing code for the NHSX Analyticus unit metric: M020_M021  (Number and percent of CSUs and CCGs registered for DSPT assessment, that meet or exceed the DSPT standard)
USAGE:
                ...
CONTRIBUTORS:   Craig Shenton, Mattia Ficarelli, Chris Todd, Everistus Oputa
CONTACT:        data@nhsx.nhs.uk
CREATED:        24 Aug 2022
VERSION:        0.0.2
"""

# COMMAND ----------

# Install libs
# -------------------------------------------------------------------------
%pip install geojson==2.5.* tabulate requests pandas pathlib azure-storage-file-datalake beautifulsoup4 numpy urllib3 lxml regex pyarrow==5.0.*

# COMMAND ----------

# Imports
# -------------------------------------------------------------------------
# Python:
import os
import io
import tempfile
from datetime import datetime
import json

# 3rd party:
import pandas as pd
import numpy as np
from pathlib import Path
from azure.storage.filedatalake import DataLakeServiceClient

# Connect to Azure datalake
# -------------------------------------------------------------------------
# !env from databricks secrets
CONNECTION_STRING = dbutils.secrets.get(scope='AzureDataLake', key="DATALAKE_CONNECTION_STRING")

# COMMAND ----------

# MAGIC %run /Shared/databricks/au-azure-databricks-cicd/functions/dbrks_helper_functions

# COMMAND ----------

# Load JSON config from Azure datalake
# -------------------------------------------------------------------------
file_path_config = "/config/pipelines/nhsx-au-analytics/"
file_name_config = "config_dspt_nhs_dbrks.json"
file_system_config =  dbutils.secrets.get(scope='AzureDataLake', key="DATALAKE_CONTAINER_NAME")
config_JSON = datalake_download(CONNECTION_STRING, file_system_config, file_path_config, file_name_config)
config_JSON = json.loads(io.BytesIO(config_JSON).read())

# COMMAND ----------

#Get parameters from JSON config
source_path = config_JSON['pipeline']['project']['source_path']
source_file = config_JSON['pipeline']['project']['source_file']
reference_path = config_JSON['pipeline']['project']['reference_path']
reference_file = config_JSON['pipeline']['project']['reference_file']
file_system = dbutils.secrets.get(scope='AzureDataLake', key="DATALAKE_CONTAINER_NAME")
sink_path = config_JSON['pipeline']['project']['databricks'][1]['sink_path']
sink_file = config_JSON['pipeline']['project']['databricks'][1]['sink_file']
table_name = config_JSON['pipeline']["staging"][1]['sink_table']

# COMMAND ----------

# Processing 
# -------------------------------------------------------------------------
latestFolder = datalake_latestFolder(CONNECTION_STRING, file_system, source_path)
reference_latestFolder = datalake_latestFolder(CONNECTION_STRING, file_system, reference_path)
file = datalake_download(CONNECTION_STRING, file_system, source_path+latestFolder, source_file)
reference_file = datalake_download(CONNECTION_STRING, file_system, reference_path+reference_latestFolder, reference_file)
DSPT_df = pd.read_csv(io.BytesIO(file))
ODS_code_df = pd.read_parquet(io.BytesIO(reference_file), engine="pyarrow")

# Make all ODS codes in DSPT dataframe capital
# -------------------------------------------------------------------------
DSPT_df.columns = DSPT_df.columns.str.strip()
DSPT_df['Code'] = DSPT_df['Code'].str.upper()

# Make ODS dataframe open and close dates datetime
# -------------------------------------------------------------------------
ODS_code_df['Close_Date'] = pd.to_datetime(ODS_code_df['Close_Date'], infer_datetime_format=True)
ODS_code_df['Open_Date'] =  pd.to_datetime(ODS_code_df['Open_Date'], infer_datetime_format=True)

# Set datefilter for org open and close dates
# -------------------------------------------------------------------------
close_date = datetime.strptime('2022-03-31','%Y-%m-%d') #------ change close date filter for CCGs and CSUs through time. Please see SOP
open_date = datetime.strptime('2022-03-31','%Y-%m-%d') #------- change open date filter for CCGs and CSUs through time. Please see SOP

# Join DSPT data with ODS table on ODS code
# -------------------------------------------------------------------------
DSPT_ODS = pd.merge(ODS_code_df, DSPT_df, how='outer', left_on="Code", right_on="Code")
DSPT_ODS =DSPT_ODS.reset_index(drop=True).rename(columns={"ODS_API_Role_Name": "Sector",})
DSPT_ODS_selection =  DSPT_ODS[(DSPT_ODS['Close_Date'].isna() | (DSPT_ODS['Close_Date'] > close_date))].reset_index(drop = True)
DSPT_ODS_selection_1 = (DSPT_ODS_selection[DSPT_ODS_selection['Open_Date'] < open_date]).reset_index(drop = True)

# Creation of final dataframe with all currently open CCGs and CSUs
# -------------------------------------------------------------------------
DSPT_ODS_selection_2 = DSPT_ODS_selection_1[ 
(DSPT_ODS_selection_1["Name"].str.contains("COMMISSIONING HUB")==False) &
(DSPT_ODS_selection_1["Code"].str.contains("RT4|RQF|RYT|0DH|0AD|0AP|0CC|0CG|0CH|0DG")==False)].reset_index(drop=True) #------ change exclusion codes for CCGs and CSUs through time. Please see SOP
DSPT_ODS_selection_3 = DSPT_ODS_selection_2[DSPT_ODS_selection_2.Sector.isin(["CLINICAL COMMISSIONING GROUP", "COMMISSIONING SUPPORT UNIT"])].reset_index(drop=True)

# Creation of final dataframe with all currently open CCGs and CSUs which meet or exceed the DSPT standard
# --------------------------------------------------------------------------------------------------------
DSPT_ODS_selection_3 = DSPT_ODS_selection_3.rename(columns = {"Status":"Latest Status"})
DSPT_ODS_selection_4 = DSPT_ODS_selection_3[DSPT_ODS_selection_3["Latest Status"].isin(["21/22 Standards Met", 
                                                                                         "21/22 Standards Exceeded", 
                                                                                         "22/23 Standards Met", 
                                                                                         "22/23 Standards Exceeded"])].reset_index(drop=True) #------ change financial year for DSPT standard through time. Please see SOP

# COMMAND ----------

# Processing - Generating final dataframe for staging to SQL database
# -------------------------------------------------------------------------
date_string = str(datetime.now().strftime("%Y-%m"))
dspt_edition = "2021/2022"  #------ change DSPT edition through time. Please see SOP
met_exceed_csu_ccg = DSPT_ODS_selection_4["Code"].count()
total_no_csu_ccg = DSPT_ODS_selection_3["Code"].count()
data = [[date_string, dspt_edition, met_exceed_csu_ccg, total_no_csu_ccg]]
df_output = pd.DataFrame(data, columns=["Date", "DSPT edition", "Number of CSUs and CCGs with a standards met or exceeded DSPT status", "Total number of CSUs and CCGs"])
df_output["Percent of CSUs and CCGs with a standards met or exceeded DSPT status"] = df_output["Number of CSUs and CCGs with a standards met or exceeded DSPT status"]/df_output["Total number of CSUs and CCGs"]
df_output = df_output.round(4)
df_output['Date'] = pd.to_datetime(df_output['Date'])
df_output.index.name = "Unique ID"
df_processed = df_output.copy()

# COMMAND ----------

#Upload processed data to datalake
file_contents = io.StringIO()
df_processed.to_csv(file_contents)
datalake_upload(file_contents, CONNECTION_STRING, file_system, sink_path+latestFolder, sink_file)

# COMMAND ----------

# Write data from databricks to dev SQL database
# -------------------------------------------------------------------------
write_to_sql(df_processed, table_name, "overwrite")
