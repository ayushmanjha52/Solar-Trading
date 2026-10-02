"""Milestone 1 end to end: download, preprocess, weather, sanity figure.

    python -m ml.data
"""

from ml.data import download, preprocess, sanity, weather

if __name__ == "__main__":
    download.main()
    preprocess.main()
    weather.main()
    sanity.main()
