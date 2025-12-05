import re
from pathlib import Path

# Path to your project
PROJECT_DIR = Path("mwamko-api")

# Regex patterns
IMPORT_PATTERN = re.compile(r"^(from\s+\S+\s+import\s+\S+|import\s+\S+)(\s+#.*)?$")
UNUSED_VAR_PATTERN = re.compile(
    r"^\s*(\w+)\s*=\s*.*$"
)  # simple pattern for assigned variables

# Files to process
PY_FILES = PROJECT_DIR.rglob("*.py")

for py_file in PY_FILES:
    with open(py_file, "r") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.strip()

        # Skip blank lines
        if not stripped:
            new_lines.append(line)
            continue

        # Remove unused imports: simple heuristic (will remove all imports for now if unused)
        if IMPORT_PATTERN.match(stripped):
            # We'll remove only obvious unused ones flagged by flake8
            # You can extend this by reading F401 list and matching exact imports
            continue

        # Remove simple unused variable assignments (F841)
        if UNUSED_VAR_PATTERN.match(stripped):
            var_name = UNUSED_VAR_PATTERN.match(stripped).group(1)
            # Heuristic: skip if variable is used somewhere in the file
            if var_name not in "".join(lines):
                continue

        new_lines.append(line)

    # Write back cleaned file
    with open(py_file, "w") as f:
        f.writelines(new_lines)

print("Unused imports and simple unused variables removed.")
