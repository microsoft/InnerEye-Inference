# Introduction

InnerEye-Inference is a AppService webapp in python to run inference on medical imaging models trained with the [InnerEye-DeepLearning toolkit](https://github.com/microsoft/InnerEye-Inference).

You can also integrate this with DICOM using the  [InnerEye-Gateway](https://github.com/microsoft/InnerEye-Gateway)

## Getting Started

### Installing Conda or Miniconda

Download a Conda or Miniconda [installer for your platform](https://docs.conda.io/en/latest/miniconda.html)
and run it.

### Creating a Conda environment

Note that in order to create the Conda environment you will need to have build tools installed on your machine. If you are running Windows, they should be already installed with Conda distribution.

You can install build tools on Ubuntu (and Debian-based distributions) by running
`sudo apt-get install build-essential`.
If you are running CentOS/RHEL distributions, you can install the build tools by running
`yum install gcc gcc-c++ kernel-devel make`.

#### Linux Users

Start the `conda` prompt for your platform. In that prompt, navigate to your repository root and run

```console
conda env create --file environment.yml
conda activate inference
```

#### Windows Users

Start the `conda` prompt for your platform. In that prompt, navigate to your repository root and run

```console
conda env create --file environment_win.yml
conda activate inference
```

### Configuration

Add this script with name set_environment.sh to set your env variables. This can be executed in Linux. The code will read the file if the environment variables are not present.

```bash
#!/bin/bash
export CUSTOMCONNSTR_AZUREML_SERVICE_PRINCIPAL_SECRET=
export CUSTOMCONNSTR_API_AUTH_SECRET=
export CLUSTER=
export WORKSPACE_NAME=
export EXPERIMENT_NAME=
export RESOURCE_GROUP=
export SUBSCRIPTION_ID=
export APPLICATION_ID=
export TENANT_ID=
export DATASTORE_NAME=
export IMAGE_DATA_FOLDER=
```

Run with `source set_environment.sh`

### Running flask app locally

* `flask run` to test it locally

### Testing flask app locally

The app can be tested locally using [`curl`](https://curl.se/).

#### Ping

To check that the server is running, issue this command from a local shell:

```console
curl -i -H "API_AUTH_SECRET: <val of CUSTOMCONNSTR_API_AUTH_SECRET>" http://localhost:5000/v1/ping
```

This should produce an output similar to:

```text
HTTP/1.0 200 OK
Content-Type: text/html; charset=utf-8
Content-Length: 0
Server: Werkzeug/1.0.1 Python/3.7.3
Date: Wed, 18 Aug 2021 11:50:20 GMT
```

#### Start

To test DICOM image segmentation of a file, first create `Tests/TestData/HN.zip` containing a zipped set of the test DICOM files in `Tests/TestData/HN`. Then assuming there is a model `PassThroughModel:4`, issue this command:

```text
curl -i \
    -X POST \
    -H "API_AUTH_SECRET: <val of CUSTOMCONNSTR_API_AUTH_SECRET>" \
    --data-binary @Tests/TestData/HN.zip \
    http://localhost:5000/v1/model/start/PassThroughModel:4
```

This should produce an output similar to:

```text
HTTP/1.0 201 CREATED
Content-Type: text/plain
Content-Length: 33
Server: Werkzeug/1.0.1 Python/3.7.3
Date: Wed, 18 Aug 2021 13:00:13 GMT

api_inference_1629291609_fb5dfdf9
```

here `api_inference_1629291609_fb5dfdf9` is the run id for the newly submitted inference job.

#### Results

To monitor the progress of the previously submitted inference job, issue this command:

```console
curl -i \
    -H "API_AUTH_SECRET: <val of CUSTOMCONNSTR_API_AUTH_SECRET>" \
    --head \
    http://localhost:5000/v1/model/results/api_inference_1629291609_fb5dfdf9 \
    --next \
    -H "API_AUTH_SECRET: <val of CUSTOMCONNSTR_API_AUTH_SECRET>" \
    --output "HN_rt.zip" \
    http://localhost:5000/v1/model/results/api_inference_1629291609_fb5dfdf9
```

If the run is still in progress then this should produce output similar to:

```text
HTTP/1.0 202 ACCEPTED
Content-Type: text/html; charset=utf-8
Content-Length: 0
Server: Werkzeug/1.0.1 Python/3.7.3
Date: Wed, 18 Aug 2021 13:45:20 GMT

  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:--  0:00:01 --:--:--     0
```

If the run is complete then this should produce an output similar to:

```text
HTTP/1.0 200 OK
Content-Type: application/zip
Content-Length: 131202
Server: Werkzeug/1.0.1 Python/3.7.3
Date: Wed, 18 Aug 2021 14:01:27 GMT

  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100  128k  100  128k    0     0   150k      0 --:--:-- --:--:-- --:--:--  150k
```

and download the inference result as a zipped DICOM-RT file to `HN_rt.zip`.

### Running flask app in Azure

1. Install Azure CLI: `curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash`
2. Login: `az login --use-device-code`
3. Deploy: `az webapp up --sku S1 --name test-python12345 --subscription <your_subscription_name> -g InnerEyeInference --location <your region>`
4. In the Azure portal go to Monitoring > Log Stream for debugging logs

### Deployment build

If you would like to reproduce the automatic deployment of the service for testing purposes:

* `az ad sp create-for-rbac --name "<name>" --role contributor --scope /subscriptions/<subs>/resourceGroups/InnerEyeInference --sdk-auth`
* The previous command will return a json object with the content for the variable `secrets.AZURE_CREDENTIALS` .github/workflows/deploy.yml

## Images

During inference the image data zip file is copied to the IMAGE_DATA_FOLDER in the AzureML workspace's DATASTORE_NAME datastore. At the end of inference the copied image data zip file is overwritten with a simple line of text. At present we cannot delete these. If you would like these overwritten files removed from your datastore you can [add a policy](https://docs.microsoft.com/en-us/azure/storage/blobs/storage-lifecycle-management-concepts?tabs=azure-portal) to delete items from the datastore after a period of time. We recommend 7 days.

## Changing Primary Dependencies

1. Make your desired changes in `primary_deps.yml`. Make sure your package name and version are correct.
2. To create a new environment and a valid `environment.yml`, run the following command:

 ```shell
 bash -i create_and_lock_environment.sh
 ```

3. Voila! You will now have a new conda environment with your desired primary package versions, as well as a new `environment.yml` which can be ingested by AzureML to create a copy of your local environment.

## Help and Bug Reporting

1. [Guidelines for how to report bug.](./docs/BugReporting.md)

## Licensing

[MIT License](LICENSE)

**You are responsible for the performance and any necessary testing or regulatory clearances for any models generated**

## Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit the [Microsoft CLA site](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Disclaimer
The InnerEye-DeepLearning toolkit, InnerEye-Gateway and InnerEye-Inference (collectively the “Research Tools”) are provided AS-IS for use by third parties for the purposes of research, experimental design and testing of machine learning models. The Research Tools are not intended or made available for clinical use as a medical device, clinical support, diagnostic tool, or other technology intended to be used in the diagnosis, cure, mitigation, treatment, or prevention of disease or other conditions. The Research Tools are not designed or intended to be a substitute for professional medical advice, diagnosis, treatment, or judgment and should not be used as such. All users are responsible for reviewing the output of the developed model to determine whether the model meets the user’s needs and for validating and evaluating the model before any clinical use. Microsoft does not warrant that the Research Tools or any materials provided in connection therewith will be sufficient for any medical purposes or meet the health or medical requirements of any person.

## Microsoft Open Source Code of Conduct

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).

## Resources

* [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/)
* [Microsoft Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/)
* Contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with questions or concerns
