"""Build-time switches for the Nexus-specific distribution."""
from pathlib import Path

NEXUS_BUILD = (Path(__file__).with_name('nexus-build.json')).is_file()
DATA_DIRECTORY = 'ModDiverLabNexus' if NEXUS_BUILD else 'ModDiverLab'
LEGACY_DIRECTORY = 'YAOModForgeNexus' if NEXUS_BUILD else 'YAOModForge'
BASELINE_DIRECTORY = 'ModDiver Lab Nexus Baseline Data' if NEXUS_BUILD else 'ModDiver Lab Baseline Data'
SHORTCUT_NAME = 'ModDiver Laboratory Nexus' if NEXUS_BUILD else 'ModDiver Laboratory'
DESKTOP_ID = 'moddiver-laboratory-nexus' if NEXUS_BUILD else 'moddiver-laboratory'
NEXUS_NOTICE = (
    'Awaiting Nexus Mods confirmation on File Submission Guidelines and Terms of Service. '
    'This feature is disabled until further notice.'
)

