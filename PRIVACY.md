# Privacy and network behavior — review draft

This is a source-inspection draft for the Nexus build, not a completed privacy
audit. No claim about every dependency's behavior is made.

ModDiver Laboratory stores settings, mod libraries, caches, stock captures and
recovery data locally under the user's profile. Selected game files are read
and modified for requested modding operations. These files are not intended to
be uploaded by the application's documented workflows.

The Nexus build disables application update controls and remote historical
repair datasets. Links to GitHub, Nexus Mods, AyakaMods, HellForge, Patreon and
Ko-fi open the user's browser when requested; those sites apply their own
privacy policies and can receive the browser's normal connection information.
Other distributions have update and repair-download functions and need separate
review before sharing this policy.

The bundled audioStudio code contains optional Audiokinetic Wwise integration
connecting to a local WAAPI server at 127.0.0.1. Whether each optional path is
reachable in the ModDiver interface and what Wwise itself transmits still needs
verification. Wwise is not granted an open-source license by this project.

The source describes the app as not requiring telemetry. This has not been
independently verified by runtime network capture. Before SignPath submission,
review all reachable network functions and third-party services, document any
automatic transfers, and provide disclosure and opt-out if required by SignPath.
