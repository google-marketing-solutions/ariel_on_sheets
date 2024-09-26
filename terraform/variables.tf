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

variable "PROJECT_ID" {
  type        = string
  description = "GCP Project ID."
}

variable "PROJECT_NUMBER" {
  type        = string
  description = "GCP Project number, to build the system service accounts name."
}

variable "LOCATION" {
  type        = string
  description = "GCP region https://cloud.google.com/compute/docs/regions-zones."
  default     = "US"
}
variable "REGION" {
  type        = string
  description = "GCP region https://cloud.google.com/compute/docs/regions-zones."
  default     = "us-central1"
}

variable "DEPLOYMENT_NAME" {
  type        = string
  description = "Solution name to add to the Cloud Functions, secrets and scheduler names."
  default     = "ariel"
}

variable "SERVICE_ACCOUNT" {
  type        = string
  description = "Service Account for running ariel."
  default     = "ariel"
}

variable "BUILD_GCS_BUCKET" {
  type        = string
  description = "Cloud Storage bucket for building cloud functions."
  default     = "build"
}

variable "USER_LIST" {
  type = string
  description = "The list of users email to grant access to ariel separated by comma"
  default = ""
}

variable "OUTPUT_DIRECTORY" {
  type = string
  description = "The directory where to write the files while being processed"
  default = "/tmp"
}

variable "PUBSUB_TOPIC" {
  type = string
  description = "The topic to communicate splitter with video dubber"
  default = "dub_video"
}
