from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class SourceConfig:
    """
    Contains all information that is required to submit a script to AzureML: Entry script, arguments,
    and information to set up the Python environment inside of the AzureML virtual machine.
    """
    root_folder: Path
    entry_script: Path
    script_params: List[str] = field(default_factory=list)

