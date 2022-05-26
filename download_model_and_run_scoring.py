#  ------------------------------------------------------------------------------------------
#  Copyright (c) Microsoft Corporation. All rights reserved.
#  Licensed under the MIT License (MIT). See LICENSE in the repo root for license information.
#  ------------------------------------------------------------------------------------------

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from azureml.core import Model, Run, Datastore


DELETED_IMAGE_DATA_NOTIFICATION = "image data deleted"


def spawn_and_monitor_subprocess(process: str, args: List[str], env: Dict[str, str]) -> Tuple[int, List[str]]:
    """
    Helper function to spawn and monitor subprocesses.
    :param process: The name or path of the process to spawn.
    :param args: The args to the process.
    :param env: The environment variables for the process (default is the environment variables of the parent).
    :return: Return code after the process has finished, and the list of lines that were written to stdout by the subprocess.
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


def run() -> None:
    """
    This script is run in an AzureML experiment which was submitted by submit_for_inference.

    It downloads a model from AzureML, and starts the score script (usually score.py) which is in the root
    folder of the model. The image data zip is are downloaded from the AzureML datastore where it was copied
    by submit_for_inference. Once scoring is completed the image data zip is overwritten with some simple
    text in lieue of there being a delete method in the AzureML datastore API. This ensure that the run does
    not retain images.
    """
    parser = argparse.ArgumentParser(description='Execute code inside of an AzureML model')
    parser.add_argument('--model_id', dest='model_id', action='store', type=str, required=True, 
                        help='AzureML model ID')
    parser.add_argument('--script_name', dest='script_name', action='store', type=str, required=True,
                        help='Name of the script in the model that will produce the image scores')
    parser.add_argument('--datastore_name', dest='datastore_name', action='store', type=str, required=True,
                        help='Name of the datastore where the image data zip has been copied')
    parser.add_argument('--datastore_image_path', dest='datastore_image_path', action='store', type=str, required=True,
                        help='Path to the image data zip copied to the datastore')
    known_args, _ = parser.parse_known_args()    

    current_run = Run.get_context()
    if not hasattr(current_run, 'experiment'):
        raise ValueError("This script must run in an AzureML experiment")

    workspace = current_run.experiment.workspace
    model = Model(workspace=workspace, id=known_args.model_id)

    # Download the model from AzureML
    here = Path.cwd().absolute()
    model_path = Path(model.download(here)).absolute()

    # Download the image data zip from the named datastore where it was copied by submit_for_infernece
    # We copy it to a data store, rather than using the AzureML experiment's snapshot, so that we can
    # overwrite it after the inference and thus not retain image data.
    image_datastore = Datastore(workspace, known_args.datastore_name)
    prefix = str(Path(known_args.datastore_image_path).parent)
    image_datastore.download(target_path=here, prefix=prefix, overwrite=False, show_progress=False)
    downloaded_image_path = here / known_args.datastore_image_path

    env = dict(os.environ.items())
    # Work around https://github.com/pytorch/pytorch/issues/37377
    env['MKL_SERVICE_FORCE_INTEL'] = '1'
    # The model should include all necessary code, hence point the Python path to its root folder.
    env['PYTHONPATH'] = str(model_path)

    score_script = model_path / known_args.script_name
    score_args = [
        str(score_script),
        '--data_folder', str(here / Path(known_args.datastore_image_path).parent),
        '--image_files', str(downloaded_image_path),
        '--model_id', known_args.model_id,
        '--use_dicom', 'True']

    if not score_script.exists():
        raise ValueError(
            f"The specified entry script {known_args.script_name} does not exist in {model_path}")

    print(f"Starting Python with these arguments: {score_args}")
    try:
        code, stdout = spawn_and_monitor_subprocess(process=sys.executable, args=score_args, env=env)
    finally:
        # Delete image data zip locally
        downloaded_image_path.unlink()
        # Overwrite image data zip in datastore. The datastore API does not (yet) include deletion
        # and so we overwrite the image data zip with a short piece of text instead. Later these
        # overwritten image data zip files can be erased, we recommend using a blobstore lifecylce
        # management policy to delete them after a period of time, e.g. seven days.
        downloaded_image_path.write_text(DELETED_IMAGE_DATA_NOTIFICATION)
        image_datastore.upload_files(files=[str(downloaded_image_path)], target_path=prefix, overwrite=True, show_progress=False)
        # Delete the overwritten image data zip locally
        downloaded_image_path.unlink()
    if code != 0:
        print(f"Python terminated with exit code {code}. Stdout: {os.linesep.join(stdout)}")
    sys.exit(code)


if __name__ == '__main__':
    run()
