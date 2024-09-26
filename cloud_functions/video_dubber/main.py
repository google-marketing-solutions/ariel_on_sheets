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

import ast
import base64
from datetime import datetime
import json
import os
import sys
import traceback
from typing import Any
from ariel.dubbing import Dubber
import functions_framework
import google.auth
from google.cloud import logging
from google.cloud import storage
import gspread
import pandas as pd
import tensorflow as tf


VOICE_PROVIDER_ELEVENLABS = "ElevenLabs"
VOICE_PROVIDER_GOOGLE = "Google"

STATUS_FAILED = "FAILED"
STATUS_SUCCESS = "OK"

sheet_client = None

FAILED_STATUS_FOR_REPORTING = "ERROR_IN_ARIEL_VIDEO_DUBBER"
CF_NAME = "ariel_video_dubber"

def _update_google_sheet(
    url: str,
    worksheet_name: str,
    row: int,
    status_columns: dict[str, str],
    status: str,
    message: str,
    client: gspread.Client,
) -> gspread.Worksheet:
  """Updates a Google Sheet with the status and message of a processing step.

  Args:
    url: The URL of the Google Sheet.
    worksheet_name: The name of the worksheet to update.
    row: The row number to update.
    status_columns: A dictionary containing the column letters for
      'STATUS_COLUMN', 'UPDATED_AT' and 'MESSAGE_COLUMN'.
    status: The status to write to the sheet (e.g., 'OK', 'FAILED').
    message: A detailed message about the status, including any errors.
    client: An authenticated gspread client object.

  Returns:
    The updated gspread.Worksheet object.
  """

  current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  sheet = client.open_by_url(url)
  sheet.worksheet(worksheet_name).update(
      f"{status_columns['STATUS_COLUMN']}{row}:{status_columns['MESSAGE_COLUMN']}{row}",
      [[status, current_datetime, message]],
  )


def _build_file_name(line_config: pd.DataFrame, file_name: str) -> str:
  """Builds the file name using the naming convention."""

  path = line_config["output_naming_convention"].format(**line_config)

  return f"{path}.{file_name.split('.')[-1]}"


def _configure_dubber(
    tool_config: pd.DataFrame, line_config: pd.DataFrame, output_directory: str
) -> Dubber:
  """Configures and initializes a Dubber instance.

  This function sets up a Dubber object with configurations from both
  tool_config and line_config DataFrames. It handles the creation of
  the output directory if it doesn't exist.

  Args:
    tool_config: DataFrame containing tool-level configurations.
    line_config: DataFrame containing line-specific configurations.
    output_directory: string containing the directory name to save temporary files.

  Returns:
    A configured Dubber instance ready for dubbing operations.
  """
  dubber = None

  bucket = line_config["video_url"].split("/")[0]
  file_name = ("/").join(line_config["video_url"].split("/")[1:])

  if not tf.io.gfile.exists(output_directory):
    tf.io.gfile.makedirs(output_directory)

  download_file_path = f"{output_directory}/{file_name.split('/')[-1]}"
  _download_file_from_gcs(bucket, file_name, download_file_path)

  # print(line_config)
  dubber = Dubber(
      input_file=download_file_path,
      output_directory=output_directory,
      advertiser_name=line_config["campaign_name"],
      original_language=line_config["original_language"],
      target_language=line_config["target_language"],
      number_of_speakers=int(line_config["number_of_speakers"]),
      gemini_token=tool_config["AI_STUDIO_API_KEY"],
      hugging_face_token=tool_config["HUGGING_FACE_ACCESS_TOKEN"],
      no_dubbing_phrases=ast.literal_eval(line_config["no_dubbing_phrases"]),
      diarization_instructions=line_config["diarization_instructions"],
      translation_instructions=line_config["translation_instructions"],
      merge_utterances=line_config["merge_utterances"],
      minimum_merge_threshold=float(line_config["minimum_merge_threshold"]),
      preferred_voices=ast.literal_eval(line_config["preferred_voice_family"]),
      adjust_speed=line_config["adjust_speed"].lower() == "true",
      vocals_volume_adjustment=float(line_config["vocals_volume_adjustment"]),
      background_volume_adjustment=float(
          line_config["background_volume_adjustment"]
      ),
      clean_up=line_config["clean_up"],
      gemini_model_name=line_config["gemini_model_name"],
      temperature=float(line_config["gemini_temperature"]),
      top_p=float(line_config["gemini_top_p"]),
      top_k=int(line_config["gemini_top_k"]),
      max_output_tokens=int(line_config["gemini_maximum_output_tokens"]),
      use_elevenlabs=VOICE_PROVIDER_ELEVENLABS in line_config["voice_provider"],
      elevenlabs_token=tool_config["ELEVEN_LABS_API_KEY"],
      elevenlabs_clone_voices=line_config["clone_original_voices"].lower() == "true",
      with_verification=line_config["with_verification"].lower() == "true",
  )

  return dubber


@functions_framework.cloud_event
def run(cloud_event: dict[str, Any]) -> tuple[str, int]:
  """Triggers the message processing.

  Args:
    cloud_event (dict):  The dictionary with data specific to this type of
      event. The `data` field contains the PubsubMessage message. The
      `attributes` field will contain custom attributes if there are any.
  Returns:
    A tuple of a string with the result message and an integer with the 
    error code.
  """

  required_elem = [
      "PROJECT_ID",
      "REGION",
      "SERVICE_ACCOUNT",
      "DEPLOYMENT_NAME",
      "OUTPUT_DIRECTORY"
  ]
  logging_client = logging.Client()
  log_name = CF_NAME
  logger = logging_client.logger(log_name)

  if not all(elem in os.environ for elem in required_elem):
    logger.log_text(
        f"{FAILED_STATUS_FOR_REPORTING}: Cannot proceed, there are missing"
        " input values please make sure you set all the environment variables"
        " correctly."
    )
    sys.exit(1)

  output_directory = os.environ["OUTPUT_DIRECTORY"]
  log_name = os.environ["DEPLOYMENT_NAME"] + CF_NAME
  msg_data = base64.b64decode(cloud_event.data["message"]["data"]).decode(
      "utf-8"
  )
  request_json = json.loads(msg_data)

  try:
    worksheet_url = request_json["worksheet_url"]
    tool_config = request_json["tool_config"]
    line_config = request_json["line_config"]
    status_columns = request_json["status_columns"]

    sheets_client = _init_google_sheet_client()

    (status, message) = _process_line(
        tool_config, line_config, worksheet_url, logger, output_directory
    )

    _update_google_sheet(
        worksheet_url,
        tool_config["DUBBING_CONFIG"],
        int(line_config["row_num"]) + 2,
        status_columns,
        status,
        message,
        client=sheets_client,
    )

    return "OK", 200

  except Exception as e:
    traceback.print_exc()
    _update_google_sheet(
        worksheet_url,
        tool_config["DUBBING_CONFIG"],
        int(line_config["row_num"]) + 2,
        status_columns,
        status,
        str(e),
        client=sheets_client,
    )
    return "Error", 500

def _dub_ad_from_script_elevenlabs(
    dubber: Dubber,
    script: dict[str, Any],
    tts_params: dict[str, Any],
    voices: dict[str, str],
):
  """Dubs an ad from a script using ElevenLabs voices.

  This function configures a Dubber instance, performs dubbing based on
  the specified target language(s), saves the output file(s) to the
  designated bucket, and updates the Google Sheet with the status and
  output file path(s).

  Args:
    dubber: Dubber instance to use for dubbing.
    script: dict with alll the utterances.
    tts_params: dict containing tts-specific configurations.
    voices: dict containing the assigned voice for each language.
  """

  dubber.dub_ad_from_script(
      script_with_timestamps=script,
      elevenlabs_text_to_speech_parameters=tts_params,
      assigned_voice=voices,
  )

def _dub_ad_from_script_google(
    dubber: Dubber,
    script: dict[str, Any],
    tts_params: dict[str, Any],
    voices: dict[str, str],
):
  """Dubs an ad from a script using Google voices.

  This function configures a Dubber instance, performs dubbing based on
  the specified target language(s), saves the output file(s) to the
  designated bucket, and updates the Google Sheet with the status and
  output file path(s).dict[str, Any],

  Args:
    dubber: Dubber instance to use for dubbing.
    script: dict with alll the utterances.
    tts_params: dict containing tts-specific configurations.
    voices: dict containing the assigned voice for each language.
  """

  dubber.dub_ad_from_script(
      script_with_timestamps=script,
      google_text_to_speech_parameters=tts_params,
      assigned_voice=voices,
  )


def _process_line(
    tool_config: pd.DataFrame,
    line_config: dict[str, Any],
    worksheet_url: str,
    logger: logging.Logger,
    output_directory: str
) -> tuple[str, str]:
  """Processes each line in the dubbing configuration.

  This function iterates through each row of the dubbing configuration
  DataFrame, configures a Dubber instance, performs dubbing based on
  the specified target language(s), saves the output file(s) to the
  designated bucket, and updates the Google Sheet with the status and
  output file path(s).

  Args:
    tool_config: DataFrame containing tool-level configurations.
    line_config: dict containing line-specific configurations.
    worksheet_url: The URL of the Google Sheet containing the configuration.
    logger: logging.Logger object for logging events and errors.
    output_directory: string containing the directory path to store temporary files.
  Returns:
    Tuple of string with status and string with message. 
  """

  output_files_paths = []
  status = STATUS_SUCCESS
  dubber = None

  try:

    line_config["script"] = ast.literal_eval(line_config["script"])
    voices = json.loads(line_config["voices"])

    target_languages = ast.literal_eval(line_config["target_language"])

    for language in target_languages:
      status = STATUS_SUCCESS
      message = ""
      line_config["target_language"] = language

      if line_config["script"]:
        dubber = _configure_dubber(tool_config, line_config, output_directory)

        if dubber.use_elevenlabs:
          _dub_ad_from_script_elevenlabs(dubber,
                                         line_config["script"],
                                         json.loads(line_config["tts_params"]),
                                         voices[line_config["target_language"]])
        else:
          _dub_ad_from_script_google(dubber,
                                         line_config["script"],
                                         json.loads(line_config["tts_params"]),
                                         voices[line_config["target_language"]])

        dubbed_file_name = dubber.postprocessing_output.video_file
        output_file_name = _build_file_name(line_config, dubbed_file_name)
        output_files_paths.append(
            _upload_file_to_gcs(
                line_config["output_bucket"], dubbed_file_name, output_file_name
            )
        )

      else:

        dubber = _configure_dubber(tool_config, line_config, output_directory)
        dubber.dub_ad()
        dubbed_file_name = dubber.postprocessing_output.video_file
        output_file_name = _build_file_name(line_config, dubbed_file_name)
        output_files_paths.append(
            _upload_file_to_gcs(
                line_config["output_bucket"], dubbed_file_name, output_file_name
            )
        )

  except Exception as e:
    traceback.print_exc()
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

    try:
      dubber.clean_up()
    except Exception as e:
      None

  return (
      status,
      message 
      if status == STATUS_FAILED else
      ",".join(output_files_paths),
  )


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


def _upload_file_to_gcs(
    bucket_name: str, source_file_name: str, destination_blob_name: str
) -> str:
  """Uploads a file to a Google Cloud Storage bucket.

  Args:
      bucket_name: Name of the GCS bucket.
      source_file_name: Path to the local file to upload.
      destination_blob_name: Name of the blob in the bucket.

  Returns:
      The full GCS path (gs://...) of the uploaded blob.
  """

  storage_client = storage.Client()
  bucket = storage_client.bucket(bucket_name)
  blob = bucket.blob(destination_blob_name)

  blob.upload_from_filename(source_file_name, if_generation_match=None)

  print(f"File {source_file_name} uploaded to {destination_blob_name}.")

  return f"gs://{bucket_name}/{destination_blob_name}"


def _download_file_from_gcs(
    bucket_name: str, source_blob_name: str, destination_file_name: str
):
  """Downloads a file from a Google Cloud Storage bucket.

  Args:
      bucket_name: Name of the GCS bucket.
      source_blob_name: Name of the blob in the bucket to download.
      destination_file_name: Path to save the downloaded file locally.
  """

  storage_client = storage.Client()
  bucket = storage_client.bucket(bucket_name)

  blob = bucket.blob(source_blob_name)
  blob.download_to_filename(destination_file_name)