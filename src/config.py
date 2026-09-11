from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(exist_ok=True)
print("Project configuratiiom loafded successfully!")
print(f"Project directory: {BASE_DIR}")