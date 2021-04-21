import logging
import os
from pathlib import Path
from typing import Dict

from azureml.core import Workspace
from injector import singleton, Binder

from azure_config import AzureConfig
from configuration_constants import (API_AUTH_SECRET_ENVIRONMENT_VARIABLE, CLUSTER, WORKSPACE_NAME,
                                     EXPERIMENT_NAME, RESOURCE_GROUP, SUBSCRIPTION_ID,
                                     APPLICATION_ID, TENANT_ID, IMAGE_DATA_FOLDER, DATASTORE_NAME,
                                     AZUREML_SERVICE_PRINCIPAL_SECRET_ENVIRONMENT_VARIABLE)

PROJECT_SECRETS_FILE = Path(__file__).resolve().parent / Path("set_environment.sh")


def read_secret_from_file(secret_name: str) -> str:
    """
    Reads a bash file with exports and returns the variables and values as dict
    :return: A dictionary with secrets, or None if the file does not exist.
    """
    try:
        secrets_file = PROJECT_SECRETS_FILE
        d: Dict[str, str] = {}
        for line in secrets_file.read_text().splitlines():
            if line.startswith("#"): continue
            parts = line.replace("export", "").strip().split("=", 1)
            key = parts[0].strip().upper()
            d[key] = parts[1].strip()
        return d[secret_name]
    except Exception as ex:
        logging.error(f"Missing configuration '{secret_name}'")
        raise ex


def get_environment_variable(environment_variable_name: str) -> str:
    value = os.environ.get(environment_variable_name, None)
    if value is None:
        value = read_secret_from_file(environment_variable_name)
        if value is None:
            raise ValueError(environment_variable_name)
    return value


# AUTHENTICATION SECRET
API_AUTH_SECRET = get_environment_variable(API_AUTH_SECRET_ENVIRONMENT_VARIABLE)
API_AUTH_SECRET_HEADER_NAME = "API_AUTH_SECRET"


def configure(binder: Binder) -> None:
    azure_config = get_azure_config()
    workspace = azure_config.get_workspace()
    binder.bind(Workspace, to=workspace, scope=singleton)
    binder.bind(AzureConfig, to=azure_config, scope=singleton)


def get_azure_config() -> AzureConfig:
    return AzureConfig(cluster=get_environment_variable(CLUSTER),
                       workspace_name=get_environment_variable(WORKSPACE_NAME),
                       experiment_name=get_environment_variable(EXPERIMENT_NAME),
                       resource_group=get_environment_variable(RESOURCE_GROUP),
                       subscription_id=get_environment_variable(SUBSCRIPTION_ID),
                       application_id=get_environment_variable(APPLICATION_ID),
                       service_principal_secret=get_environment_variable(
                           AZUREML_SERVICE_PRINCIPAL_SECRET_ENVIRONMENT_VARIABLE),
                       tenant_id=get_environment_variable(TENANT_ID),
                       datastore_name=get_environment_variable(DATASTORE_NAME),
                       image_data_folder=get_environment_variable(IMAGE_DATA_FOLDER))
