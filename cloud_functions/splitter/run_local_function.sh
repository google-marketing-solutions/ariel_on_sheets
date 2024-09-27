#!/bin/bash
# Tests the initial call
#
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
export DEPLOYMENT_NAME="copycat"
export PROJECT_ID="<SET_PROJECT_HERE>"
export REGION="us-central1"
export SERVICE_ACCOUNT="<SET_SA_HERE>"
export PUBSUB_TOPIC="ariel_dub_video"

#cp -R ../../lib ./

functions-framework --target=run