#  ------------------------------------------------------------------------------------------
#  Copyright (c) Microsoft Corporation. All rights reserved.
#  Licensed under the MIT License (MIT). See LICENSE in the repo root for license information.
#  ------------------------------------------------------------------------------------------

import random
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Optional
from unittest import mock

from app import ERROR_EXTRA_DETAILS, HTTP_STATUS_CODE, app
from azureml._restclient.constants import RunStatus
from azureml.core import Datastore, Experiment, Model, Workspace
from azureml.exceptions import WebserviceException
from configure import API_AUTH_SECRET, API_AUTH_SECRET_HEADER_NAME, get_azure_config
from download_model_and_run_scoring import DELETED_IMAGE_DATA_NOTIFICATION
from pydicom import dcmread
from submit_for_inference import (
    DEFAULT_RESULT_IMAGE_NAME, IMAGEDATA_FILE_NAME, SubmitForInferenceConfig, submit_for_inference
)
from werkzeug.test import TestResponse

# Timeout, in seconds, for Azure runs, 20 minutes.
TIMEOUT_IN_SECONDS = 20 * 60

# The directory containing this file.
THIS_DIR: Path = Path(__file__).parent.resolve()
# The TestData directory.
TEST_DATA_DIR: Path = THIS_DIR / "TestData"
# Test reference series.
TestDicomVolumeLocation: Path = TEST_DATA_DIR / "HN"

PASSTHROUGH_MODEL_ID = "PassThroughModel:1729"


def assert_response_error_type(response: TestResponse, status_code: HTTP_STATUS_CODE,
                               extra_details: Optional[ERROR_EXTRA_DETAILS] = None) -> None:
    """
    Assert that response contains an error, formatted as JSON.

    :param response: Response to test.
    :param status_code: Expected status code
    :param extra_details: Optional extra details.
    """
    assert response.content_type == 'application/json'
    # assert response.data == b''
    assert response.status_code == status_code.value
    response_json = response.json

    # this makes mypy happy that a dictionary has actually been returned 
    assert response_json is not None

    assert len(response_json['code']) > 0 
    assert len(response_json['detail']) > 0
    assert response_json['status'] == status_code.value
    assert len(response_json['title']) > 0
    if extra_details is not None:
        assert response_json['extra_details'] == extra_details.value
    else:
        assert 'extra_details' not in response_json


def test_ping_unauthorized() -> None:
    """
    Test "/v1/ping" with unauthorized GET.

    This should return HTTP status code 401 (unauthorized) and error content.
    """
    with app.test_client() as client:
        response = client.get("/v1/ping")
        assert_response_error_type(response, HTTP_STATUS_CODE.UNAUTHORIZED)


def test_ping_forbidden() -> None:
    """
    Test "/v1/ping" with unauthenticated GET.

    This should return HTTP status code 403 (forbidden) and error content.
    """
    with app.test_client() as client:
        response = client.get("/v1/ping",
                              headers={API_AUTH_SECRET_HEADER_NAME: 'forbidden'})
        assert_response_error_type(response, HTTP_STATUS_CODE.FORBIDDEN)


def test_ping_authenticated() -> None:
    """
    Test "/v1/ping" with authenticated GET.

    This should return HTTP status code 200 (ok) and no content.
    """
    with app.test_client() as client:
        response = client.get("/v1/ping",
                              headers={API_AUTH_SECRET_HEADER_NAME: API_AUTH_SECRET})
        assert response.content_type == 'text/html; charset=utf-8'
        assert response.data == b''
        assert response.status_code == HTTP_STATUS_CODE.OK.value


def test_model_start_unauthorized() -> None:
    """
    Test "/v1/model/start/<model_id>" with unauthorized POST.

    This should return HTTP status code 401 (unauthorized) and error content.
    """
    with app.test_client() as client:
        response = client.post("/v1/model/start/ValidModel:3")
        assert_response_error_type(response, HTTP_STATUS_CODE.UNAUTHORIZED)


def test_model_start_forbidden() -> None:
    """
    Test "/v1/model/start/<model_id>" with unauthenticated POST.

    This should return HTTP status code 403 (forbidden) and error content.
    """
    with app.test_client() as client:
        response = client.post("/v1/model/start/ValidModel:3",
                               headers={API_AUTH_SECRET_HEADER_NAME: 'forbidden'})
        assert_response_error_type(response, HTTP_STATUS_CODE.FORBIDDEN)


def test_model_start_authenticated_invalid_model_id() -> None:
    """
    Test "/v1/model/start/<model_id>" with authenticated POST but invalid model.

    This should return HTTP status code 404 (not found) and error message content.
    """
    # Patch Model.__init__ to raise WebserviceException as if the model_id is invalid.
    exception_message = "ModelNotFound: This is an invalid model id"
    with mock.patch.object(Model, "__init__", side_effect=WebserviceException(exception_message)):
        with app.test_client() as client:
            response = client.post("/v1/model/start/InvalidModel:1594",
                                   headers={API_AUTH_SECRET_HEADER_NAME: API_AUTH_SECRET})
            assert_response_error_type(response, HTTP_STATUS_CODE.NOT_FOUND,
                                       ERROR_EXTRA_DETAILS.INVALID_MODEL_ID)


def test_model_start_authenticated_valid_model_id() -> None:
    """
    Test "/v1/model/start/<model_id>" with authenticated POST and valid model.

    This should return status code 201 (Created) and run id as content.
    """
    # Mock an azureml.core.Run object to have attribute id=='test_run_id'.
    run_mock = mock.Mock(id='test_run_id')
    # Patch the method Experiment.submit to prevent the AzureML experiment actually running.
    with mock.patch.object(Experiment, 'submit', return_value=run_mock):
        with app.test_client() as client:
            response = client.post(f"/v1/model/start/{PASSTHROUGH_MODEL_ID}",
                                   headers={API_AUTH_SECRET_HEADER_NAME: API_AUTH_SECRET})
            assert response.status_code == HTTP_STATUS_CODE.CREATED.value
            assert response.content_type == 'text/plain'
            assert response.data == bytes(run_mock.id, 'utf-8')


def test_model_results_unauthorized() -> None:
    """
    Test "/v1/model/results/<run_id>" with unauthorized GET.

    This should return HTTP status code 401 (unauthorized) and error content.
    """
    with app.test_client() as client:
        response = client.get("/v1/model/results/test_run_id")
        assert_response_error_type(response, HTTP_STATUS_CODE.UNAUTHORIZED)


def test_model_results_forbidden() -> None:
    """
    Test "/v1/model/results/<run_id>" with unauthenticated GET.

    This should return HTTP status code 403 (forbidden) and error content.
    """
    with app.test_client() as client:
        response = client.get("/v1/model/results/test_run_id",
                              headers={API_AUTH_SECRET_HEADER_NAME: 'forbidden'})
        assert_response_error_type(response, HTTP_STATUS_CODE.FORBIDDEN)


def test_model_results_authenticated_invalid_run_id() -> None:
    """
    Test "/v1/model/results/<run_id>" with authenticated GET but invalid run_id.

    This should return HTTP status code 404 (not found) and error content.
    """
    # Patch the method Workspace.get_run to raise an exception as if the run_id was invalid.
    # exception_object = mock.Mock(response=mock.Mock(status_code=404))
    # with mock.patch.object(Workspace, 'get_run', side_effect=ServiceException(exception_object)):
    with app.test_client() as client:
        response = client.get("/v1/model/results/invalid_run_id",
                              headers={API_AUTH_SECRET_HEADER_NAME: API_AUTH_SECRET})
        assert_response_error_type(response, HTTP_STATUS_CODE.NOT_FOUND,
                                   ERROR_EXTRA_DETAILS.INVALID_RUN_ID)


def test_model_results_authenticated_valid_run_id_in_progress() -> None:
    """
    Test "/v1/model/results/<run_id>" with authenticated GET, valid run_id but still in progress.

    This should return HTTP status code 202 (accepted) and no content.
    """
    # Mock an azureml.core.Run object to run status=='NOT_STARTED'.
    run_mock = mock.Mock(status=RunStatus.NOT_STARTED)
    # Patch the method Workspace.get_run to return the mock run object.
    with mock.patch.object(Workspace, 'get_run', return_value=run_mock):
        with app.test_client() as client:
            response = client.get("/v1/model/results/valid_run_id",
                                  headers={API_AUTH_SECRET_HEADER_NAME: API_AUTH_SECRET})
            assert response.content_type == 'text/html; charset=utf-8'
            assert response.data == b''
            assert response.status_code == HTTP_STATUS_CODE.ACCEPTED.value


def test_model_results_authenticated_valid_run_id_completed() -> None:
    """
    Test "/v1/model/results/<run_id>" with authenticated GET, valid run_id and completed.

    This should return HTTP status code 200 (accepted) and binary content.
    """
    # Get a random 1Kb
    random_bytes = bytes([random.randint(0, 255) for _ in range(0, 1024)])

    def download_file(name: str, output_file_path: str) -> None:
        with open(output_file_path, "wb+") as f:
            f.write(random_bytes)

    # Create a mock azure.core.Run object
    run_mock = mock.Mock(status=RunStatus.COMPLETED, download_file=download_file)
    # Patch the method Workspace.get_run to return the mock run object.
    with mock.patch.object(Workspace, 'get_run', return_value=run_mock):
        with app.test_client() as client:
            response = client.get("/v1/model/results/valid_run_id",
                                  headers={API_AUTH_SECRET_HEADER_NAME: API_AUTH_SECRET})
            assert response.content_type == 'application/zip'
            assert response.data == random_bytes
            assert response.status_code == HTTP_STATUS_CODE.OK.value


def create_zipped_dicom_series() -> bytes:
    """
    Create a test zipped DICOM series.

    There are 3 slices of a full reference DICOM series in the folder TestDicomVolumeLocation.
    Create a zip file containing them, read the binary data and then clean up the zip file.

    :return: Binary contents of a zipped DICOM series.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        zipped_dicom_file = Path(temp_dir) / "temp.zip"
        shutil.make_archive(str(zipped_dicom_file.with_suffix('')), 'zip', str(TestDicomVolumeLocation))
        with open(zipped_dicom_file, 'rb') as f:
            return f.read()


def submit_for_inference_and_wait(model_id: str, data: bytes) -> Any:
    """
    Submit a model and data to the inference service and wait until it has completed or failed.

    :param model_id: Model id to submit.
    :param data: Data to submit.
    :return: POST response.
    """
    with app.test_client() as client:
        response = client.post(f"/v1/model/start/{model_id}",
                               data=data,
                               headers={API_AUTH_SECRET_HEADER_NAME: API_AUTH_SECRET})
        assert response.status_code == HTTP_STATUS_CODE.CREATED.value
        assert response.content_type == 'text/plain'
        run_id = response.data.decode('utf-8')
        assert run_id is not None

        start = time.time()
        while True:
            response = client.get(f"/v1/model/results/{run_id}",
                                  headers={API_AUTH_SECRET_HEADER_NAME: API_AUTH_SECRET})
            if response.status_code != HTTP_STATUS_CODE.ACCEPTED.value:
                return response

            assert response.content_type == 'text/html; charset=utf-8'
            assert response.data == b''
            end = time.time()
            assert end - start < TIMEOUT_IN_SECONDS
            time.sleep(1)


def test_submit_for_inference_end_to_end() -> None:
    """
    Test that submitting a zipped DICOM series to model PASSTHROUGH_MODEL_ID returns
    the expected DICOM-RT format.
    """
    image_data = create_zipped_dicom_series()
    assert len(image_data) > 0
    response = submit_for_inference_and_wait(PASSTHROUGH_MODEL_ID, image_data)
    assert response.content_type == 'application/zip'
    assert response.status_code == HTTP_STATUS_CODE.OK.value
    # Create a scratch directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        # Store the response data in a file.
        response_file_name = temp_dir_path / "response.zip"
        response_file_name.write_bytes(response.data)
        # Check that the response data can be unzipped.
        extraction_folder_path = temp_dir_path / "unpack"
        with zipfile.ZipFile(response_file_name, 'r') as zip_file:
            zip_file.extractall(extraction_folder_path)
        # Check that there is a single file in the zip, not in a directory.
        extracted_files = list(extraction_folder_path.glob('**/*'))
        print(extracted_files)
        assert len(extracted_files) == 1
        extracted_file = extracted_files[0]
        assert extracted_file.is_file()
        relative_path = extracted_file.relative_to(extraction_folder_path)
        # Strip off the final .zip suffix
        assert relative_path == Path(DEFAULT_RESULT_IMAGE_NAME).with_suffix("")

        with open(extracted_file, 'rb') as infile:
            ds = dcmread(infile)
        assert ds is not None
        # Check the modality
        assert ds.Modality == 'RTSTRUCT'
        assert ds.Manufacturer == 'Default_Manufacturer'
        assert ds.SoftwareVersions == PASSTHROUGH_MODEL_ID
        # Check the structure names
        expected_structure_names = ["SpinalCord", "Lung_R", "Lung_L", "Heart", "Esophagus"]
        assert len(ds.StructureSetROISequence) == len(expected_structure_names)
        for i, item in enumerate(expected_structure_names):
            assert ds.StructureSetROISequence[i].ROINumber == i + 1
            assert ds.StructureSetROISequence[i].ROIName == item
            assert ds.RTROIObservationsSequence[i].RTROIInterpretedType == "ORGAN"
            assert "Default_Interpreter" in ds.RTROIObservationsSequence[i].ROIInterpreter
        assert len(ds.ROIContourSequence) == len(expected_structure_names)
        for i, item in enumerate(expected_structure_names):
            assert ds.ROIContourSequence[i].ReferencedROINumber == i + 1
    # Download image data zip, which should now have been overwritten


def test_submit_for_inference_bad_image_file() -> None:
    """
    Test submitting a random file instead of a zipped DICOM series.

    This should fail because the input file is not a zip file.
    """
    # Get a random 1Kb
    image_data = bytes([random.randint(0, 255) for _ in range(0, 1024)])
    response = submit_for_inference_and_wait(PASSTHROUGH_MODEL_ID, image_data)
    assert_response_error_type(response, HTTP_STATUS_CODE.BAD_REQUEST,
                               ERROR_EXTRA_DETAILS.INVALID_ZIP_FILE)


def test_submit_for_inference_image_data_deletion() -> None:
    """
    Test that the image data zip is overwritten after the inference runs
    """
    image_data = create_zipped_dicom_series()
    azure_config = get_azure_config()
    workspace = azure_config.get_workspace()
    config = SubmitForInferenceConfig(
        model_id=PASSTHROUGH_MODEL_ID,
        image_data=image_data,
        experiment_name=azure_config.experiment_name)
    run_id, datastore_image_path = submit_for_inference(config, workspace, azure_config)
    run = workspace.get_run(run_id)
    run.wait_for_completion()
    image_datastore = Datastore(workspace, azure_config.datastore_name)
    with tempfile.TemporaryDirectory() as temp_dir:
        image_datastore.download(
            target_path=temp_dir,
            prefix=datastore_image_path,
            overwrite=False,
            show_progress=False)
        temp_dir_path = Path(temp_dir)
        image_data_zip_path = temp_dir_path / datastore_image_path / IMAGEDATA_FILE_NAME
        with image_data_zip_path.open() as image_data_file:
            first_line = image_data_file.readline().strip()
            assert first_line == DELETED_IMAGE_DATA_NOTIFICATION
