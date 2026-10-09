"""`python run.py data`: fetch and process every data source.

Source adapters arrive in milestone b; for now this lists what will be fetched.
"""

from __future__ import annotations

from sitescore.config import load_region, load_sources
from sitescore.settings import get_settings


def main() -> None:
    settings = get_settings()
    region = load_region()
    print(f"Region: {region.name} (LGA {region.lga_code})\n")
    for key, src in load_sources().items():
        key_note = ""
        if src.env_key:
            key_note = " [key set]" if getattr(settings, src.env_key.lower(), None) else " [no key -> mock]"
        print(f"  {key:<22} {src.title}{key_note}")


if __name__ == "__main__":
    main()
