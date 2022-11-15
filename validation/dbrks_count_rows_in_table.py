# Databricks notebook source
#!/usr/bin python3

# -------------------------------------------------------------------------
# Copyright (c) 2021 NHS England and NHS Improvement. All rights reserved.
# Licensed under the MIT License. See license.txt in the project root for
# license information.
# -------------------------------------------------------------------------

"""
FILE:           dbrks_nhs_app_jumpoff_raw.py
DESCRIPTION:
                Databricks notebook with code to append new raw data to historical
                data for the NHSX Analyticus unit metrics within the NHS app
                topic
USAGE:
                ...
CONTRIBUTORS:   Mattia Ficarelli, Chris Todd, Everistus Oputa
CONTACT:        data@nhsx.nhs.uk
CREATED:        07 Jun. 2022
VERSION:        0.0.2
"""

# COMMAND ----------

# Install libs
# ------------------------------------------------------------------------------------
%pip install pandas pathlib azure-storage-file-datalake numpy pyarrow==5.0.*

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

# Load parameters and JSON config from Azure datalake
# -------------------------------------------------------------------------
file_path_config = dbutils.widgets.get("adf_file_path")
file_name_config = dbutils.widgets.get("adf_file_name")
log_table = dbutils.widgets.get("adf_log_table")

file_system_config = dbutils.secrets.get(scope='AzureDataLake', key="DATALAKE_CONTAINER_NAME")
config_JSON = datalake_download(CONNECTION_STRING, file_system_config, file_path_config, file_name_config)
config_JSON = json.loads(io.BytesIO(config_JSON).read())

# COMMAND ----------

# Read parameters from JSON config
# -------------------------------------------------------------------------
file_system = dbutils.secrets.get(scope='AzureDataLake', key="DATALAKE_CONTAINER_NAME")
new_source_path = config_JSON['pipeline']['raw']['snapshot_source_path']
staging = config_JSON['pipeline']["staging"]


# COMMAND ----------

# Read and aggregate table data
# -------------------------------------------------------------------------
today = pd.to_datetime('now').strftime("%Y-%m-%d %H:%M:%S")
date = datetime.strptime(today, '%Y-%m-%d %H:%M:%S')
staging_tbl = ''

for entry in staging:
  for key in entry:
    if key == 'sink_table':
      staging_tbl = entry[key]
      spark_df = read_sql_server_table(staging_tbl)
      row_count = spark_df.count()
      in_row = {'load_date':[date], 'tbl_name':[staging_tbl], 'aggregation':'Count', 'aggregate_value':[row_count]}
      df = pd.DataFrame(in_row)
      write_to_sql(df, log_table, "append")
        
