import os
import tempfile

# The hub module keeps its workspace on disk; point it at a throwaway folder and the stand-ins.
os.environ["CUEON_DATA"] = tempfile.mkdtemp(prefix="cueon-test-")
os.environ["CUEON_FAKE"] = "1"
