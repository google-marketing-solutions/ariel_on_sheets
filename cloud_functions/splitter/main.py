"""Google Cloud function that uploads the chunk of conversions to Google Ads."""

# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# -*- coding: utf-8 -*-

from datetime import datetime
import json
import os
import sys
import traceback
from typing import Any, List
import flask
import functions_framework
import google.auth
from google.cloud import logging
from google.cloud import pubsub_v1
import gspread
import pandas as pd

sheet_client = None

STATUS_PROCESSING = "PROCESSING"
STATUS_FAILED = "FAILED"

STATUS_COLUMNS = {
    "STATUS_COLUMN": "P",
    "UPDATED_AT_COLUMN": "Q",
    "MESSAGE_COLUMN": "R",
}

FAILED_STATUS_FOR_REPORTING = "ERROR_IN_ARIEL_SPLITTER"
CF_NAME = "ariel_splitter"


VOICE_PROVIDER_ELEVENLABS = "ElevenLabs"
VOICE_PROVIDER_GOOGLE = "Google"

DEFAULT_DUBBING_CONFIG: dict[str, str] = {
    "campaign_name": "Default",
    "custom_tag": "default_tag",
    "original_language": "",
    "target_language": "[]",
    "video_url": "",
    "script": "[]",
    "target_gender": "",
    "voice_provider": VOICE_PROVIDER_GOOGLE,
    "clone_original_voices": "False",
    "preferred_voice_family": "[]",
    "voices": "[]",
    "output_naming_convention": "",
    "output_bucket": "",
    "status": "",
    "output_file_path": "",
    "number_of_speakers": "1",
    "diarization_instructions": "",
    "translation_instructions": "",
    "no_dubbing_phrases": "[]",
    "merge_utterances": "True",
    "minimum_merge_threshold": "0.001",
    "adjust_speed": "True",
    "vocals_volume_adjustment": "5.0",
    "background_volume_adjustment": "0.0",
    "gemini_model_name": "gemini-1.5-flash",
    "gemini_temperature": "1.0",
    "gemini_top_p": "0.95",
    "gemini_top_k": "64",
    "gemini_maximum_output_tokens": "8192",
    "clean_up": "False",
    "with_verification": "False",
    "tts_params": "{}",
}


def _update_google_sheet(
    url: str,
    worksheet_name: str,
    row: int,
    status: str,
    message: str,
    client: gspread.Client,
) -> gspread.Worksheet:
  """Updates a Google Sheet with the processing status and a message.

  Args:
    url: The URL of the Google Sheet.
    worksheet_name: The name of the worksheet to update.
    row: The row number to update.
    status: The status to write to the sheet (e.g., 'PROCESSING', 'FAILED').
    message: A message about the status, typically an error message if the
      status is 'FAILED'.
    client: An authenticated gspread client object.

  Returns:
    The updated gspread.Worksheet object.
  """

  current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  sheet = client.open_by_url(url)
  sheet.worksheet(worksheet_name).update(
      f"{STATUS_COLUMNS['STATUS_COLUMN']}{row}:{STATUS_COLUMNS['MESSAGE_COLUMN']}{row}",
      [[status, current_datetime, message]],
  )


@functions_framework.http
def run(request: flask.Request) -> flask.Response:
  """HTTP Cloud Function.

  Args:
      request (flask.Request): The request object.
        <https://flask.palletsprojects.com/en/1.1.x/api/#incoming-request-data>

  Returns:
      The response text, or any set of values that can be turned into a
      Response object using `make_response`
      <https://flask.palletsprojects.com/en/1.1.x/api/#flask.make_response>.
  """

  logging_client = logging.Client()
  log_name = os.environ["DEPLOYMENT_NAME"] + CF_NAME
  logger = logging_client.logger(log_name)

  required_elem = [
      "PROJECT_ID",
      "REGION",
      "SERVICE_ACCOUNT",
      "DEPLOYMENT_NAME",
      "PUBSUB_TOPIC",
  ]
  if not all(elem in os.environ for elem in required_elem):
    logger.log_text(
        f"{FAILED_STATUS_FOR_REPORTING}: Cannot proceed, there are missing"
        " input values please make sure you set all the environment variables"
        " correctly."
    )

    sys.exit(1)

  request_json = request.get_json(silent=True)
  print(request_json)

  try:

    worksheet_url = request_json["worksheet_url"]
    tool_config_sheet_name = request_json["tool_config_sheet_name"]
    sheets_client = _init_google_sheet_client()
    tool_config = _read_tool_config_from_google_sheet(
        {}, sheets_client, worksheet_url, tool_config_sheet_name
    )

    dubbing_config = _read_dubbing_config_from_google_sheet(
        DEFAULT_DUBBING_CONFIG,
        sheets_client,
        worksheet_url,
        tool_config["DUBBING_CONFIG"],
    )

    _process_lines(
        os.environ["PROJECT_ID"],
        os.environ["PUBSUB_TOPIC"],
        tool_config,
        dubbing_config,
        sheets_client,
        worksheet_url,
        logger,
    )

    return "OK", 200

  except Exception as e:
    traceback.print_exc()
    return f"Error {e}", 500


def _process_lines(
    project_id: str,
    pubsub_topic: str,
    tool_config: pd.DataFrame,
    dubbing_config: List[dict[str, Any]],
    sheets_client: gspread.Client,
    worksheet_url: str,
    logger: logging.Logger,
) -> None:
  """Processes each line in the dubbing configuration and publishes a message to PubSub.

  This function iterates through each row of the dubbing configuration,
  prepares a payload containing the configuration for each video,
  and publishes it to a PubSub topic for asynchronous processing.
  It also updates the Google Sheet with the processing status.

  Args:
    project_id: Google Cloud project ID.
    pubsub_topic: Name of the PubSub topic to publish messages to.
    tool_config: DataFrame containing tool-level configurations.
    dubbing_config: List of dictionaries, each representing a line's dubbing
      configuration.
    sheets_client: gspread client object for interacting with Google Sheets.
    worksheet_url: The URL of the Google Sheet containing the configuration.
    logger: logging.Logger object for logging events and errors.
  Returns:
    None
  """

  publisher_client = pubsub_v1.PublisherClient()

  for row_num, line_config in enumerate(dubbing_config):

    line_config["row_num"] = row_num
    message = ""

    try:

      status = STATUS_PROCESSING
      payload = {
          "worksheet_url": worksheet_url,
          "line_config": line_config,
          "tool_config": tool_config,
          "status_columns": STATUS_COLUMNS,
      }

      _publish_pubsub(publisher_client, project_id, pubsub_topic, payload)

    except Exception as e:
      traceback.print_exc()
      print(str(e))
      logger.log(str(e))
      logging_payload = {
          "worksheet_url": worksheet_url if worksheet_url else None,
          "status": FAILED_STATUS_FOR_REPORTING,
          "message": (
              str(e)
              if len(str(e)) > 1
              else "Check you shared the spreadsheet with the service account"
          ),
          "success": False,
      }
      logger.log_text(
          f"{FAILED_STATUS_FOR_REPORTING}: {json.dumps(logging_payload)}"
      )
      status = STATUS_FAILED
      message = logging_payload["message"]

    finally:

      _update_google_sheet(
          worksheet_url,
          tool_config["DUBBING_CONFIG"],
          row_num + 2,
          status,
          message if status == STATUS_FAILED else "",
          client=sheets_client,
      )


def _publish_pubsub(
    publisher_client: pubsub_v1.PublisherClient,
    project_id: str,
    pubsub_topic: str,
    payload: dict[str, Any],
):
  """Publishes a message to a given Pub/Sub topic.

  Args:
      publisher_client: A Pub/Sub publisher client instance.
      project_id: Google Cloud project ID.
      pubsub_topic: Name of the Pub/Sub topic to publish to.
      payload: The dictionary containing the message payload to publish.
  """
  topic_path_reporting = publisher_client.topic_path(project_id, pubsub_topic)
  publisher_client.publish(
      topic_path_reporting, data=bytes(json.dumps(payload), "utf-8")
  ).result()


def _init_google_sheet_client() -> gspread.Client:
  """Initializes and authenticates a gspread client.

  This function sets up the necessary credentials and authorization
  to interact with Google Sheets using the gspread library.

  Returns:
    A gspread.Client object authorized to access Google Sheets.
  """
  scopes = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
      "https://spreadsheets.google.com/feeds",
  ]

  credentials, _ = google.auth.default(scopes=scopes)
  client = gspread.authorize(credentials)

  return client


def _read_tool_config_from_google_sheet(
    default_config: dict[str, str],
    sheets_client: gspread.client,
    worksheet_url: str,
    config_sheet_name: str,
) -> List[dict[str, Any]]:
  """Reads the configuration parameters from a Google Sheet.

  Args:
    default_config: A dictionary containing the default configuration
      parameters.
    sheets_client: gspread client object.
    worksheet_url: The URL of the Google Sheet containing the configuration.
    config_sheet_name: The name of the sheet in the Google Sheet containing the
      configuration.

  Returns:
    A a list of dictionary containing the configuration parameters.
  """
  data = _load_data_from_google_sheet(
      worksheet_url, config_sheet_name, sheets_client, skip_rows=0
  )
  for i, k in enumerate(data.variable):
    default_config[k] = data.value[i]

  return default_config


def _read_dubbing_config_from_google_sheet(
    default_config: dict[str, str],
    sheets_client: gspread.client,
    worksheet_url: str,
    config_sheet_name: str,
) -> List[dict[str, str]]:
  """Reads the configuration parameters from a Google Sheet.

  Args:
    default_config: A dictionary containing the default configuration
      parameters.
    sheets_client: gspread client object.
    worksheet_url: The URL of the Google Sheet containing the configuration.
    config_sheet_name: The name of the sheet in the Google Sheet containing the
      configuration.

  Returns:
    A list of dictionary containing the configuration parameters.
  """
  data = _load_data_from_google_sheet(
      worksheet_url, config_sheet_name, sheets_client, skip_rows=0
  )
  lines = []

  for index, row in data.iterrows():
    line = {}
    for k in default_config.keys():
      line[k] = default_config[k] if (k not in row or not row[k]) else row[k]
    lines.append(line)

  return lines


def _load_data_from_google_sheet(
    url: str,
    worksheet_name: str,
    sheets_client: gspread.Client,
    skip_rows: int = 0,
) -> pd.DataFrame:
  """Loads data from a Google Sheet to pandas dataframe.

  Args:
    url: The URL of the Google Sheet.
    worksheet_name: The name of the worksheet to load data from.
    sheets_client: A gspread.Client object.
    skip_rows: The number of rows to skip from the beginning of the sheet.

  Returns:
    A pandas DataFrame containing the data from the specified Google Sheet.

  Raises:
    Exception: If there is an error loading data from the Google Sheet.
  """

  input_sheet = sheets_client.open_by_url(url)

  if worksheet_name:
    values = input_sheet.worksheet(worksheet_name).get_all_values()
  else:
    values = input_sheet.sheet1.get_all_values()

  return pd.DataFrame.from_records(
      values[skip_rows + 1 :], columns=values[skip_rows]
  )