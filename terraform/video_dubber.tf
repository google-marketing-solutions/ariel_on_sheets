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

resource "google_cloud_run_v2_service_iam_binding" "video_dubber_cf_cr_binding" {
  location = google_cloudfunctions2_function.video_dubber.location
  project  = google_cloudfunctions2_function.video_dubber.project
  name     = google_cloudfunctions2_function.video_dubber.name
  role     = "roles/run.invoker"
  members = [
    "serviceAccount:${google_service_account.sa.email}",
    "serviceAccount:${var.PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
    ]
}

resource "google_cloud_run_v2_service_iam_binding" "video_dubber_cf_srva_binding" {
  location = google_cloudfunctions2_function.video_dubber.location
  project  = google_cloudfunctions2_function.video_dubber.project
  name     = google_cloudfunctions2_function.video_dubber.name
  role     = "roles/cloudfunctions.serviceAgent"
  members = [
    "serviceAccount:${google_service_account.sa.email}",
    "serviceAccount:${var.PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
  ]
}

data "archive_file" "video_dubber_archive" {
  type        = "zip"
  output_path = ".temp/video_dubber_code_source.zip"
  source_dir  = "${path.module}/../cloud_functions/video_dubber/"

  depends_on = [ google_storage_bucket.ariel_build_bucket,
  #null_resource.add_ariel_lib
  ]
}

resource "google_storage_bucket_object" "video_dubber_object" {
  name       = "${var.DEPLOYMENT_NAME}-video-dubber-${data.archive_file.video_dubber_archive.output_sha256}.zip"
  bucket     = google_storage_bucket.ariel_build_bucket.name
  source     = data.archive_file.video_dubber_archive.output_path
  depends_on = [data.archive_file.video_dubber_archive,
  #null_resource.add_ariel_lib
  ]
  lifecycle {
    replace_triggered_by = [
      #null_resource.add_ariel_lib
    ]
  }
}

resource "google_cloudfunctions2_function" "video_dubber" {
  name        = "${var.DEPLOYMENT_NAME}-video-dubber"
  description = "It runs a ariel execution receiving and input google sheet URL and the name of the sheet with the configuration"
  project     = var.PROJECT_ID
  location    = var.REGION
  depends_on = [ #null_resource.clone_ariel_repo,
  google_storage_bucket.ariel_build_bucket,
  #null_resource.add_ariel_lib,
  google_storage_bucket_object.video_dubber_object,
  time_sleep.wait_60s]

  build_config {
    runtime     = "python310"
    entry_point = "run" # Set the entry point
    service_account = google_service_account.sa.name
    environment_variables = {
      BUILD_CONFIG_TEST = "build_test"
    }
    source {
      storage_source {
        bucket = google_storage_bucket.ariel_build_bucket.name
        object = google_storage_bucket_object.video_dubber_object.name
      }
    }
  }

  service_config {
    min_instance_count = 0
    available_cpu = 8
    available_memory   = "16Gi"
    timeout_seconds    = 540
    environment_variables = {
      PROJECT_ID      = var.PROJECT_ID
      DEPLOYMENT_NAME = var.DEPLOYMENT_NAME
      SERVICE_ACCOUNT = google_service_account.sa.email
      REGION          = var.REGION
      OUTPUT_DIRECTORY  = var.OUTPUT_DIRECTORY
    }
    #ingress_settings               = "ALLOW_INTERNAL_ONLY"
    all_traffic_on_latest_revision = true
    service_account_email          = google_service_account.sa.email
  }

  event_trigger {
    trigger_region = var.REGION
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic   = google_pubsub_topic.ariel_topic.id
    retry_policy   = "RETRY_POLICY_RETRY"
  }

  lifecycle {
    ignore_changes = [
      # Ignore changes to generation
      build_config[0].source[0].storage_source[0].generation
    ]
  }
}