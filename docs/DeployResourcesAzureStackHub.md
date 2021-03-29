# Deploying Resources on Azure Stack Hub

## Description
This document highlights how to deploy the InnerEye inferencing solution to an Azure Stack Hub subscription. The solution has been packaged as a Cloud Native Application Bundle (CNAB) for deployment purposes. The sections below cover the necessary steps required to deploy the CNAB package to your Azure Stack Hub environment.

## Prerequisites
- Azure Stack Hub subscription
- Docker (Here is a link if you need to install [Docker Installation Instructions](https://docs.docker.com/get-docker/))
- Porter (Here is a link if you need to install: [Porter Installation Instructions](https://porter.sh/install/))
    > **NOTE:** be sure to add porter to your PATH
- Service Principal that has been granted contributor access to your Azure Stack Hub subscription
    - You will need the following information for the service principal
        - Client ID 
        - Client secret
        - Object ID (this is different than the application id and can be found on the enterpise application area of Azure Active Directory)
        - Tenant ID
- Your user account needs to have owner access to the subscription. This is required for assigning access to the service principal for resource deployment.

## Step 1: Prepare for Installation

### Create CNAB Parameter File

Locate the file named `azure-stack-profile.template.txt` and open it for editing. You will need to provide some values so the CNAB package can register your Azure Stack environment and deploy into it. After assigning the required values, save the file as `azure-stack-profile.txt` .

```
azure_stack_tenant_arm="Your Azure Stack Tenant Endpoint"
azure_stack_storage_suffix="Your Azure Stack Storage Suffix"
azure_stack_keyvault_suffix="Your Azure Stack KeyVault Suffix"
azure_stack_location="Your Azure Stack’s location identifier here."
azure_stack_resource_group="Your desired Azure Stack resource group name to create"
```
### Generate Credentials
Open a new shell window and make sure you are in the root directory of this repo. Run the command below to generate credentials required for deployment. Follow the prompts to assign values for the credentials needed. Select "specific value" from the interactive menu for each of the required credential fields. A description of each credential is provided below.

```sh
porter generate credentials
```

|Item|Description|
|----|-----------|
|AZURE_STACK_SP_CLIENT_ID|The client id for the service principal that is registered with your Azure Stack Hub Subscription|
|AZURE_STACK_SP_PASSWORD|The secret associated with the service principal that is registered with your Azure Stack Hub Subscription|
|AZURE_STACK_SP_TENANT_DNS|The DNS for the Azure Active Directory that is tied to your Azure Stack Hub (e.g. mycomany.onmicrosoft.com)|
|AZURE_STACK_SUBSCRIPTION_ID|The subscription id for the subscription on your Azure Stack Hub that you want to deploy into|
|VM_PASSWORD|The password you would like to use for the login to the VM that is deployed as part of this CNAB package|

## Step 2: Build CNAB

Run the command below to build the Porter CNAB package. This step builds the docker invocation image required for executing the CNAB installation steps.

```sh
porter build
```

## Step 3: Install CNAB

### Install CNAB Package
Run the below command to install the CNAB package. This will create a new resource group on you Azure Stack subscription and will deploy the solution into it.

```sh
porter install InnerEyeInferencing --cred InnerEyeInferencing --param-file "azure-stack-profile.txt"
```

### (Optional) Uninstall CNAB Package
If you wish to remove the solution from your Azure Stack Hub, run the below command. Please note that this will delete the entire resource group that the solution was deployed into. If you have created any other custom resources in this resource group, they will also be deleted.

```sh
porter uninstall InnerEyeInferencing --cred InnerEyeInferencing --param-file "azure-stack-profile.txt"
```