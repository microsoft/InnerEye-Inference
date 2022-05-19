#  ------------------------------------------------------------------------------------------
#  Copyright (c) Microsoft Corporation. All rights reserved.
#  Licensed under the MIT License (MIT). See LICENSE in the repo root for license information.
#  ------------------------------------------------------------------------------------------

from enum import Enum
import logging
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, Optional
from azureml._restclient.constants import RunStatus
from azureml._restclient.exceptions import ServiceException
from azureml.core import Workspace, Run
from azureml.exceptions import WebserviceException
from flask import Flask, Response, make_response, jsonify, Request, request
from flask_injector import FlaskInjector
from injector import inject
from memory_tempfile import MemoryTempfile

from azure_config import AzureConfig
from configure import configure, API_AUTH_SECRET_HEADER_NAME, API_AUTH_SECRET
from submit_for_inference import DEFAULT_RESULT_IMAGE_NAME, submit_for_inference, SubmitForInferenceConfig

app = Flask(__name__)

RUNNING_OR_POST_PROCESSING = RunStatus.get_running_statuses() + RunStatus.get_post_processing_statuses()

root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)


# HTTP REST status codes.
class HTTP_STATUS_CODE(Enum):
    OK = 200
    CREATED = 201
    ACCEPTED = 202
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    INTERNAL_SERVER_ERROR = 500


# HTTP REST error messages, to be formatted as JSON.
ERROR_MESSAGES: Dict[HTTP_STATUS_CODE, Any] = {
    HTTP_STATUS_CODE.BAD_REQUEST: {
        'detail': 'Input file is not in correct format.',
        'title': 'InvalidInput'
    },
    HTTP_STATUS_CODE.UNAUTHORIZED: {
        'detail': 'Server failed to authenticate the request. '
                  f'Make sure the value of the {API_AUTH_SECRET_HEADER_NAME} header is populated.',
        'title': 'NoAuthenticationInformation'
    },
    HTTP_STATUS_CODE.FORBIDDEN: {
        'detail': 'Server failed to authenticate the request. '
                  f'Make sure the value of the {API_AUTH_SECRET_HEADER_NAME} header is correct.',
        'title': 'AuthenticationFailed'
    },
    HTTP_STATUS_CODE.NOT_FOUND: {
        'detail': 'The specified resource does not exist.',
        'title': 'ResourceNotFound'
    },
    HTTP_STATUS_CODE.INTERNAL_SERVER_ERROR: {
        'detail': 'The server encountered an internal error. Please retry the request.',
        'title': 'InternalError'
    },
}


class ERROR_EXTRA_DETAILS(Enum):
    INVALID_MODEL_ID = 'InvalidModelId'
    INVALID_ZIP_FILE = 'InvalidZipFile'
    RUN_CANCELLED = 'RunCancelled'
    INVALID_RUN_ID = 'InvalidRunId'


def make_error_response(error_code: HTTP_STATUS_CODE, extra_details: Optional[ERROR_EXTRA_DETAILS] = None) -> Response:
    """
    Format a Response object for an error_code.

    :param error_code: Error code.
    :param extra_details: Optional, any further information.
    :return: Flask Response object with JSON error message.
    """
    error_message = ERROR_MESSAGES[error_code]
    error_message['code'] = error_code.name
    error_message['status'] = error_code.value
    if extra_details is not None:
        error_message['extra_details'] = extra_details.value
    return make_response(jsonify(error_message), error_code.value)


def is_authenticated_request(req: Request) -> Optional[Response]:
    """
    Check request is authenticated.
    If API_AUTH_SECRET_HEADER_NAME is not in request headers then return 401.
    If API_AUTH_SECRET_HEADER_NAME is in request headers but incorrect then return 403.
    Else return none.
    :param req: Flask request object.
    :return: Response if error else None.
    """
    if API_AUTH_SECRET_HEADER_NAME not in req.headers:
        return make_error_response(HTTP_STATUS_CODE.UNAUTHORIZED)
    if req.headers[API_AUTH_SECRET_HEADER_NAME] != API_AUTH_SECRET:
        return make_error_response(HTTP_STATUS_CODE.FORBIDDEN)
    return None


@app.route("/v1/ping", methods=['GET'])
def ping() -> Response:
    authentication_response = is_authenticated_request(request)
    if authentication_response is not None:
        return authentication_response
    return make_response("", HTTP_STATUS_CODE.OK.value)


@inject
@app.route("/v1/model/start/<model_id>", methods=['POST'])
def start_model(model_id: str, workspace: Workspace, azure_config: AzureConfig) -> Response:
    authentication_response = is_authenticated_request(request)
    if authentication_response is not None:
        return authentication_response

    try:
        image_data: bytes = request.stream.read()
        logging.info(f'Starting {model_id}')
        config = SubmitForInferenceConfig(model_id=model_id, image_data=image_data, experiment_name=azure_config.experiment_name)
        run_id, _ = submit_for_inference(config, workspace, azure_config)
        response = make_response(run_id, HTTP_STATUS_CODE.CREATED.value)
        response.headers.set('Content-Type', 'text/plain')
        return response
    except WebserviceException as webException:
        if webException.message.startswith('ModelNotFound'):
            return make_error_response(HTTP_STATUS_CODE.NOT_FOUND,
                                       ERROR_EXTRA_DETAILS.INVALID_MODEL_ID)
        logging.error(webException)
        return make_error_response(HTTP_STATUS_CODE.INTERNAL_SERVER_ERROR)
    except Exception as fatal_error:
        logging.error(fatal_error)
        return make_error_response(HTTP_STATUS_CODE.INTERNAL_SERVER_ERROR)


def read_log_file(log_path: Path) -> str:
    """
    Given a log file path, returns the text in the log file if it exists.

    :param log_path: Path to log file.
    :return: Text in log file if it exists, empty string if not.
    """
    log_text = ""
    if log_path.exists():
        log_text = log_path.read_text()
    return log_text


def check_run_logs_for_zip_errors(run: Run) -> bool:
    """Checks AzureML log files for zip errors, both old and new runtime logs.

    :param run: object representing run to be checked.
    :return: True if zip error found in logs, False if not.
    """
    with tempfile.TemporaryDirectory() as tmpdirname:
        # Download the azureml-log files
        run.download_files(prefix="azureml-logs", output_directory=tmpdirname,
                            append_prefix=False)
        # In particular look for 70_driver_log.txt
        driver_log_path = Path(tmpdirname) / '70_driver_log.txt'
        driver_log = read_log_file(driver_log_path)
        if "zipfile.BadZipFile" in driver_log:
            return True

    return False

def get_cancelled_or_failed_run_response(run: Run, run_status: Any) -> Response:
    """Given a run object, generates an HTTP response based upon its status

    :param run: Object representing run to be cheked.
    :param run_status: Status of incomplete run.
    :return: HTTP response containing relevant information about run.
    """
    if run_status == RunStatus.FAILED:
        if check_run_logs_for_zip_errors(run):
            return make_error_response(HTTP_STATUS_CODE.BAD_REQUEST,
                            ERROR_EXTRA_DETAILS.INVALID_ZIP_FILE)

    elif run_status == RunStatus.CANCELED:
        return make_error_response(HTTP_STATUS_CODE.INTERNAL_SERVER_ERROR,
                                    ERROR_EXTRA_DETAILS.RUN_CANCELLED)
    return make_error_response(HTTP_STATUS_CODE.INTERNAL_SERVER_ERROR)


def get_completed_result_bytes(run: Run) -> Response:
    """Given a completed run, download the run result file as return as HTTP response.

    :param run: Object representing completed run.
    :return: HTTP response containing result bytes.
    """
    memory_tempfile = MemoryTempfile(fallback=True)
    with memory_tempfile.NamedTemporaryFile() as tf:
        file_name = str(tf.name)
        run.download_file(DEFAULT_RESULT_IMAGE_NAME, file_name)
        tf.seek(0)
        result_bytes = tf.read()
    response = make_response(result_bytes, HTTP_STATUS_CODE.OK.value)
    response.headers.set('Content-Type', 'application/zip')
    return response


@inject
@app.route("/v1/model/results/<run_id>", methods=['GET'])
def download_result(run_id: str, workspace: Workspace) -> Response:
    authentication_response = is_authenticated_request(request)
    if authentication_response is not None:
        return authentication_response

    logging.info(f"Checking run_id='{run_id}'")
    try:
        run = workspace.get_run(run_id)
        run_status = run.status
        if run_status in RUNNING_OR_POST_PROCESSING:
            return make_response("", HTTP_STATUS_CODE.ACCEPTED.value)
        logging.info(f"Run has completed with status {run.get_status()}")

        if run_status != RunStatus.COMPLETED:
            return get_cancelled_or_failed_run_response(run, run_status)

        return get_completed_result_bytes(run)

    except ServiceException as error:
        if error.status_code == 404:
            return make_error_response(HTTP_STATUS_CODE.NOT_FOUND,
                                       ERROR_EXTRA_DETAILS.INVALID_RUN_ID)
        logging.error(error)
        return make_error_response(HTTP_STATUS_CODE.INTERNAL_SERVER_ERROR)
    except Exception as fatal_error:
        logging.error(fatal_error)
        return make_error_response(HTTP_STATUS_CODE.INTERNAL_SERVER_ERROR)


# Setup Flask Injector, this has to happen *AFTER* routes are added
FlaskInjector(app=app, modules=[configure])
