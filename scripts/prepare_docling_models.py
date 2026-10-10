"""Download PDF models to ordinary local files, including on Windows without symlinks.

Run from the repository root: python -m scripts.prepare_docling_models
"""
from pathlib import Path

from app.document_processing.config import DEFAULT_ARTIFACTS_PATH, Settings


def main() -> None:
    from docling.utils.model_downloader import download_models

    settings = Settings.from_env()
    destination = Path(settings.artifacts_path or DEFAULT_ARTIFACTS_PATH).resolve()
    download_models(
        output_dir=destination, with_code_formula=False, with_picture_classifier=False,
        with_rapidocr=True, progress=True,
    )
    (destination / ".ready").write_text("Docling PDF models downloaded\n", encoding="utf-8")
    print(f"Docling models ready: {destination}")


if __name__ == "__main__":
    main()
