import shutil
from pathlib import Path

import pytest

from jobagent.config import load_config

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "config"


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    dest = tmp_path / "config"
    shutil.copytree(FIXTURES_DIR, dest)
    return dest


@pytest.fixture
def app_config(config_dir: Path, tmp_path: Path):
    return load_config(config_dir=config_dir, data_dir=tmp_path / "data")


@pytest.fixture
def profile(app_config):
    return app_config.profile


@pytest.fixture
def preferences(app_config):
    return app_config.preferences


@pytest.fixture
def domain_policy(app_config):
    return app_config.domain_policy
