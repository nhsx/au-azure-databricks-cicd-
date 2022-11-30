# Databricks notebook source
#!/usr/bin python3

# -------------------------------------------------------------------------
# Copyright (c) 2021 NHS England and NHS Improvement. All rights reserved.
# Licensed under the MIT License. See license.txt in the project root for
# license information.
# -------------------------------------------------------------------------

"""
FILE:           dbrks_dscr_all_variables_month_count.py
DESCRIPTION:
                Databricks notebook with processing code for the CQC digital social care records : Monthly digital social care records mapping to icb_region
USAGE:
                ...
CONTRIBUTORS:   Everistus Oputa
CONTACT:        data@nhsx.nhs.uk
CREATED:        30 Nov. 2022
VERSION:        0.0.1
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
file_name_config = "config_dscr_dbrks.json"
file_system_config = dbutils.secrets.get(scope='AzureDataLake', key="DATALAKE_CONTAINER_NAME")
config_JSON = datalake_download(CONNECTION_STRING, file_system_config, file_path_config, file_name_config)
config_JSON = json.loads(io.BytesIO(config_JSON).read())

# COMMAND ----------

#Get parameters from JSON config
# -------------------------------------------------------------------------
source_path = config_JSON['pipeline']['project']['source_path']
source_file = config_JSON['pipeline']['project']['source_file']
reference_path = config_JSON['pipeline']['project']['reference_source_path']
reference_file = config_JSON['pipeline']['project']['reference_source_file']
file_system =  dbutils.secrets.get(scope='AzureDataLake', key="DATALAKE_CONTAINER_NAME")
sink_path = config_JSON['pipeline']['project']['databricks'][0]['sink_path']
sink_file = config_JSON['pipeline']['project']['databricks'][0]['sink_file']
table_name = config_JSON['pipeline']["staging"][0]['sink_table']

# COMMAND ----------

# dscr data Processing
# -------------------------------------------------------------------------
latestFolder = datalake_latestFolder(CONNECTION_STRING, file_system, source_path)
file = datalake_download(CONNECTION_STRING, file_system, source_path+latestFolder, source_file)
df = pd.read_parquet(io.BytesIO(file), engine="pyarrow")
df_1 = df[['Location ID', 'Dormant (Y/N)',' Care home?','Location Inspection Directorate','Location Primary Inspection Category','Location ONSPD CCG Code','Location ONSPD CCG','Provider ID','Provider Inspection Directorate','Provider Primary Inspection Category','Provider Postal Code','run_date']]
df_1['run_date'] = pd.to_datetime(df_1['run_date']).dt.strftime('%Y-%m')
df_2 = df_1[~df_1.duplicated(['Location ID', 'Dormant (Y/N)',' Care home?','Location Inspection Directorate','Location Primary Inspection Category','Location ONSPD CCG Code','Location ONSPD CCG','Provider ID','Provider Inspection Directorate','Provider Primary Inspection Category','Provider Postal Code','run_date'])].reset_index(drop = True)
df_2 = df_2.rename(columns = {'Location ID', 'Dormant (Y/N)',' Care home?','Location Inspection Directorate','Location Primary Inspection Category','Location ONSPD CCG Code':'CCG_ONS_Code','Location ONSPD CCG','Provider ID','Provider Inspection Directorate','Provider Primary Inspection Category','Provider Postal Code','run_date'})


#df_2['Use a Digital Social Care Record system?'] = df_2['Use a Digital Social Care Record system?'].replace('Yes',1).replace('No',0)
#df_3 = df_2[df_2['Location Status'] == 'Active']
#df_4 = df_3.groupby(['PIR submission date'])['Use a Digital Social Care Record system?'].agg(['sum', 'count']).reset_index()
#df_4[['sum', 'count']] = df_4[['sum', 'count']].cumsum()
#df_4 = df_4.rename(columns = {'PIR submission date': 'Date', 'sum': 'Cummulative number of adult socialcare providers that have adopted a digital social care record', 'count': 'Cummulative number of adult socialcare providers that returned a PIR'})

# ref data Processing
# -------------------------------------------------------------------------
latestFolder = datalake_latestFolder(CONNECTION_STRING, file_system, reference_source_path)
file = datalake_download(CONNECTION_STRING, file_system, denom_source_path+latestFolder, reference_source_file)
df_ref = pd.read_parquet(io.BytesIO(file), engine="pyarrow")
df_ref_1 = df_ref[['CCG_ONS_Code ', 'CCG_ODS_Code','CCG_Name','ICB_ONS_Code','ICB_Code','ICB_Name','Region_Code','Region_Name','Last_Refreshed']]
df_2 = df_ref_1[~df_ref_1.duplicated(['CCG_ONS_Code ', 'CCG_ODS_Code','CCG_Name','ICB_ONS_Code','ICB_Code','ICB_Name','Region_Code','Region_Name','Last_Refreshed'])].reset_index(drop = True)
#df_ref_2= df_ref_1[df_ref_1['Dormant (Y/N)'] == 'N'].reset_index(drop = True)
#df_ref_3=df_ref_2.groupby('Date').count().reset_index().drop(columns = 'Dormant (Y/N)')
#df_ref_4 = df_ref_3.rename(columns = {'Location CQC ID ': 'Number of active adult socialcare organisations'})

# COMMAND ----------

# Joint processing
# -------------------------------------------------------------------------
df_join = df_2.merge(df_ref_2, how ='left', on = 'CCG_ONS_Code')
#df_join['Percentage of adult socialcare providers that have adopted a digital social care record']= df_join['Cummulative number of adult socialcare providers that have adopted a digital social care record']/df_join['Number of active adult socialcare organisations']
df_join.index.name = "Unique ID"
df_join = df_join.round(4)
df_join["Date"] = pd.to_datetime(df_join["Date"])
df_processed = df_join.copy()

# COMMAND ----------

# Joint processing
# -------------------------------------------------------------------------
df_join = df_2.merge(df_ref_2, how ='left', on = 'CCG_ONS_Code')
#df_join['Percentage of adult socialcare providers that have adopted a digital social care record']= df_join['Cummulative number of adult socialcare providers that have adopted a digital social care record']/df_join['Number of active adult socialcare organisations']
df_join.index.name = "Unique ID"
df_join = df_join.round(4)
df_join["Date"] = pd.to_datetime(df_join["Date"])
df_processed = df_join.copy()

# COMMAND ----------

# Write data from databricks to dev SQL database
# -------------------------------------------------------------------------
write_to_sql(df_processed, table_name, "overwrite")
