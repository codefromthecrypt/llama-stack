# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.

import json
import os
from datetime import datetime
from enum import Enum
from typing import List, Optional

import pkg_resources
import yaml

from llama_toolchain.common.config_dirs import BUILDS_BASE_DIR
from llama_toolchain.common.exec import run_with_pty
from llama_toolchain.common.serialize import EnumEncoder
from pydantic import BaseModel

from termcolor import cprint

from llama_toolchain.core.datatypes import *  # noqa: F403
from pathlib import Path

from llama_toolchain.core.distribution import api_providers, SERVER_DEPENDENCIES


class ImageType(Enum):
    docker = "docker"
    conda = "conda"


class Dependencies(BaseModel):
    pip_packages: List[str]
    docker_image: Optional[str] = None


class ApiInput(BaseModel):
    api: Api
    provider: str


def build_package(build_config: BuildConfig, build_file_path: Path):
    package_deps = Dependencies(
        docker_image=build_config.distribution_spec.docker_image or "python:3.10-slim",
        pip_packages=SERVER_DEPENDENCIES,
    )

    # extend package dependencies based on providers spec
    all_providers = api_providers()
    for api_str, provider in build_config.distribution_spec.providers.items():
        providers_for_api = all_providers[Api(api_str)]
        if provider not in providers_for_api:
            raise ValueError(
                f"Provider `{provider}` is not available for API `{api_str}`"
            )

        provider_spec = providers_for_api[provider]
        package_deps.pip_packages.extend(provider_spec.pip_packages)
        if provider_spec.docker_image:
            raise ValueError("A stack's dependencies cannot have a docker image")

    if build_config.image_type == ImageType.docker.value:
        script = pkg_resources.resource_filename(
            "llama_toolchain", "core/build_container.sh"
        )
        args = [
            script,
            build_config.name,
            package_deps.docker_image,
            str(build_file_path),
            " ".join(package_deps.pip_packages),
        ]
    else:
        script = pkg_resources.resource_filename(
            "llama_toolchain", "core/build_conda_env.sh"
        )
        args = [
            script,
            build_config.name,
            " ".join(package_deps.pip_packages),
        ]

    return_code = run_with_pty(args)
    if return_code != 0:
        cprint(
            f"Failed to build target {build_config.name} with return code {return_code}",
            color="red",
        )
        return