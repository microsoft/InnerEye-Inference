import logging
from typing import Optional, Union

from attr import dataclass
from azureml.core import Workspace, Run
from azureml.core.authentication import ServicePrincipalAuthentication, InteractiveLoginAuthentication


@dataclass
class AzureConfig:
    """
    Azure related configurations to set up valid workspace. Note that for a parameter to be settable (when not given
    on the command line) to a value from settings.yml, its default here needs to be None and not the empty
    string, and its type will be Optional[str], not str.
    """
    subscription_id: str  # "The ID of your Azure subscription."
    tenant_id: str  # The Azure tenant ID.
    application_id: str  # The ID of the Service Principal for authentication to Azure.
    workspace_name: str  # The name of the AzureML workspace that should be used.
    resource_group: str  # The Azure resource group that contains the AzureML workspace.
    cluster: str  # The name of the GPU cluster inside the AzureML workspace, that should execute the job.
    experiment_name: str
    service_principal_secret: str
    datastore_name: str  # The datastore data store for temp image storage.
    image_data_folder: str  # The folder name in the data store for temp image storage.
    _workspace: Optional[Workspace] = None  # "The cached workspace object

    @staticmethod
    def is_offline_run_context(run_context: Run) -> bool:
        """
        Tells if a run_context is offline by checking if it has an experiment associated with it.
        :param run_context: Context of the run to check
        :return:
        """
        return not hasattr(run_context, 'experiment')

    def get_workspace(self) -> Workspace:
        """
        Return a workspace object for an existing Azure Machine Learning Workspace (or default from YAML).
        When running inside AzureML, the workspace that is retrieved is always the one in the current
        run context. When running outside AzureML, it is created or accessed with the service principal.
        This function will read the workspace only in the first call to this method, subsequent calls will return
        a cached value.
        Throws an exception if the workspace doesn't exist or the required fields don't lead to a uniquely
        identifiable workspace.
        :return: Azure Machine Learning Workspace
        """
        if self._workspace:
            return self._workspace
        run_context = Run.get_context()
        if self.is_offline_run_context(run_context):
            print(self.subscription_id)
            print(self.resource_group)
            if self.subscription_id and self.resource_group:
                service_principal_auth = self.get_service_principal_auth()
                self._workspace = Workspace.get(
                    name=self.workspace_name,
                    auth=service_principal_auth,
                    subscription_id=self.subscription_id,
                    resource_group=self.resource_group)
            else:
                raise ValueError("The values for 'subscription_id' and 'resource_group' were not found. "
                                 "Was the Azure setup completed?")
        else:
            self._workspace = run_context.experiment.workspace
        return self._workspace

    def get_service_principal_auth(self) -> Optional[Union[InteractiveLoginAuthentication,
                                                           ServicePrincipalAuthentication]]:
        """
        Creates a service principal authentication object with the application ID stored in the present object.
        The application key is read from the environment.
        :return: A ServicePrincipalAuthentication object that has the application ID and key or None if the key
         is not present
        """
        secret = self.service_principal_secret
        if secret is not None:
            logging.info("Starting with ServicePrincipalAuthentication")
            service_principal = ServicePrincipalAuthentication(
                tenant_id=self.tenant_id,
                service_principal_id=self.application_id,
                service_principal_password=secret)
            return service_principal

        raise ValueError("Invalid service_principal_secret")
