#  ------------------------------------------------------------------------------------------
#  Copyright (c) Microsoft Corporation. All rights reserved.
#  Licensed under the MIT License (MIT). See LICENSE in the repo root for license information.
#  ------------------------------------------------------------------------------------------

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import conda_merge
import requests
import ruamel.yaml
from attr import dataclass
from azureml.core import Experiment, Model
from azureml.core.conda_dependencies import CondaDependencies
from azureml.core.workspace import WORKSPACE_DEFAULT_BLOB_STORE_NAME, Workspace
from azureml.data.dataset_consumption_config import DatasetConsumptionConfig
from azureml.train.dnn import PyTorch

from azure_config import AzureConfig
from source_config import SourceConfig

ENVIRONMENT_YAML_FILE_NAME = "environment.yml"
DEFAULT_RESULT_IMAGE_NAME = "segmentation.dcm.zip"
DEFAULT_DATA_FOLDER = "data"
SCORE_SCRIPT = "score.py"
RUN_SCORING_SCRIPT = "download_model_and_run_scoring.py"


def merge_conda_files(files: List[Path], result_file: Path) -> None:
    """
    Merges the given Conda environment files using the conda_merge package, and writes the merged file to disk.
    :param files: The Conda environment files to read.
    :param result_file: The location where the merge results should be written.
    """
    # This code is a slightly modified version of conda_merge. That code can't be re-used easily
    # it defaults to writing to stdout
    env_definitions = [conda_merge.read_file(str(f)) for f in files]
    unified_definition = {}
    NAME = "name"
    CHANNELS = "channels"
    DEPENDENCIES = "dependencies"
    name = conda_merge.merge_names(env.get(NAME) for env in env_definitions)
    if name:
        unified_definition[NAME] = name
    try:
        channels = conda_merge.merge_channels(env.get(CHANNELS) for env in env_definitions)
    except conda_merge.MergeError:
        logging.error("Failed to merge channel priorities.")
        raise
    if channels:
        unified_definition[CHANNELS] = channels
    deps = conda_merge.merge_dependencies(env.get(DEPENDENCIES) for env in env_definitions)
    if deps:
        unified_definition[DEPENDENCIES] = deps
    with result_file.open("w") as f:
        ruamel.yaml.dump(unified_definition, f, indent=2, default_flow_style=False)


def _log_conda_dependencies_stats(conda: CondaDependencies, message_prefix: str) -> None:
    """
    Write number of conda and pip packages to logs.
    :param conda: A conda dependencies object
    :param message_prefix: A message to prefix to the log string.
    """
    conda_packages_count = len(list(conda.conda_packages))
    pip_packages_count = len(list(conda.pip_packages))
    logging.info(f"{message_prefix}: {conda_packages_count} conda packages, {pip_packages_count} pip packages")
    logging.debug("  Conda packages:")
    for p in conda.conda_packages:
        logging.debug(f"    {p}")
    logging.debug("  Pip packages:")
    for p in conda.pip_packages:
        logging.debug(f"    {p}")


def merge_conda_dependencies(files: List[Path]) -> CondaDependencies:
    """
    Creates a CondaDependencies object from the Conda environments specified in one or more files.
    The resulting object contains the union of the Conda and pip packages in the files, where merging
    is done via the conda_merge package.
    :param files: The Conda environment files to read.
    :return: A CondaDependencies object that contains packages from all the files.
    """
    for file in files:
        _log_conda_dependencies_stats(CondaDependencies(file), f"Conda environment in {file}")
    merged_file = tempfile.NamedTemporaryFile(delete=False)
    merge_conda_files(files, result_file=Path(merged_file.name))
    merged_dependencies = CondaDependencies(merged_file.name)
    _log_conda_dependencies_stats(merged_dependencies, "Merged Conda environment")
    merged_file.close()
    return merged_dependencies


def pytorch_version_from_conda_dependencies(conda_dependencies: CondaDependencies) -> Optional[str]:
    """
    Given a CondaDependencies object, look for a spec of the form "pytorch=...", and return
    whichever supported version is compatible with the value, or None if there isn't one.
    """
    supported_versions = PyTorch.get_supported_versions()
    for spec in conda_dependencies.conda_packages:
        components = spec.split("=")
        if len(components) == 2 and components[0] == "pytorch":
            version = components[1]
            for supported in supported_versions:
                if version.startswith(supported) or supported.startswith(version):
                    return supported
    return None


def create_estimator_from_configs(azure_config: AzureConfig,
                                  source_config: SourceConfig,
                                  estimator_inputs: List[DatasetConsumptionConfig]) -> PyTorch:
    """
    Create an return a PyTorch estimator from the provided configuration information.
    :param azure_config: Azure configuration, used to store various values for the job to be submitted
    :param source_config: source configutation, for other needed values
    :param estimator_inputs: value for the "inputs" field of the estimator.
    :return:
    """
    # AzureML seems to sometimes expect the entry script path in Linux format, hence convert to posix path
    entry_script_relative_path = source_config.entry_script.relative_to(source_config.root_folder).as_posix()
    logging.info(f"Entry script {entry_script_relative_path} ({source_config.entry_script} relative to "
                 f"source directory {source_config.root_folder})")
    environment_variables = {
        "AZUREML_OUTPUT_UPLOAD_TIMEOUT_SEC": str(source_config.upload_timeout_seconds),
        "MKL_SERVICE_FORCE_INTEL": "1",
        **(source_config.environment_variables or {})
    }
    # Merge the project-specific dependencies with the packages that InnerEye itself needs. This should not be
    # necessary if the innereye package is installed. It is necessary when working with an outer project and
    # InnerEye as a git submodule and submitting jobs from the local machine.
    # In case of version conflicts, the package version in the outer project is given priority.
    conda_dependencies = merge_conda_dependencies(source_config.conda_dependencies_files)  # type: ignore
    if azure_config.pip_extra_index_url:
        # When an extra-index-url is supplied, swap the order in which packages are searched for.
        # This is necessary if we need to consume packages from extra-index that clash with names of packages on
        # pypi
        conda_dependencies.set_pip_option(f"--index-url {azure_config.pip_extra_index_url}")
        conda_dependencies.set_pip_option("--extra-index-url https://pypi.org/simple")
    # create Estimator environment
    framework_version = pytorch_version_from_conda_dependencies(conda_dependencies)
    assert framework_version is not None, "The AzureML SDK is behind PyTorch, it does not yet know the version we use."
    logging.info(f"PyTorch framework version: {framework_version}")
    workspace = azure_config.get_workspace()
    estimator = PyTorch(
        source_directory=str(source_config.root_folder),
        entry_script=entry_script_relative_path,
        script_params=source_config.script_params,
        compute_target=azure_config.cluster,
        # Use blob storage for storing the source, rather than the FileShares section of the storage account.
        source_directory_data_store=workspace.datastores.get(WORKSPACE_DEFAULT_BLOB_STORE_NAME),
        inputs=estimator_inputs,
        environment_variables=environment_variables,
        shm_size=azure_config.docker_shm_size,
        use_docker=True,
        use_gpu=True,
        framework_version=framework_version
    )
    estimator.run_config.environment.python.conda_dependencies = conda_dependencies
    return estimator


@dataclass
class SubmitForInferenceConfig:
    """
    Inference config class.
    """
    model_id: str
    image_data: bytes
    experiment_name: str = "inference"


def download_files_from_model(model_sas_urls: Dict[str, str], base_name: str, dir_path: Path) -> List[Path]:
    """
    Identifies all the files in an AzureML model that have a given file name (ignoring path), and downloads them
    to a folder.
    :param model_sas_urls: The files making up the model, as a mapping from file name to a URL with
    an SAS token.
    :param base_name: The file name of the files to download.
    :param dir_path: The folder into which the files will be written. All downloaded files will keep the relative
    path that they also have in the model.
    :return: a list of the files that were downloaded.
    """
    downloaded: List[Path] = []
    for path, url in model_sas_urls.items():
        if Path(path).name == base_name:
            target_path = dir_path / path
            target_path.parent.mkdir(exist_ok=True, parents=True)
            target_path.write_bytes(requests.get(url, allow_redirects=True).content)
            # Remove additional information from the URL to make it more legible
            index = url.find("?")
            if index > 0:
                url = url[:index]
            logging.info(f"Downloaded {path} from {url}")
            downloaded.append(target_path)
    if not downloaded:
        logging.warning(f"No file(s) with name '{base_name}' were found in the model!")
    return downloaded


def submit_for_inference(args: SubmitForInferenceConfig, workspace: Workspace, azure_config: AzureConfig) -> str:
    """
    Create and submit an inference to AzureML, and optionally download the resulting segmentation.
    :param args: configuration, see SubmitForInferenceConfig
    :param workspace: Azure ML workspace.
    :param azure_config: An object with all necessary information for accessing Azure.
    :return: Azure Run Id.
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
    image_path = image_folder / "imagedata.zip"
    image_path.write_bytes(args.image_data)

    model_sas_urls = model.get_sas_urls()
    # Identifies all the files with basename "environment.yml" in the model and downloads them.
    # These downloads should go into a temp folder that will most likely not be included in the model itself,
    # because the AzureML run will later download the model into the same folder structure, and the file names might
    # clash.
    temp_folder = source_directory_path / "temp_for_scoring"
    conda_files = download_files_from_model(model_sas_urls, ENVIRONMENT_YAML_FILE_NAME, dir_path=temp_folder)
    if not conda_files:
        raise ValueError("At least 1 Conda environment definition must exist in the model.")
    # Copy the scoring script from the repository. This will start the model download from Azure, and invoke the
    # scoring script.
    entry_script = source_directory_path / Path(RUN_SCORING_SCRIPT).name
    current_file_path = Path(os.path.dirname(os.path.realpath(__file__)))
    shutil.copyfile(current_file_path / str(RUN_SCORING_SCRIPT),
                    str(entry_script))
    source_config = SourceConfig(
        root_folder=source_directory_path,
        entry_script=entry_script,
        script_params={"--model-folder": ".",
                       "--model-id": model_id,
                       SCORE_SCRIPT: "",
                       # The data folder must be relative to the root folder of the AzureML job. test_image_files
                       # is then just the file relative to the data_folder
                       "--data_folder": image_path.parent.name,
                       "--image_files": image_path.name,
                       "--use_dicom": "True"},
        conda_dependencies_files=conda_files,
    )
    estimator = create_estimator_from_configs(azure_config, source_config, [])
    exp = Experiment(workspace=workspace, name=args.experiment_name)
    run = exp.submit(estimator)
    logging.info(f"Submitted run {run.id} in experiment {run.experiment.name}")
    logging.info(f"Run URL: {run.get_portal_url()}")
    source_directory.cleanup()
    logging.info(f"Deleted submission directory {source_directory_path}")
    return run.id
