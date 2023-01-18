# Databricks notebook source
#!/usr/bin python3

# -------------------------------------------------------------------------
# Copyright (c) 2021 NHS England and NHS Improvement. All rights reserved.
# Licensed under the MIT License. See license.txt in the project root for
# license information.
# -------------------------------------------------------------------------

"""
FILE:           dbrks_trigger_nhs_app_validation.py
DESCRIPTION:
                To reduce manual checks and improve quality validations need to added to dbrks_trigger_nhs_app_devices_validation pipeline for digital social care
USAGE:
                ...
CONTRIBUTORS:   Abdu Nuhu, Kabir Khan
CONTACT:        nhsx.data@england.nhs.uk
CREATED:        16 Jan 2023
VERSION:        0.0.1
"""

# COMMAND ----------

# Install libs
# -------------------------------------------------------------------------------------
%pip install pandas pathlib azure-storage-file-datalake numpy pyarrow==5.0.* great_expectations openpyxl 

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
import great_expectations as ge

# Connect to Azure datalake
# -------------------------------------------------------------------------
# !env from databricks secrets
CONNECTION_STRING = dbutils.secrets.get(scope='AzureDataLake', key="DATALAKE_CONNECTION_STRING")

# COMMAND ----------

# MAGIC %run /Shared/databricks/au-azure-databricks-cicd/functions/dbrks_helper_functions

# COMMAND ----------

# Load parameters and JSON config from Azure datalake
# -------------------------------------------------------------------------

file_path_config = "config/pipelines/nhsx-au-analytics"
file_name_config = "config_nhs_app_dbrks.json"
log_table = "dbo.pre_load_log"

file_system_config = dbutils.secrets.get(scope="AzureDataLake", key="DATALAKE_CONTAINER_NAME")
config_JSON = datalake_download(CONNECTION_STRING, file_system_config, file_path_config, file_name_config)
config_JSON = json.loads(io.BytesIO(config_JSON).read())

# COMMAND ----------

# Read parameters from JSON config
# -------------------------------------------------------------------------
file_system = dbutils.secrets.get(scope="AzureDataLake", key="DATALAKE_CONTAINER_NAME")
new_source_path = config_JSON["pipeline"]['raw']["snapshot_source_path"]

# COMMAND ----------

# Pull new snapshot dataset
# -------------------------
latestFolder = datalake_latestFolder(CONNECTION_STRING, file_system, new_source_path)
file_name_list = datalake_listContents(CONNECTION_STRING, file_system, new_source_path+latestFolder)
file_name_list = [file for file in file_name_list if 'nhs_app_table_snapshot' in file]
for new_source_file in file_name_list:
  new_dataset = datalake_download(CONNECTION_STRING, file_system, new_source_path+latestFolder, new_source_file)
  new_dataframe = pd.read_csv(io.BytesIO(new_dataset))
  new_dataframe['Date'] = pd.to_datetime(new_dataframe['Date']).dt.strftime("%Y-%m-%d")

# COMMAND ----------

# validate data
# Greate expectations https://www.architecture-performance.fr/ap_blog/built-in-expectations-in-great-expectations/
# ----------------------------------
val_df = new_dataframe.mask(new_dataframe == " ") # convert all blanks to NaN for validtion
df1 = ge.from_pandas(val_df) # Create great expectations dataframe from pandas datafarme

# COMMAND ----------

# MAGIC %md
# MAGIC ## Tests Begin

# COMMAND ----------

#Test that the all the column have expected type such as int, str etc

info = "Checking that all the columns have integer type\n"
types = {
    "P5NewAppUsers": "int",
    "AcceptedTermsAndConditions": "int",
    "P9VerifiedNHSAppUsers": "int",
    "Logins": "int",
    "RecordViews": "int",
    "Prescriptions": "int",
    "NomPharmacy": "int",
    "AppointmentsBooked": "int",
    "AppointmentsCancelled": "int",
    "ODRegistrations": "int",
    "ODWithdrawals": "int",
    "ODUpdates": "int",
    "ODLookups": "int",
    "RecordViewsDCR": "int",
    "RecordViewsSCR": "int"
}
for column, type_ in types.items():
    expect = df1.expect_column_values_to_be_of_type(column=column, type_=type_)
    test_result(expect, info)
    assert expect.success
    
# COMMAND ----------

#Test that the OdsCode column do not contain any null values

info = "Checking that the OdsCode column do not contain any null values\n"
expect = df1.expect_column_values_to_not_be_null(column='OdsCode')
test_result(expect, info)
assert expect.success


# COMMAND ----------

#Test that there are 7 records for the weekly data

info = 'Checking there are 7 records for the weekly data\n'
expect = df1.expect_table_row_count_to_equal(7)
test_result(expect, info)
assert expect.success


# COMMAND ----------

#Test that the 7 rows have unique dates

info = 'Checking the Dates for the 7 records for the week are unique data\n'
expect = df1.expect_column_values_to_be_unique(column="Date")
test_result(expect, info)
assert expect.success


# COMMAND ----------

#Test that the Type column only contains Apple or Google

info = 'Checking that the Type column only contains Google or Apple\n'
expect = df1.expect_column_values_to_be_in_set(column="Type", value_set=["Google", "Apple"]) # Check the values in the columns are either Apple or Google only
test_result(expect, info)
assert expect.success


# COMMAND ----------

# MAGIC %md
# MAGIC ## Tests End

# COMMAND ----------

# Count rows in file and write to log table
#___________________________________________
full_path = new_source_path + latestFolder + new_source_file
row_count = len(new_dataframe)
today = pd.to_datetime('now').strftime("%Y-%m-%d %H:%M:%S")
date = datetime.strptime(today, '%Y-%m-%d %H:%M:%S')
in_row = {'row_count':[row_count], 'load_date':[date], 'file_to_load':[full_path]}
df = pd.DataFrame(in_row)  
write_to_sql(df, log_table, "append")
