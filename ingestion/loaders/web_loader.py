"""
Web loader — downloads PDF documents from regulatory websites.
Supports FATF, Bank of Thailand, and SEC Thailand.
"""
import logging
import time
from pathlib import Path
from typing import List
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# Known regulatory document sources
DOCUMENT_SOURCES = {
    "FATF": [
        "https://www.fatf-gafi.org/content/dam/fatf-gafi/recommendations/FATF%20Recommendations%202012.pdf",
        "https://www.fatf-gafi.org/content/dam/fatf-gafi/guidance/Guidance-AML-CFT-Measures-Virtual-Assets-VASPS.pdf",
    ],
    "BOT": [
        "https://www.bot.or.th/content/dam/bot/documents/th/financial-institutions/aml-news/aml-guideline.pdf",
    ],
    "SEC": [
        "https://www.sec.or.th/TH/Documents/ActandRules/Acts/AML_Act.pdf",
    ],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; FinComply-Ingestion/1.0; "
        "+https://github.com/meuracha/fincomply)"
    )
}


@dataclass
class DownloadResult:
    url: str
    filename: str
    source: str
    success: bool
    local_path: str = ""
    error: str = ""


class WebLoader:
    def __init__(self, output_dir: str = "/app/data/raw", timeout: int = 30):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    def download_source(self, source: str) -> List[DownloadResult]:
        """Download all documents for a given source (FATF/BOT/SEC)."""
        urls = DOCUMENT_SOURCES.get(source.upper(), [])
        if not urls:
            logger.warning(f"No URLs configured for source: {source}")
            return []

        results = []
        for url in urls:
            result = self._download_pdf(url, source)
            results.append(result)
            time.sleep(1)  # polite crawling

        return results

    def download_all(self) -> List[DownloadResult]:
        """Download documents from all configured sources."""
        all_results = []
        for source in DOCUMENT_SOURCES:
            logger.info(f"Downloading from {source}...")
            results = self.download_source(source)
            all_results.extend(results)

        success = sum(1 for r in all_results if r.success)
        logger.info(f"Downloaded {success}/{len(all_results)} documents")
        return all_results

    def _download_pdf(self, url: str, source: str) -> DownloadResult:
        """Download a single PDF from URL."""
        filename = url.split("/")[-1].replace("%20", "_")
        if not filename.endswith(".pdf"):
            filename += ".pdf"

        local_path = self.output_dir / f"{source.lower()}_{filename}"

        # Skip if already downloaded
        if local_path.exists():
            logger.info(f"Already exists: {local_path.name}")
            return DownloadResult(
                url=url,
                filename=filename,
                source=source,
                success=True,
                local_path=str(local_path),
            )

        try:
            response = requests.get(url, headers=HEADERS, timeout=self.timeout, stream=True)
            response.raise_for_status()

            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"Downloaded: {local_path.name} ({local_path.stat().st_size // 1024}KB)")
            return DownloadResult(
                url=url,
                filename=filename,
                source=source,
                success=True,
                local_path=str(local_path),
            )

        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return DownloadResult(
                url=url,
                filename=filename,
                source=source,
                success=False,
                error=str(e),
            )
