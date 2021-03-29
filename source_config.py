from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List


@dataclass
class SourceConfig:
    """
    Contains all information that is required to submit a script to AzureML: Entry script, arguments,
    and information to set up the Python environment inside of the AzureML virtual machine.
    """
    root_folder: Path
    entry_script: Path
    conda_dependencies_files: List[Path]
    script_params: Optional[Dict[str, str]] = None
    upload_timeout_seconds: int = 36000
    environment_variables: Optional[Dict[str, str]] = None

