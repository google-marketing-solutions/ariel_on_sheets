<!--
Copyright 2024 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

      https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

**Disclaimer: This is not an official supported Google product.**
Please use this tool responsibly. Avoid entering any sensitive or personal data, including your
own and that of others.

# Ariel on Sheets

Ariel on sheets is an interface to use the [Ariel](https://github.com/google-marketing-solutions/ariel)
library from Google Sheets.
While automatic dubbing from a video with speech, and scripted dubbing for source videos without
speech is present, the interactive tune process that Ariel library offers when used from
notebook s not available on Ariel on sheets.
This repository contains 2 Google Cloud Functions that automates video dubbing using Google
Cloud's latest LLM models and Text to speech technology. It aslo supports other voice providers
like Elevenlabs.
It's designed to be triggered by a Google Sheet, allowing users to easily dub videos in multiple
languages without writing any code.

## Pre-requisites

1. Follow the [Before You Begin Section](https://github.com/google-marketing-solutions/ariel?tab=readme-ov-file#before-you-begin) from the Ariel github repository.

## Installation Steps

1. `git clone` this repository
2. Navigate to the directory `ariel_on_sheets/terraform`
3. Edit the file `terraform.tfvars` replacing the values for your project:

   * `PROJECT_ID` = is the name of the Google Cloud project where you will deploy.i.e: "my-project"
   * `PROJECT_NUMBER` = is the number of the Google Cloud project. It's different from the name). i.e: "8888888"
   * `REGION` = the Google Cloud region where you will deploy. i.e: "us-central1"
   * `LOCATION` = the broader region where you will be deploying. i.e: "US"
   * `DEPLOYMENT_NAME` = The prefix to append to all the created resources so they can be easily identified. i.e:"ariel"
   * `SERVICE_ACCOUNT` = The name of the service account to be created. i.e:"ariel-sa"
   * `USER_LIST` = A list of emails separated by comma, representing the persons with access to the tool.
The emails must be accounts granted into the Google Cloud Project. i.e: "<myemail@somecompany.com>,<youremail@somecompany.com>"

4. Open a shell terminal and navigate to `ariel_on_sheets/terraform` directory. Execute the
command: `terraform apply`
5. If prompted to confirm the deployment type: `yes`
6. When everything completed successfully, make sure you write down the information displayed in
the console at the end of the process, i.e:

    * `PROJECT_NUMBER=8888888`
    * `ARIEL_SERVICE_ACCOUNT=ariel-sa@my-project.iam.gserviceaccount.com`
    * `ARIEL_ENDPOINT_URL=https://us-central1-my-project.cloudfunctions.net/ariel-splitter`

7. Make a copy of [this Google Spreadsheet](https://docs.google.com/spreadsheets/d/1F3vmKc8qyZ6bp4hMv0XeMZTmaQdX8OVI2Z3F8OhcSIU/edit?usp=sharing), it will be used to run ariel.
8. Open the sheet and grant edit permissions to the service account noted in step 6 and all the
members of the team who will be using the tool, defined on the `USER_LIST` of Step 3.
9. Open the Google Sheet, navigate to the `config` tab and replace the value of the following
variables obtained during the deployment process:

    * `ARIEL_ENDPOINT_URL`
    * `ARIELSERVICE_ACCOUNT`

10. On the menu bar on the top, click on `Extension` > `Apps Script`
11. On the new window, on the left pane menu, click on `Project Settings` and on the section
"Google Cloud Platform (GCP) Project", click on `Change Project` and add the value of `PROJECT_NUMBER` from Step 6.
12. You are all set!! Follow the instructions on the `instructions` tab of the sheet.