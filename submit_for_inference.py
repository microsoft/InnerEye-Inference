#  ------------------------------------------------------------------------------------------
#  Copyright (c) Microsoft Corporation. All rights reserved.
#  Licensed under the MIT License (MIT). See LICENSE in the repo root for license information.
#  ------------------------------------------------------------------------------------------

import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Tuple

from attr import dataclass
from azureml.core import Experiment, Model, ScriptRunConfig, Environment, Datastore
from azureml.core.runconfig import RunConfiguration
from azureml.core.workspace import WORKSPACE_DEFAULT_BLOB_STORE_NAME, Workspace

from azure_config import AzureConfig
from source_config import SourceConfig

ENVIRONMENT_VERSION = "1"
DEFAULT_RESULT_IMAGE_NAME = "segmentation.dcm.zip"
DEFAULT_DATA_FOLDER = "data"
SCORE_SCRIPT = "score.py"
RUN_SCORING_SCRIPT = "download_model_and_run_scoring.py"
# The property in the model registry that holds the name of the Python environment
PYTHON_ENVIRONMENT_NAME = "python_environment_name"
IMAGEDATA_FILE_NAME = "imagedata.zip"


@dataclass
class SubmitForInferenceConfig:
    """
    Inference config class.
    """
    model_id: str
    image_data: bytes
    experiment_name: str


def create_run_config(azure_config: AzureConfig,
                      source_config: SourceConfig,
                      environment_name: str) -> ScriptRunConfig:
    """
    Creates a configuration to run the InnerEye training script in AzureML.
    :param azure_config: azure related configurations to use for model scale-out behaviour
    :param source_config: configurations for model execution, such as name and execution mode
    :param environment_name: If specified, try to retrieve the existing Python environment with this name. If that
    is not found, create one from the Conda files provided in `source_config`. This parameter is meant to be used
    when running inference for an existing model.
    :return: The configured script run.
    """
    # AzureML seems to sometimes expect the entry script path in Linux format, hence convert to posix path
    entry_script_relative_path = source_config.entry_script.relative_to(source_config.root_folder).as_posix()
    logging.info(f"Entry script {entry_script_relative_path} ({source_config.entry_script} "
                 f"relative to source directory {source_config.root_folder})")
    max_run_duration = 43200  # 12 hours in seconds
    workspace = azure_config.get_workspace()
    run_config = RunConfiguration(script=entry_script_relative_path, arguments=source_config.script_params)
    env = Environment.get(azure_config.get_workspace(), name=environment_name, version=ENVIRONMENT_VERSION)
    logging.info(f"Using existing Python environment '{env.name}'.")
    run_config.environment = env
    run_config.target = azure_config.cluster
    run_config.max_run_duration_seconds = max_run_duration
    # Use blob storage for storing the source, rather than the FileShares section of the storage account.
    run_config.source_directory_data_store = workspace.datastores.get(WORKSPACE_DEFAULT_BLOB_STORE_NAME).name
    script_run_config = ScriptRunConfig(source_directory=str(source_config.root_folder), run_config=run_config)
    return script_run_config


def submit_for_inference(args: SubmitForInferenceConfig, workspace: Workspace, azure_config: AzureConfig) -> Tuple[str, str]:
    """
    Create and submit an inference to AzureML, and optionally download the resulting segmentation.
    :param args: configuration, see SubmitForInferenceConfig
    :param workspace: Azure ML workspace.
    :param azure_config: An object with all necessary information for accessing Azure.
    :return: Azure Run Id (and the target path on the datastore, including the uuid, for a unit
    test to ensure that the image data zip is overwritten after infernece)
    """
    logging.info("Identifying model")
    model = Model(workspace=workspace, id=args.model_id)
    model_id = model.id
    logging.info(f"Identified model {model_id}")

    source_directory = tempfile.TemporaryDirectory()
    source_directory_path = Path(source_directory.name)
    logging.info(f"Building inference run submission in {source_directory_path}")

    image_folder = source_directory_path / DEFAULT_DATA_FOLDER
    image_folder.mkdir(parents=True, exist_ok=True)
    image_path = image_folder / IMAGEDATA_FILE_NAME
    image_path.write_bytes(args.image_data)

    image_datastore = Datastore(workspace, azure_config.datastore_name)
    target_path = f"{azure_config.image_data_folder}/{str(uuid.uuid4())}"
    image_datastore.upload_files(files=[str(image_path)], target_path=target_path, overwrite=False, show_progress=False)
    image_path.unlink()

    # Retrieve the name of the Python environment that the training run used. This environment
    # should have been registered. If no such environment exists, it will be re-create from the
    # Conda files provided.
    python_environment_name = model.tags.get(PYTHON_ENVIRONMENT_NAME, "")
    if python_environment_name == "":
        raise ValueError(
            f"Model ID: {model_id} does not contain an environment tag {PYTHON_ENVIRONMENT_NAME}")

    # Copy the scoring script from the repository. This will start the model download from Azure,
    # and invoke the scoring script.
    entry_script = source_directory_path / Path(RUN_SCORING_SCRIPT).name
    current_file_path = Path(os.path.dirname(os.path.realpath(__file__)))
    shutil.copyfile(current_file_path / str(RUN_SCORING_SCRIPT), str(entry_script))
    source_config = SourceConfig(
        root_folder=source_directory_path,
        entry_script=entry_script,
        script_params=["--model_id", model_id,
                       "--script_name", SCORE_SCRIPT,
                       "--datastore_name", azure_config.datastore_name,
                       "--datastore_image_path", str(Path(target_path) / IMAGEDATA_FILE_NAME)])
    run_config = create_run_config(azure_config, source_config, environment_name=python_environment_name)
    exp = Experiment(workspace=workspace, name=args.experiment_name)
    run = exp.submit(run_config)
    logging.info(f"Submitted run {run.id} in experiment {run.experiment.name}")
    logging.info(f"Run URL: {run.get_portal_url()}")
    source_directory.cleanup()
    logging.info(f"Deleted submission directory {source_directory_path}")
    return run.id, target_path
