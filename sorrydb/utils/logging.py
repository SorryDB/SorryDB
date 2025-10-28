import sys
from datetime import datetime
from io import StringIO
from pathlib import Path


class LogContext:
    """Context manager for logging to both console and file with stdout/stderr capture."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_file = None
        self.old_stdout = None
        self.old_stderr = None
        self.captured_stdout = None
        self.captured_stderr = None

    def __enter__(self):
        self.log_file = open(self.log_path, "w", encoding="utf-8")
        self.old_stdout, self.old_stderr = sys.stdout, sys.stderr
        self.captured_stdout = StringIO()
        self.captured_stderr = StringIO()

        class Tee:
            def __init__(self, *outputs):
                self.outputs = outputs

            def write(self, data):
                timestamp = datetime.now().strftime('[%Y-%m-%d %H:%M:%S] ')
                for output in self.outputs:
                    output.write(f"{timestamp}{data}")
                return len(data)

            def flush(self):
                for output in self.outputs:
                    output.flush()

        sys.stdout = Tee(self.old_stdout, self.log_file, self.captured_stdout)
        sys.stderr = Tee(self.old_stderr, self.log_file, self.captured_stderr)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self.old_stdout
        sys.stderr = self.old_stderr
        self.log_file.close()
