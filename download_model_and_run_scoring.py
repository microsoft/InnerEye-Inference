#  ------------------------------------------------------------------------------------------
#  Copyright (c) Microsoft Corporation. All rights reserved.
#  Licensed under the MIT License (MIT). See LICENSE in the repo root for license information.
#  ------------------------------------------------------------------------------------------

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

from azureml.core import Model, Run, Datastore


DELETED_IMAGE_DATA_NOTIFICATION = "image data deleted"


def spawn_and_monitor_subprocess(
        process: str,
        args: List[str],
        env: Dict[str, str]) -> Tuple[int, List[str]]:
    """
    Helper function to spawn and monitor subprocesses.
    :param process: The name or path of the process to spawn.
    :param args: The args to the process.
    :param env: The environment variables for the process (default is the environment variables of
    the parent).
    :return: Return code after the process has finished, and the list of lines that were written
    to stdout by the
    subprocess.
    """
    p = subprocess.Popen(
        [process] + args,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env
    )

    # Read and print all the lines that are printed by the subprocess
    stdout_lines = [line.decode('UTF-8').strip() for line in p.stdout]  # type: ignore
    for line in stdout_lines:
        print(line)

    # return the subprocess error code to the calling job so that it is reported to AzureML
    return p.wait(), stdout_lines


def get_unknown_arg_value(unknown_args: List[str], option: str) -> Any:
    """
    Helper function to return the value of an option in the unparsed 'unknown args' of a parameter
    list
    :param unknown_args: the unparsed 'unknown args' list
    :param option: the option whose value we want
    :return: the value of the option
    """
    if option in unknown_args:
        index_of_option = unknown_args.index(option)
        return unknown_args[index_of_option + 1]
    raise ValueError(f"{option} not found in {unknown_args}")


def run() -> None:
    """
    Downloads a model from AzureML, and starts the score script (usually score.py) in the root
    folder of the model. Downloading the model is only supported if the present code is running
    inside of AzureML. When running outside of AzureML, the model must have been downloaded
    beforehand into the folder given by the model-folder argument.
    The script is executed with the current Python interpreter.
    If the model requires a specific Conda environment to run in, the caller of this script needs
    to ensure that this has been set up correctly (taking the environment.yml file stored in the
    model).
    All arguments that are not recognized by the present code will be passed through to `score.py`
    unmodified.
    Example arguments:
        download_model_and_run_scoring.py --model-id=Foo:1 score.py --foo=1 --bar
    This would attempt to download version 1 of model Foo, and then start the script score.py in the
    model's root folder. Arguments --foo and --bar are passed through to score.py
    """
    parser = argparse.ArgumentParser(description='Execute code inside of an AzureML model')
    # Use argument names with dashes here. The rest of the codebase uses _ as the separator, meaning
    # that there can't be a clash of names with arguments that are passed through to score.py
    parser.add_argument(
        '--model-folder',
        dest='model_folder',
        action='store',
        type=str)
    parser.add_argument(
        '--model-id',
        dest='model_id',
        action='store',
        type=str)
    parser.add_argument(
        '--datastore-name',
        dest='datastore_name',
        action='store',
        type=str)
    parser.add_argument(
        '--datastore-image-path',
        dest='datastore_image_path',
        action='store',
        type=str)
    known_args, unknown_args = parser.parse_known_args()

    if not known_args.model_id:
        raise ValueError("No model ID given.")

    current_run = Run.get_context()
    if not hasattr(current_run, 'experiment'):
        raise ValueError("The model-id argument can only be used inside AzureML. Please drop the"
                            "argument, and supply the downloaded model in the model-folder.")

    workspace = current_run.experiment.workspace
    model = Model(workspace=workspace, id=known_args.model_id)

    # Download the model from AzureML into a sub-folder of model_folder
    model_folder = known_args.model_folder or "."
    model_folder = str(Path(model.download(model_folder)).absolute())

    # Download the image data zip from the default datastore
    data_folder = get_unknown_arg_value(unknown_args, "--data_folder")
    image_files_zip = get_unknown_arg_value(unknown_args, "--image_files")
    image_datastore = Datastore(workspace, known_args.datastore_name)
    image_datastore.download(
        target_path=data_folder,
        prefix=known_args.datastore_image_path,
        overwrite=False,
        show_progress=False)
    downloaded_image_path = Path(data_folder)
    downloaded_image_path /= known_args.datastore_image_path
    downloaded_image_path /= image_files_zip
    image_data_zip_path = Path(data_folder) / image_files_zip
    downloaded_image_path.rename(image_data_zip_path)

    env = dict(os.environ.items())
    # Work around https://github.com/pytorch/pytorch/issues/37377
    env['MKL_SERVICE_FORCE_INTEL'] = '1'
    # The model should include all necessary code, hence point the Python path to its root folder.
    env['PYTHONPATH'] = model_folder

    if not unknown_args:
        raise ValueError("No arguments specified for starting the scoring script.")
    score_script = Path(model_folder) / unknown_args[0]
    score_args = [str(score_script), *unknown_args[1:]]

    if not score_script.exists():
        raise ValueError(
            f"The specified entry script {score_args[0]} does not exist in {model_folder}")
    print(f"Starting Python with these arguments: {' '.join(score_args)}")
    code, stdout = -1, ["default stdout message"]
    try:
        code, stdout = spawn_and_monitor_subprocess(
            process=sys.executable,
            args=score_args, env=env)
    finally:
        # Delete image data zip locally
        image_data_zip_path.unlink()
        # Overwrite image data zip in datastore
        with image_data_zip_path.open(mode="w") as replacement_file:
            replacement_file.writelines([DELETED_IMAGE_DATA_NOTIFICATION])
        image_datastore.upload_files(
            files=[str(image_data_zip_path)],
            target_path=known_args.datastore_image_path,
            overwrite=True,
            show_progress=False)
        image_data_zip_path.unlink()
    if code != 0:
        print(f"Python terminated with exit code {code}. Stdout: {os.linesep.join(stdout)}")
    sys.exit(code)


if __name__ == '__main__':
    run()
