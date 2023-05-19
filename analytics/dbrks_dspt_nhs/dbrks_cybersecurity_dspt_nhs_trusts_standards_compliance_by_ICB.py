# Databricks notebook source
#!/usr/bin python3

# -------------------------------------------------------------------------
# Copyright (c) 2021 NHS England and NHS Improvement. All rights reserved.
# Licensed under the MIT License. See license.txt in the project root for
# license information.
# -------------------------------------------------------------------------

"""
FILE:           cybersecurity_dspt_nhs_trusts_standards_compliance_by_ICB.py
DESCRIPTION:
                Databricks notebook with processing code for the NHSX Analyticus unit metric: M394  (Number and percent of Trusts registered for DSPT assessment that meet or exceed the DSPT standard at ICB level)
USAGE:
                ...
CONTRIBUTORS:   Everistus Oputa
CONTACT:        NHSX.Data@england.nhs.uk
CREATED:        13 Mar 2023
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

#Download JSON config from Azure datalake
file_path_config = "/config/pipelines/nhsx-au-analytics/"
file_name_config = "config_dspt_nhs_dbrks.json"
file_system_config =  dbutils.secrets.get(scope='AzureDataLake', key="DATALAKE_CONTAINER_NAME")
config_JSON = datalake_download(CONNECTION_STRING, file_system_config, file_path_config, file_name_config)
config_JSON = json.loads(io.BytesIO(config_JSON).read())

# COMMAND ----------

#Get parameters from JSON config
source_path = config_JSON['pipeline']['project']['source_path']
source_file = config_JSON['pipeline']['project']['source_file']
reference_path = config_JSON['pipeline']['project']['reference_path2']
reference_file = config_JSON['pipeline']['project']['reference_file2']
file_system =  dbutils.secrets.get(scope='AzureDataLake', key="DATALAKE_CONTAINER_NAME")
sink_path = config_JSON['pipeline']['project']['databricks'][2]['sink_path']
sink_file = config_JSON['pipeline']['project']['databricks'][2]['sink_file']
table_name = config_JSON['pipeline']["staging"][2]['sink_table']

# COMMAND ----------

def datalake_list_folders(CONNECTION_STRING, file_system, source_path):
  try:
      service_client = DataLakeServiceClient.from_connection_string(CONNECTION_STRING)
      file_system_client = service_client.get_file_system_client(file_system=file_system)
      pathlist = list(file_system_client.get_paths(source_path))
      folders = []
      # remove file_path and source_file from list
      for path in pathlist:
        folders.append(path.name.replace(source_path.strip("/"), "").lstrip("/").rsplit("/", 1)[0])
        folders.sort(key=lambda date: datetime.strptime(date, "%Y-%m-%d"))
      
      return folders
  except Exception as e:
      print(e)

# COMMAND ----------

folders = datalake_list_folders(CONNECTION_STRING, file_system, source_path)
folders

# COMMAND ----------

folder = folders[0]
folder

# COMMAND ----------

# Processing 
# -------------------------------------------------------------------------

latestFolder = folder
reference_latestFolder = datalake_latestFolder(CONNECTION_STRING, file_system, reference_path)
file = datalake_download(CONNECTION_STRING, file_system, source_path+latestFolder, source_file)
reference_file = datalake_download(CONNECTION_STRING, file_system, reference_path+reference_latestFolder, reference_file)
DSPT_df = pd.read_csv(io.BytesIO(file))
ODS_code_df = pd.read_parquet(io.BytesIO(reference_file), engine="pyarrow")

# Make all ODS codes in DSPT dataframe capital
# -------------------------------------------------------------------------
DSPT_df['Code'] = DSPT_df['Code'].str.upper()
DSPT_df = DSPT_df.rename(columns = {'Code': 'Organisation_Code'})

# Join DSPT data with ODS table on ODS code
# -------------------------------------------------------------------------
DSPT_ODS = ODS_code_df.merge(DSPT_df, how ='outer', on = 'Organisation_Code')

# Creation of final dataframe with all currently open NHS Trusts
# -------------------------------------------------------------------------
DSPT_ODS_selection_2 = DSPT_ODS[ 
(DSPT_ODS["Organisation_Code"].str.contains("RT4|RQF|RYT|0DH|0AD|0AP|0CC|0CG|0CH|0DG")==False)].reset_index(drop=True) #------ change exclusion codes for CCGs and CSUs through time. Please see SOP
DSPT_ODS_selection_3 = DSPT_ODS_selection_2[DSPT_ODS_selection_2.ODS_Organisation_Type.isin(["NHS TRUST", "CARE TRUST"])].reset_index(drop=True)

# Creation of final dataframe with all currently open NHS Trusts which meet or exceed the DSPT standard
# --------------------------------------------------------------------------------------------------------
DSPT_ODS_selection_3 = DSPT_ODS_selection_3.rename(columns = {"Status":"Latest Status"})

DSPT_ODS_selection_3




# COMMAND ----------

DSPT_ODS_selection_3['Latest Status'].unique()

# COMMAND ----------

pd.to_datetime('01/07/2022')

# COMMAND ----------

import time
pd.to_datetime(DSPT_ODS_selection_3['Date Of Publication'].max()).strftime('%Y-%m-%m') < '2022-07-01' and pd.to_datetime(DSPT_ODS_selection_3['Date Of Publication'].max()).strftime('%Y-%m-%m') > '2023-07-01'

# COMMAND ----------

# Processing - Generating final dataframe for staging to SQL database
# -------------------------------------------------------------------------
# Generating Total_no_trusts

#2019/2020
df1 = DSPT_ODS_selection_3[["Organisation_Code", "STP_Code", 'Latest Status']].copy()
list_of_statuses1 = ["19/20 Approaching Standards", 
                      "19/20 Standards Exceeded", 
                      "19/20 Standards Met", 
                      "19/20 Standards Not Met"]

if pd.to_datetime(DSPT_ODS_selection_3['Date Of Publication'].max()).strftime('%Y-%m-%m') < '2020-07-01' and pd.to_datetime(DSPT_ODS_selection_3['Date Of Publication'].max()).strftime('%Y-%m-%m') > '2019-07-01':
  list_of_statuses1.append('Not Published')
  
df1 = df1[df1['Latest Status'].isin(list_of_statuses1)]

df1['Organisation_Code'] = df1['Organisation_Code'].astype(str)
df1 = df1.groupby(['STP_Code'], as_index=False).count()
df1['date_string'] = str(datetime.now().strftime("%Y-%m"))
df1['dspt_edition'] = "2019/2020"   #------ change DSPT edition through time. Please see SOP
df1 = df1[['date_string','dspt_edition','STP_Code', 'Organisation_Code']]
df1 = df1.rename(columns = {'date_string': 'Date','dspt_edition': 'Dspt_edition','STP_Code': 'ICB_Code','Organisation_Code':'Total_no_trusts'})

#2020/2021
df2 = DSPT_ODS_selection_3[["Organisation_Code", "STP_Code", 'Latest Status']].copy()
list_of_statuses2 = ["20/21 Approaching Standards", 
                    "20/21 Standards Exceeded", 
                    "20/21 Standards Met", 
                    "20/21 Standards Not Met"]

if pd.to_datetime(DSPT_ODS_selection_3['Date Of Publication'].max()).strftime('%Y-%m-%m') < '2021-07-01' and pd.to_datetime(DSPT_ODS_selection_3['Date Of Publication'].max()).strftime('%Y-%m-%m') > '2020-07-01':
  list_of_statuses2.append('Not Published') 

df2 = df2[df2['Latest Status'].isin(list_of_statuses2)]
                        
df2['Organisation_Code'] = df2['Organisation_Code'].astype(str)
df2 = df2.groupby(['STP_Code'], as_index=False).count()
df2['date_string'] = str(datetime.now().strftime("%Y-%m"))
df2['dspt_edition'] = "2021/2022"   #------ change DSPT edition through time. Please see SOP
df2 = df2[['date_string','dspt_edition','STP_Code', 'Organisation_Code']]
df2 = df2.rename(columns = {'date_string': 'Date','dspt_edition': 'Dspt_edition','STP_Code': 'ICB_Code','Organisation_Code':'Total_no_trusts'})


#2021/2022
df2 = DSPT_ODS_selection_3[["Organisation_Code", "STP_Code", 'Latest Status']].copy()
df2 = df2[df2['Latest Status'].isin(["22/23 Approaching Standards", 
                                      "22/23 Standards Exceeded", 
                                      "22/23 Standards Met", 
                                      "22/23 Standards Not Met"])]
                                      
df2['Organisation_Code'] = df2['Organisation_Code'].astype(str)
df2 = df2.groupby(['STP_Code'], as_index=False).count()                                    
df2['date_string'] = str(datetime.now().strftime("%Y-%m"))
df2['dspt_edition'] = "2022/2023"   #------ change DSPT edition through time. Please see SOP      
df5 = df2[['date_string','dspt_edition','STP_Code', 'Organisation_Code']] 
df5 = df5.rename(columns = {'date_string': 'Date','dspt_edition': 'Dspt_edition','STP_Code': 'ICB_Code','Organisation_Code':'Total_no_trusts'})                         


#Joined data processing
df_join = pd.concat([df4, df5], ignore_index=True)
df_join_1 = df_join.rename(columns = {'Date':'Report Date','ICB_Code': 'ICB_CODE','Dspt_edition': 'Dspt_edition','Total_no_trusts':'Total number of Trusts','status':'Standard status','status number':'Number of Trusts with the standard status'})
# df_join_1["Percent of Trusts with a standards met or exceeded DSPT status"] = df_join_1["Number of Trusts with the standard status"]/df_join_1["Total number of Trusts"]
df_join_1 = df_join_1.round(2)
df_join_1['Report Date'] = pd.to_datetime(df_join_1['Report Date'])
df_join_1.index.name = "Unique ID"
df_processed = df_join_1.copy()



# COMMAND ----------

df_processed

# COMMAND ----------

#Upload processed data to datalake
file_contents = io.StringIO()
df_processed.to_csv(file_contents)
datalake_upload(file_contents, CONNECTION_STRING, file_system, sink_path+latestFolder, sink_file)

# COMMAND ----------

# Write data from databricks to dev SQL database
# -------------------------------------------------------------------------
write_to_sql(df_processed, table_name, "overwrite")
