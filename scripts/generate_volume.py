import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import DATABASE_URL
from app.volume import VOLUME_COUNT, generate_volume


def main() -> None:
    inserted = generate_volume(DATABASE_URL, VOLUME_COUNT)
    if inserted == 0:
        print("East already has the extra certificate rows. Nothing was added.")
        print("python start.py --reset restores the small demo dataset.")
        return
    print(f"Inserted {inserted} East certificates.")
    print("Seeded demo rows were not changed. Startup does not load this dataset.")


if __name__ == "__main__":
    main()
